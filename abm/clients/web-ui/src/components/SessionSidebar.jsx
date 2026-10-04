import { Plus, MessageCircle } from 'lucide-react';
import './SessionSidebar.css';

export default function SessionSidebar({ sessions, currentSessionId, onSelectSession, onNewChat }) {
  return (
    <div className="session-sidebar glass-panel">
      <button className="new-chat-btn" onClick={onNewChat}>
        <Plus size={18} />
        New Chat
      </button>
      
      <div className="session-list">
        {sessions.length === 0 && (
          <div className="no-sessions">No previous sessions</div>
        )}
        {sessions.map(session => (
          <div 
            key={session.id}
            className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
            onClick={() => onSelectSession(session.id)}
          >
            <MessageCircle size={16} className="session-icon" />
            <div className="session-info">
              <div className="session-title">
                {session.title || `Session ${session.id.substring(0, 8)}`}
              </div>
              <div className="session-date">
                {new Date(session.updated_at * 1000).toLocaleString(undefined, { 
                  month: 'short', 
                  day: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit'
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
