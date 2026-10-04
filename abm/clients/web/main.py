import json
import logging

import tempfile
import os
import time
import uuid
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.api.capabilities import answerQuestion, ingestDocument, proposeEdit, applyEdit

logger = logging.getLogger(__name__)

registry: ServiceRegistry | None = None

class SessionManager:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = os.path.join(os.path.dirname(__file__), "sessions.json")
        else:
            self.db_path = db_path
            
    def _load(self):
        if not os.path.exists(self.db_path):
            return {}
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
            
    def _save(self, data):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
    def get_sessions(self):
        data = self._load()
        sessions = []
        for sid, sdata in data.items():
            sessions.append({
                "id": sid,
                "title": sdata.get("title", "New Chat"),
                "timestamp": sdata.get("timestamp", 0)
            })
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        return sessions
        
    def get_session(self, session_id):
        return self._load().get(session_id)
        
    def add_message(self, session_id, message, title=None):
        data = self._load()
        if session_id not in data:
            data[session_id] = {
                "title": title or "New Chat",
                "timestamp": time.time(),
                "messages": []
            }
        # Update timestamp on new message
        data[session_id]["timestamp"] = time.time()
        if title and data[session_id]["title"] == "New Chat":
            data[session_id]["title"] = title
            
        data[session_id]["messages"].append(message)
        self._save(data)

session_manager = SessionManager()

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class ABMWebAPIHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/sessions":
            self.handle_get_sessions()
        elif parsed_url.path == "/api/session":
            qs = parse_qs(parsed_url.query)
            session_id = qs.get("id", [None])[0]
            self.handle_get_session(session_id)
        elif parsed_url.path == "/api/browse":
            self.handle_browse()
        elif not parsed_url.path.startswith("/api/"):
            self.serve_static_file(parsed_url.path)
        else:
            self.send_error(404, "Not Found")
            
    def serve_static_file(self, path):
        if path == "/" or path == "":
            path = "/index.html"
            
        # Normalize path and prevent directory traversal (strip slashes to make relative)
        path = path.lstrip("/\\")
        path = os.path.normpath(path)
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        dist_dir = os.path.join(project_root, "abm", "clients", "web-ui", "dist")
        file_path = os.path.join(dist_dir, path)
        
        if not os.path.abspath(file_path).startswith(os.path.abspath(dist_dir)):
            self.send_error(403, "Forbidden")
            return
            
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            # Fallback to index.html for SPA routing
            file_path = os.path.join(dist_dir, "index.html")
            if not os.path.exists(file_path):
                self.send_error(404, "Not Found")
                return
                
        # Guess mime type
        ext = os.path.splitext(file_path)[1].lower()
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml"
        }.get(ext, "application/octet-stream")
        
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Internal Server Error: {e}")
            
    def handle_get_sessions(self):
        sessions = session_manager.get_sessions()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"sessions": sessions}).encode('utf-8'))
        
    def handle_get_session(self, session_id):
        if not session_id:
            self.send_error(400, "Missing session id")
            return
        session_data = session_manager.get_session(session_id)
        if not session_data:
            self.send_error(404, "Session not found")
            return
            
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(session_data).encode('utf-8'))

    def handle_browse(self):
        import subprocess
        import sys
        script = (
            "import tkinter as tk\n"
            "from tkinter import filedialog\n"
            "root = tk.Tk()\n"
            "root.withdraw()\n"
            "root.attributes('-topmost', True)\n"
            "path = filedialog.askdirectory()\n"
            "root.destroy()\n"
            "print(path)\n"
        )
        try:
            output = subprocess.check_output([sys.executable, "-c", script], text=True, stderr=subprocess.STDOUT)
            path = output.strip()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error opening folder dialog: {e}")
            path = ""
            
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"path": path}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/ask":
            self.handle_ask()
        elif self.path == "/api/ingest":
            self.handle_ingest()
        elif self.path == "/api/edit/propose":
            self.handle_edit_propose()
        elif self.path == "/api/edit/apply":
            self.handle_edit_apply()
        else:
            self.send_error(404, "Not Found")

    def handle_ask(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_error(400, "Empty Body")
            return
            
        post_data = self.rfile.read(content_length)
        try:
            req = json.loads(post_data.decode('utf-8'))
            question = req.get("question", "")
            session_id = req.get("session_id", None)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
            
        if not registry:
            self.send_error(500, "Service Registry not booted")
            return
            
        history = None
        if session_id:
            session_data = session_manager.get_session(session_id)
            if session_data and "messages" in session_data:
                # get last 6 messages
                last_messages = session_data["messages"][-6:]
                history = [{"role": m.get("role"), "content": m.get("text")} for m in last_messages if m.get("role") and m.get("text")]
            
        result = answerQuestion(question, registry=registry, history=history)
        
        if not session_id:
            session_id = str(uuid.uuid4())
            title = " ".join(question.split()[:4]) + "..." if question else "New Chat"
        else:
            title = None
            
        # Serialize the response
        response = {
            "session_id": session_id,
            "question": result.question,
            "department": result.department,
            "confidence": result.confidence,
            "synthesis": result.synthesis,
            "fallback_used": result.fallback_used,
            "degraded": result.degraded,
            "hits": [
                {
                    "text": h.get("text", ""),
                    "collection": h.get("collection", ""),
                    "metadata": h.get("metadata", {})
                }
                for h in result.hits
            ]
        }
        
        # Save to history
        session_manager.add_message(session_id, {
            "id": int(time.time() * 1000),
            "role": "user",
            "text": question
        }, title=title)
        
        session_manager.add_message(session_id, {
            "id": int(time.time() * 1000) + 1,
            "role": "agent",
            "text": response["synthesis"],
            "sources": response["hits"],
            "metadata": {"department": response["department"], "confidence": response["confidence"]}
        })
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_ingest(self):
        if not registry:
            self.send_error(500, "Service Registry not booted")
            return
            
        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_error(400, "Empty Body")
            return
            
        post_data = self.rfile.read(content_length)
        
        # Support for simple JSON folder-path ingestion
        if content_type.startswith('application/json'):
            try:
                req = json.loads(post_data.decode('utf-8'))
                path = req.get("path")
                if not path:
                    self.send_error(400, "Path missing in JSON")
                    return
                
                result = ingestDocument(path, registry=registry)
                self._send_ingest_response(result)
                return
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

        # Original multipart file upload logic
        if 'multipart/form-data' not in content_type:
            self.send_error(400, "Must be multipart/form-data or application/json")
            return
            
        import email
        from email.policy import default
        
        msg_bytes = f"Content-Type: {content_type}\r\n\r\n".encode('utf-8') + post_data
        msg = email.message_from_bytes(msg_bytes, policy=default)
        
        filename = None
        file_content = None
        
        if msg.is_multipart():
            for part in msg.iter_parts():
                if part.get_filename():
                    filename = part.get_filename()
                    file_content = part.get_payload(decode=True)
                    break
        
        if not file_content:
            self.send_error(400, "No file uploaded")
            return
            
        if not filename:
            filename = "uploaded_file.txt"
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_f:
            temp_f.write(file_content)
            temp_path = temp_f.name
            
        try:
            result = ingestDocument(temp_path, registry=registry)
            self._send_ingest_response(result)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.warning(f"Could not remove temp file {temp_path}: {e}")

    def _send_ingest_response(self, result):
        response = {
            "path": result.path,
            "degraded": result.degraded,
            "results": [
                {
                    "status": r.get("status"),
                    "collection": r.get("collection"),
                    "reason": r.get("reason"),
                    "doc_ids": r.get("doc_ids")
                } for r in result.results
            ]
        }
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_edit_propose(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        req = json.loads(post_data.decode('utf-8'))
        
        target_file = req.get("target_file")
        instruction = req.get("instruction")
        
        result = proposeEdit(target_file, instruction, registry=registry)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "target_file": result.target_file,
            "diff": result.diff,
            "new_content": result.new_content,
            "verified": result.verified,
            "degraded": result.degraded
        }).encode('utf-8'))
        
    def handle_edit_apply(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        req = json.loads(post_data.decode('utf-8'))
        
        target_file = req.get("target_file")
        new_content = req.get("new_content")
        
        applyEdit(target_file, new_content, registry=registry)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    global registry
    config = APIConfig(model_gateway_provider="groq")
    registry = ServiceRegistry(config)
    
    logger.info("Booting Service Registry...")
    registry.boot()
    
    port = 8080
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, ABMWebAPIHandler)
    
    logger.info(f"Starting ABM Web API on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        httpd.server_close()
        registry.shutdown()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
