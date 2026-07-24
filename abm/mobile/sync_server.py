"""
abm/mobile/sync_server.py
=========================
HTTP sync server for receiving ambient telemetry from the Flutter mobile node.
Uses AES-256-GCM for cross-node sync payload decryption.
"""
import base64
import json
import logging
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from abm.api.capabilities import ingestAmbientEvent
from abm.api.core.registry import ServiceRegistry
from abm.mobile.event_models import AmbientEvent

logger = logging.getLogger(__name__)

CONFIG_FILE = ".sync_pairing.json"
PROTOCOL_VERSION = 1
ALGORITHM = "AES-256-GCM"


class SyncServerHandler(BaseHTTPRequestHandler):
    registry: ServiceRegistry
    pairing_config: dict[str, str]

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json(400, {"error": "Empty body"})
            return

        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if self.path == "/api/sync/handshake":
            self.handle_handshake(payload)
        elif self.path == "/api/sync/payload":
            self.handle_payload(payload)
        else:
            self._send_json(404, {"error": "Not Found"})

    def handle_handshake(self, payload: dict[str, Any]) -> None:
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            self._send_json(400, {"error": "Unsupported protocol version"})
            return

        expected_key_id = self.pairing_config.get("key_id")
        if not expected_key_id:
            logger.warning("401 Unauthorized (Handshake): Pairing config missing key_id (key not found).")
            self._send_json(401, {"error": "Unpaired or invalid key_id"})
            return
        if payload.get("key_id") != expected_key_id:
            logger.warning("401 Unauthorized (Handshake): Key ID mismatch. Expected: %s, Received: %s", expected_key_id, payload.get("key_id"))
            self._send_json(401, {"error": "Unpaired or invalid key_id"})
            return

        self._send_json(200, {
            "status": "ok",
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": ["ambient_event_ingest", "state_snapshot", "encrypted_payload_v1"]
        })

    def handle_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            self._send_json(400, {"error": "Unsupported protocol version"})
            return

        expected_key_id = self.pairing_config.get("key_id")
        if not expected_key_id:
            logger.warning("401 Unauthorized (Payload): Pairing config missing key_id (key not found).")
            self._send_json(401, {"error": "Unpaired or invalid key_id"})
            return
        if payload.get("key_id") != expected_key_id:
            logger.warning("401 Unauthorized (Payload): Key ID mismatch. Expected: %s, Received: %s", expected_key_id, payload.get("key_id"))
            self._send_json(401, {"error": "Unpaired or invalid key_id"})
            return

        if payload.get("algorithm") != ALGORITHM:
            self._send_json(400, {"error": "Unsupported algorithm"})
            return

        key_b64 = self.pairing_config.get("key", "")
        try:
            key_bytes = base64.b64decode(key_b64)
            nonce = base64.b64decode(payload["nonce"])
            ciphertext = base64.b64decode(payload["ciphertext"])
            mac = base64.b64decode(payload["mac"])
        except Exception:
            self._send_json(400, {"error": "Base64 decode failed"})
            return

        aad_str = "|".join([
            "abm-sync",
            str(payload.get("protocol_version")),
            payload.get("key_id", ""),
            payload.get("node_id", ""),
            str(payload.get("created_at_epoch", "")),
            payload.get("content_type", "")
        ])
        aad_bytes = aad_str.encode("utf-8")

        try:
            aesgcm = AESGCM(key_bytes)
            # cryptography expects ciphertext + mac combined
            decrypted_bytes = aesgcm.decrypt(nonce, ciphertext + mac, aad_bytes)
            decrypted_json = json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as e:
            logger.warning("401 Unauthorized (Payload): Decryption or MAC failure. Error: %s", e)
            self._send_json(401, {"error": "Decryption failed"})
            return

        # Parse AmbientEvent
        try:
            event = AmbientEvent(
                source_kind=decrypted_json["source_kind"],
                active_repository=decrypted_json["active_repository"],
                source_path=decrypted_json["source_path"],
                text=decrypted_json["text"],
                epoch_timestamp=decrypted_json.get("epoch_timestamp", int(time.time())),
                device_source="dynamic_mobile_node",
            )
            if "extra" in decrypted_json:
                event.extra = decrypted_json["extra"]
        except KeyError as e:
            self._send_json(400, {"error": f"Missing required field: {e}"})
            return
        except (TypeError, ValueError) as e:
            self._send_json(400, {"error": f"Invalid AmbientEvent payload: {e}"})
            return

        result = ingestAmbientEvent(event, registry=self.registry)

        if result.degraded:
            self._send_json(500, {"error": "Ambient manager failed to ingest"})
            return

        self._send_json(200, {
            "status": result.status,
            "doc_id": result.doc_id,
            "reason": result.reason,
            "housekeeper_ran": result.housekeeper_ran
        })


def run_server(host: str, port: int, registry: ServiceRegistry, pairing_config_path: str) -> None:
    if not os.path.exists(pairing_config_path):
        logger.warning("Pairing config not found at %s. Please run python -m abm.mobile.pair.", pairing_config_path)
        pairing_config = {}
    else:
        with open(pairing_config_path, "r", encoding="utf-8") as f:
            pairing_config = json.load(f)

    SyncServerHandler.registry = registry
    SyncServerHandler.pairing_config = pairing_config

    server = HTTPServer((host, port), SyncServerHandler)
    logger.info("Starting sync server on %s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    registry = ServiceRegistry()
    try:
        registry.boot()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        config_path = os.path.join(project_root, CONFIG_FILE)
        run_server("0.0.0.0", 8765, registry, config_path)
    except KeyboardInterrupt:
        logger.info("Shutting down sync server...")
    finally:
        registry.shutdown()
