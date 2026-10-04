import unittest
import json
from unittest.mock import MagicMock, patch
from io import BytesIO

from abm.clients.web.main import ABMWebAPIHandler

class MockRequest:
    def makefile(self, *args, **kwargs):
        return BytesIO(b"")

class TestWebAPIHandler(unittest.TestCase):
    @patch('abm.clients.web.main.registry')
    @patch('abm.clients.web.main.answerQuestion')
    def test_handle_ask_routes_to_answerQuestion(self, mock_answerQuestion, mock_registry):
        # Setup mock return value
        mock_result = MagicMock()
        mock_result.question = "what is ABM?"
        mock_result.department = "software_engineering"
        mock_result.confidence = "high"
        mock_result.synthesis = "A cognitive OS."
        mock_result.fallback_used = False
        mock_result.degraded = False
        mock_result.hits = [{"text": "context", "collection": "abm_cognitive_identity", "metadata": {}}]
        mock_answerQuestion.return_value = mock_result

        # Simulate the HTTP request payload
        payload = json.dumps({"question": "what is ABM?"}).encode('utf-8')
        
        handler = ABMWebAPIHandler(MockRequest(), ("127.0.0.1", 8080), MagicMock())
        handler.rfile = BytesIO(payload)
        handler.wfile = BytesIO()
        handler.headers = {'Content-Length': str(len(payload))}
        handler.path = '/api/ask'
        handler.requestline = 'POST /api/ask HTTP/1.1'
        handler.request_version = 'HTTP/1.1'

        # Execute
        handler.do_POST()

        # Assert correct capability was called
        mock_answerQuestion.assert_called_once_with("what is ABM?", registry=mock_registry, history=None)

        # Assert correct response
        response_bytes = handler.wfile.getvalue()
        # The HTTP status line and headers are written to wfile, followed by the JSON body.
        # Find the double CRLF separating headers and body
        body_start = response_bytes.find(b'\r\n\r\n') + 4
        body = json.loads(response_bytes[body_start:].decode('utf-8'))
        
        self.assertEqual(body["synthesis"], "A cognitive OS.")
        self.assertEqual(body["hits"][0]["collection"], "abm_cognitive_identity")

    @patch('abm.clients.web.main.registry')
    @patch('abm.clients.web.main.ingestDocument')
    def test_handle_ingest_routes_to_ingestDocument(self, mock_ingestDocument, mock_registry):
        mock_result = MagicMock()
        mock_result.path = "/tmp/test.txt"
        mock_result.degraded = False
        mock_result.results = [{"status": "ok", "collection": "abm_technical_mastery", "reason": "", "doc_ids": ["123"]}]
        mock_ingestDocument.return_value = mock_result

        # Create a mock multipart form payload
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"Hello World\r\n"
            f"--{boundary}--\r\n"
        ).encode('utf-8')

        handler = ABMWebAPIHandler(MockRequest(), ("127.0.0.1", 8080), MagicMock())
        handler.rfile = BytesIO(payload)
        handler.wfile = BytesIO()
        handler.headers = {
            'Content-Length': str(len(payload)),
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        }
        handler.path = '/api/ingest'
        handler.requestline = 'POST /api/ingest HTTP/1.1'
        handler.request_version = 'HTTP/1.1'

        # Execute
        handler.do_POST()

        # Assert correct capability was called
        mock_ingestDocument.assert_called_once()
        # The first argument should be a filepath, let's just check it was passed
        passed_file_path = mock_ingestDocument.call_args[0][0]
        self.assertTrue(passed_file_path.endswith(".txt"))
        
        # Verify response body
        response_bytes = handler.wfile.getvalue()
        body_start = response_bytes.find(b'\r\n\r\n') + 4
        body = json.loads(response_bytes[body_start:].decode('utf-8'))
        
        self.assertEqual(body["results"][0]["status"], "ok")

if __name__ == "__main__":
    unittest.main()
