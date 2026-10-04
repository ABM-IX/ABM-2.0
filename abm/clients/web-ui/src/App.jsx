import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, Code2 } from 'lucide-react';
import ChatInterface from './components/ChatInterface';
import FileUpload from './components/FileUpload';
import SessionSidebar from './components/SessionSidebar';
import EditPanel from './components/EditPanel';
import './App.css';

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' or 'edit'
  
  const constraintsRef = useRef(null);

  const fetchSessions = async () => {
    try {
      const res = await fetch('http://localhost:8080/api/sessions');
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleNewChat = () => {
    setCurrentSessionId(null);
  };

  return (
    <motion.div 
      className="app-container" 
      ref={constraintsRef}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <div className="app-header glass-panel">
        <h1 className="glowing-logo">&lt;/ABM&gt; <span className="version-badge">2.0</span></h1>
        <p className="subtitle">Persistent Personal Cognitive Layer</p>
      </div>
      
      <main className="main-content">
        <motion.aside 
          className="sidebar"
          drag
          dragConstraints={constraintsRef}
          dragElastic={0.2}
          whileDrag={{ scale: 1.02, zIndex: 50, cursor: "grabbing" }}
          style={{ cursor: "grab" }}
        >
          <SessionSidebar 
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSelectSession={setCurrentSessionId}
            onNewChat={handleNewChat}
          />
          <FileUpload />
        </motion.aside>
        
        <motion.section 
          className="chat-section glass-panel"
          drag
          dragConstraints={constraintsRef}
          dragElastic={0.2}
          whileDrag={{ scale: 1.01, zIndex: 50, cursor: "grabbing" }}
          style={{ cursor: "grab" }}
        >
          <div className="tabs">
            <button 
              className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <MessageSquare size={18} />
              Chat
            </button>
            <button 
              className={`tab-btn ${activeTab === 'edit' ? 'active' : ''}`}
              onClick={() => setActiveTab('edit')}
            >
              <Code2 size={18} />
              Edit File
            </button>
          </div>
          
          <div className="tab-content chat-content" style={{ display: activeTab === 'chat' ? 'flex' : 'none' }}>
            <ChatInterface 
              currentSessionId={currentSessionId} 
              onSessionUpdated={(newSessionId) => {
                if (newSessionId !== currentSessionId) {
                  setCurrentSessionId(newSessionId);
                }
                fetchSessions();
              }}
            />
          </div>
          
          <div className="tab-content edit-content" style={{ display: activeTab === 'edit' ? 'block' : 'none' }}>
            <EditPanel />
          </div>
        </motion.section>
      </main>
    </motion.div>
  );
}

export default App;
