import { useState } from 'react';
import { motion } from 'framer-motion';
import { FileEdit, Check, AlertCircle } from 'lucide-react';
import './EditPanel.css';

export default function EditPanel() {
  const [targetFile, setTargetFile] = useState('');
  const [instruction, setInstruction] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [error, setError] = useState(null);
  
  const handleSimulate = async () => {
    if (!targetFile.trim() || !instruction.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const response = await fetch('http://localhost:8080/api/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_file: targetFile,
          instruction: instruction,
          simulate_only: true
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'Failed to generate edit proposal');
      }
      
      setProposal(data);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };
  
  const handleApply = async () => {
    if (!proposal || !targetFile || !instruction) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const response = await fetch('http://localhost:8080/api/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_file: targetFile,
          instruction: instruction,
          simulate_only: false
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'Failed to apply edit');
      }
      
      setProposal({ ...data, applied: true });
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };
  
  return (
    <div className="edit-panel">
      <div className="edit-header">
        <FileEdit className="header-icon" />
        <h3>Edit Sandbox</h3>
      </div>
      
      <div className="edit-form">
        <input 
          type="text" 
          className="edit-input" 
          placeholder="Target file path (e.g., abm/main.py)"
          value={targetFile}
          onChange={(e) => setTargetFile(e.target.value)}
          disabled={isProcessing}
        />
        
        <textarea 
          className="edit-textarea" 
          placeholder="Instruction (e.g., Add a retry block around the network call)"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          disabled={isProcessing}
        />
        
        <button 
          className="action-btn"
          onClick={handleSimulate}
          disabled={!targetFile.trim() || !instruction.trim() || isProcessing}
        >
          {isProcessing && !proposal?.applied ? 'Simulating...' : 'Generate Proposal'}
        </button>
      </div>
      
      {error && (
        <motion.div 
          className="edit-message error"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <AlertCircle size={16} />
          {error}
        </motion.div>
      )}
      
      {proposal && (
        <motion.div 
          className="proposal-container"
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
        >
          <div className="proposal-header">
            <h4>Generated Diff</h4>
            {proposal.degraded && (
              <span className="degraded-badge">Degraded Execution</span>
            )}
          </div>
          
          <pre className="diff-viewer">
            {proposal.diff || 'No changes.'}
          </pre>
          
          {proposal.applied ? (
            <div className="edit-message success">
              <Check size={16} />
              Edit applied successfully.
            </div>
          ) : (
            <button 
              className="action-btn apply-btn"
              onClick={handleApply}
              disabled={isProcessing}
            >
              {isProcessing ? 'Applying...' : 'Apply Edit'}
            </button>
          )}
        </motion.div>
      )}
    </div>
  );
}
