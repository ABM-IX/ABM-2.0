import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, Folder, File, CheckCircle2, XCircle, Loader2, FolderSearch } from 'lucide-react';
import './FileUpload.css';

export default function FileUpload() {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [pathInput, setPathInput] = useState('');
  
  const fileInputRef = useRef(null);

  const processFiles = async (files) => {
    if (!files || files.length === 0) return;
    
    setIsUploading(true);
    setUploadResult(null);

    let successCount = 0;
    let errors = [];

    // Upload each file one by one using multipart/form-data
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      const filename = file.webkitRelativePath || file.name;
      formData.append('file', file, filename);

      try {
        const response = await fetch('http://localhost:8080/api/ingest', {
          method: 'POST',
          body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
          successCount++;
        } else {
          errors.push(result.error || 'Unknown error');
        }
      } catch (error) {
        console.error(error);
        errors.push(error.message);
      }
    }

    setIsUploading(false);
    
    if (errors.length === 0) {
      setUploadResult({ 
        success: true, 
        message: 'Ingestion completed successfully',
        details: `Processed ${successCount} file(s)`
      });
    } else {
      setUploadResult({ 
        success: false, 
        message: 'Ingestion failed for some files', 
        details: `Successfully processed ${successCount} file(s)`,
        errors: errors
      });
    }
  };

  const handleFileChange = (e) => {
    processFiles(e.target.files);
    e.target.value = null;
  };

  const handleBrowseFolder = async () => {
    try {
      const response = await fetch('http://localhost:8080/api/browse');
      const data = await response.json();
      if (data.path) {
        setPathInput(data.path);
      }
    } catch (error) {
      console.error('Failed to open native browser:', error);
    }
  };

  const handlePathUpload = async () => {
    if (!pathInput.trim()) return;
    
    setIsUploading(true);
    setUploadResult(null);

    try {
      const response = await fetch('http://localhost:8080/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathInput })
      });
      
      const result = await response.json();
      
      if (response.ok) {
        setUploadResult({ 
          success: true, 
          message: 'Path ingested successfully',
          details: result.results?.length ? `Processed path with ${result.results.length} result(s)` : null
        });
        setPathInput('');
      } else {
        setUploadResult({ 
          success: false, 
          message: 'Ingestion failed', 
          errors: result.errors || [result.error || 'Unknown error']
        });
      }
    } catch (error) {
      console.error(error);
      setUploadResult({ 
        success: false, 
        message: 'Network error', 
        errors: [error.message]
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="file-upload glass-panel">
      <div className="upload-header">
        <Folder size={18} className="header-icon" />
        <h3>Ingest Memory</h3>
      </div>
      
      <div className="upload-actions">
        <input 
          type="file" 
          ref={fileInputRef} 
          style={{ display: 'none' }} 
          multiple
          onChange={handleFileChange}
        />

        <button 
          className="upload-btn" 
          onClick={() => fileInputRef.current.click()}
          disabled={isUploading}
        >
          <File size={16} />
          Upload File(s)
        </button>

        <div className="path-ingest-container">
          <div className="path-input-group">
            <input 
              type="text" 
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              placeholder="Local folder path"
              className="path-input"
              disabled={isUploading}
            />
            <button 
              className="browse-btn" 
              onClick={handleBrowseFolder}
              disabled={isUploading}
              title="Browse native folder"
            >
              <FolderSearch size={16} />
            </button>
          </div>
          <button 
            className="upload-btn folder-btn" 
            onClick={handlePathUpload}
            disabled={!pathInput.trim() || isUploading}
          >
            {isUploading ? 'Ingesting...' : 'Ingest Path'}
          </button>
        </div>
      </div>
      
      <AnimatePresence>
        {isUploading && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="upload-progress"
          >
            <Loader2 className="spinner" size={16} />
            <p>Ingesting...</p>
          </motion.div>
        )}

        {uploadResult && !isUploading && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className={`upload-result ${uploadResult.success ? 'success' : 'error'}`}
          >
            <div className="result-header">
              {uploadResult.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              <p>{uploadResult.message}</p>
            </div>
            
            {uploadResult.details && (
              <p className="result-details">{uploadResult.details}</p>
            )}
            
            {uploadResult.errors && uploadResult.errors.length > 0 && (
              <ul>
                {uploadResult.errors.slice(0, 5).map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
                {uploadResult.errors.length > 5 && (
                  <li>...and {uploadResult.errors.length - 5} more errors</li>
                )}
              </ul>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
