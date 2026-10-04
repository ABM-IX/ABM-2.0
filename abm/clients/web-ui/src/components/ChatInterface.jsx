import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './ChatInterface.css';

function MessageBubble({ msg }) {
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  return (
    <div className={`message-bubble ${msg.role}`}>
      <div className="message-text">
        {msg.role === 'agent' ? (
          <ReactMarkdown>{msg.text}</ReactMarkdown>
        ) : (
          msg.text
        )}
      </div>
      {msg.role === 'agent' && msg.sources && msg.sources.length > 0 && (
        <div className="message-sources">
          <div 
            className="sources-toggle" 
            onClick={() => setSourcesExpanded(!sourcesExpanded)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', userSelect: 'none' }}
          >
            {sourcesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span style={{ fontWeight: 500, fontSize: '0.85rem' }}>{msg.sources.length} Sources</span>
          </div>
          {sourcesExpanded && (
            <ul style={{ marginTop: '0.75rem' }}>
              {msg.sources.map((src, i) => (
                <li key={i}>
                  <span className="source-collection">[{src.collection}]</span>
                  {src.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatInterface({ currentSessionId, onSessionUpdated }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (currentSessionId) {
      fetch(`http://localhost:8080/api/session?id=${currentSessionId}`)
        .then(res => {
          if (!res.ok) throw new Error('Session not found');
          return res.json();
        })
        .then(data => {
          setMessages(data.messages || []);
        })
        .catch(err => {
          console.error(err);
          setMessages([]);
        });
    } else {
      setMessages([]);
    }
  }, [currentSessionId]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;
    
    const userMessage = { id: Date.now(), role: 'user', text: inputValue };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const payload = { question: userMessage.text };
      if (currentSessionId) {
        payload.session_id = currentSessionId;
      }
      const response = await fetch('http://localhost:8080/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error('API Error');
      
      const data = await response.json();
      
      const agentMessage = {
        id: Date.now() + 1,
        role: 'agent',
        text: data.synthesis || "I couldn't generate an answer.",
        sources: data.hits || [],
        metadata: { department: data.department, confidence: data.confidence }
      };
      
      setMessages(prev => [...prev, agentMessage]);
      onSessionUpdated(data.session_id);
    } catch (error) {
      console.error(error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'agent',
        text: 'Sorry, I encountered an error communicating with the backend.'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {messages.length === 0 && (
          <motion.div 
            className="empty-state"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Bot size={48} className="empty-icon" />
            <p>Ask ABM a question to get started.</p>
          </motion.div>
        )}
        
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div 
              key={msg.id} 
              className={`message-wrapper ${msg.role}`}
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
            >
              <div className={`message-avatar ${msg.role}`}>
                {msg.role === 'agent' ? <Bot size={20} /> : <User size={20} />}
              </div>
              <MessageBubble msg={msg} />
            </motion.div>
          ))}
          
          {isLoading && (
            <motion.div 
              key="loading"
              className="message-wrapper agent"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
            >
              <div className="message-avatar agent">
                <Bot size={20} />
              </div>
              <div className="message-bubble agent loading">
                <Loader2 className="spinner" size={20} />
                <span>Thinking...</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>
      
      <div className="input-area glass-panel">
        <input 
          type="text" 
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask ABM..."
          disabled={isLoading}
        />
        <button className="send-btn" onClick={handleSend} disabled={!inputValue.trim() || isLoading}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
