import base64
import json
import os
import time
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from abm.mobile.sync_server import SyncServerHandler

@pytest.fixture
def dummy_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)

@pytest.fixture
def dummy_key_id() -> str:
    return "test-key-id"

@pytest.fixture
def pairing_config(dummy_key, dummy_key_id) -> dict[str, str]:
    return {
        "key": base64.b64encode(dummy_key).decode("utf-8"),
        "key_id": dummy_key_id
    }

def create_mock_handler(pairing_config):
    handler = MagicMock(spec=SyncServerHandler)
    handler.pairing_config = pairing_config
    handler.registry = MagicMock()
    
    # Capture the JSON sent back
    handler.sent_json = {}
    handler.sent_status = 0
    
    def mock_send_json(status, data):
        handler.sent_status = status
        handler.sent_json = data
        
    handler._send_json = mock_send_json
    # Bind the methods
    handler.handle_handshake = SyncServerHandler.handle_handshake.__get__(handler, SyncServerHandler)
    handler.handle_payload = SyncServerHandler.handle_payload.__get__(handler, SyncServerHandler)
    return handler

def make_dart_encrypted_payload(key_bytes, key_id, json_payload):
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12)
    epoch = int(time.time())
    
    aad_str = "|".join([
        "abm-sync",
        "1", # protocol_version
        key_id,
        "test-node",
        str(epoch),
        "application/json"
    ])
    aad_bytes = aad_str.encode("utf-8")
    
    plaintext = json.dumps(json_payload).encode("utf-8")
    encrypted_with_tag = aesgcm.encrypt(nonce, plaintext, aad_bytes)
    
    ciphertext = encrypted_with_tag[:-16]
    mac = encrypted_with_tag[-16:]
    
    return {
        "protocol_version": 1,
        "key_id": key_id,
        "algorithm": "AES-256-GCM",
        "node_id": "test-node",
        "created_at_epoch": epoch,
        "content_type": "application/json",
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "mac": base64.b64encode(mac).decode("utf-8"),
    }


class TestDesktopSyncServerGate:
    """Gate: Cross-node encrypted payload handling matching Dart AES-GCM format."""

    def test_handshake_success(self, pairing_config):
        handler = create_mock_handler(pairing_config)
        handler.handle_handshake({
            "protocol_version": 1,
            "key_id": pairing_config["key_id"],
            "node_id": "test-node",
            "algorithm": "AES-256-GCM",
            "created_at_epoch": int(time.time()),
            "capabilities": []
        })
        assert handler.sent_status == 200
        assert handler.sent_json["status"] == "ok"
        assert "encrypted_payload_v1" in handler.sent_json["capabilities"]
        
    def test_payload_decryption_success(self, dummy_key, dummy_key_id, pairing_config):
        handler = create_mock_handler(pairing_config)
        
        mock_result = MagicMock()
        mock_result.degraded = False
        mock_result.status = "ok"
        mock_result.doc_id = "doc-123"
        mock_result.reason = ""
        mock_result.housekeeper_ran = True
        
        import abm.mobile.sync_server
        original_ingest = abm.mobile.sync_server.ingestAmbientEvent
        try:
            abm.mobile.sync_server.ingestAmbientEvent = MagicMock(return_value=mock_result)
            
            event_json = {
                "source_kind": "git_commit",
                "active_repository": "test_repo",
                "source_path": "/path/to/repo",
                "text": "test commit",
                "epoch_timestamp": 1234567890,
                "device_source": "dynamic_mobile_node",
                "extra": {}
            }
            
            payload = make_dart_encrypted_payload(dummy_key, dummy_key_id, event_json)
            handler.handle_payload(payload)
            
            assert handler.sent_status == 200
            assert handler.sent_json["status"] == "ok"
            assert handler.sent_json["doc_id"] == "doc-123"
            
            abm.mobile.sync_server.ingestAmbientEvent.assert_called_once()
            called_event = abm.mobile.sync_server.ingestAmbientEvent.call_args[0][0]
            assert called_event.text == "test commit"
        finally:
            abm.mobile.sync_server.ingestAmbientEvent = original_ingest
            
    def test_payload_wrong_key_rejected(self, dummy_key_id, pairing_config):
        handler = create_mock_handler(pairing_config)
        wrong_key = AESGCM.generate_key(bit_length=256)
        
        event_json = {
            "source_kind": "git_commit",
            "active_repository": "test_repo",
            "source_path": "/path/to/repo",
            "text": "test commit",
            "epoch_timestamp": 1234567890,
            "device_source": "dynamic_mobile_node",
            "extra": {}
        }
        
        payload = make_dart_encrypted_payload(wrong_key, dummy_key_id, event_json)
        handler.handle_payload(payload)
        
        assert handler.sent_status == 401
        assert handler.sent_json["error"] == "Decryption failed"
        
    def test_payload_wrong_key_id_rejected(self, dummy_key, pairing_config):
        handler = create_mock_handler(pairing_config)
        
        event_json = {
            "source_kind": "git_commit",
            "active_repository": "test_repo",
            "source_path": "/path/to/repo",
            "text": "test commit",
            "epoch_timestamp": 1234567890,
            "device_source": "dynamic_mobile_node",
            "extra": {}
        }
        
        payload = make_dart_encrypted_payload(dummy_key, "different-key-id", event_json)
        handler.handle_payload(payload)
        
        assert handler.sent_status == 401
        assert handler.sent_json["error"] == "Unpaired or invalid key_id"

class TestSyncPairingGitignoreGate:
    def test_sync_pairing_json_is_gitignored(self):
        import subprocess
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        test_file = os.path.join(project_root, ".sync_pairing.json")
        
        # Ensure the .gitignore file exists before running check-ignore
        gitignore_path = os.path.join(project_root, ".gitignore")
        assert os.path.exists(gitignore_path), ".gitignore is missing"
        
        with open(gitignore_path, "r") as f:
            content = f.read()
            assert ".sync_pairing.json" in content
            
        if not os.path.exists(test_file):
            with open(test_file, "w") as f:
                f.write("{}")
                
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", ".sync_pairing.json"],
                cwd=project_root,
                check=False
            )
            assert result.returncode == 0, ".sync_pairing.json must be covered by .gitignore"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
