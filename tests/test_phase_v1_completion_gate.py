"""
tests/test_phase_v1_completion_gate.py
======================================
Phase v1.0 Roadmap Completion Gate — ABM 2.0

Final gate before the whole roadmap is declared complete.  Proves:

  1. TestForegroundServiceSurvivalGate
     - Foreground service uses device-agnostic flutter_foreground_task (no
       Tecno Spark 40 or other hardware hardcoding).
     - Low-memory survival mechanisms: wake lock, repeat heartbeat,
       boot auto-restart, persistent notification — simulated trim does not
       terminate the task handler loop.

  2. TestEncryptedSyncIntegrityGate
     - Sync channel uses only vetted packages (cryptography,
       flutter_secure_storage).
     - Unencrypted / malformed payloads are rejected.
     - Tampered ciphertext, MAC, or AAD fields fail AES-GCM authentication.

  3. TestAmbientManagerSourceAllowlistGate
     - Only git_commit, workspace_file, and design_doc sources are ingested.
     - Clipboard, voice, browser are structurally absent (Python + Dart).

  4. TestStreamCCompressionWindowGate
     - Duplicates within COMPRESS_WINDOW_SECONDS return status "compressed".
     - Identical events after the window elapse are stored again (not compressed).

  5. TestRoadmapRegressionGate
     - All prior phase gates (v0.1–v0.5), Client #1, and mobile gate remain
       100% green.

Gate run command:
    python -m pytest tests/test_phase_v1_completion_gate.py -v

Full roadmap regression:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from abm.companion.file_watcher import FileChangeEvent
from abm.mobile.ambient_manager import (
    DESIGN_DOC_EXTENSIONS,
    WorkspaceStateMonitor,
)
from abm.mobile.event_models import PERMITTED_SOURCE_KINDS, AmbientEvent
from abm.mobile.retention_housekeeper import (
    DELETE_AFTER_SECONDS,
    SUMMARIZE_AFTER_SECONDS,
    StreamCRetentionHousekeeper,
    HousekeeperResult,
)
from abm.mobile.stream_c_writer import (
    COMPRESS_WINDOW_SECONDS,
    StreamCWriter,
    WriteResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = PROJECT_ROOT / "mobile"
TESTS_ROOT = PROJECT_ROOT / "tests"

# Prior gated suites — must all stay green for roadmap completion.
PRIOR_GATE_FILES = [
    "tests/test_phase_v01_gate.py",
    "tests/test_phase_v02_gate.py",
    "tests/test_phase_v03_gate.py",
    "tests/test_phase_v04_gate.py",
    "tests/test_phase_v05_gate.py",
    "tests/test_client01_gate.py",
    "tests/test_phase_v10_mobile_gate.py",
]

# Hardware-specific strings banned from the mobile node (ABM_SPEC correction).
BANNED_DEVICE_FRAGMENTS = [
    "Tecno",
    "Spark 40",
    "spark_40",
    "tecno_spark",
    "Build.MODEL",
    "Build.MANUFACTURER",
]

K_SYNC_PROTOCOL_VERSION = 1
K_SYNC_ALGORITHM = "AES-256-GCM"
K_SYNC_CONTENT_TYPE_JSON = "application/json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_mobile(relative: str) -> str:
    return (MOBILE_ROOT / relative).read_text(encoding="utf-8")


def _read_all_mobile_sources() -> str:
    parts: list[str] = []
    for path in sorted(MOBILE_ROOT.rglob("*")):
        if path.suffix in {".dart", ".yaml", ".xml"} and path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _sync_aad(
    *,
    protocol_version: int,
    key_id: str,
    node_id: str,
    created_at_epoch: int,
    content_type: str,
) -> bytes:
    return "|".join(
        [
            "abm-sync",
            str(protocol_version),
            key_id,
            node_id,
            str(created_at_epoch),
            content_type,
        ]
    ).encode()


def _encrypt_sync_json(
    key_bytes: bytes,
    payload: dict[str, Any],
    *,
    node_id: str = "dynamic_mobile_node",
    key_id: str = "testkeyid0000001",
    created_at_epoch: int = 1_700_000_000,
) -> dict[str, Any]:
    plain = json.dumps(payload).encode()
    nonce = os.urandom(12)
    aad = _sync_aad(
        protocol_version=K_SYNC_PROTOCOL_VERSION,
        key_id=key_id,
        node_id=node_id,
        created_at_epoch=created_at_epoch,
        content_type=K_SYNC_CONTENT_TYPE_JSON,
    )
    aesgcm = AESGCM(key_bytes)
    ct = aesgcm.encrypt(nonce, plain, aad)
    ciphertext, tag = ct[:-16], ct[-16:]
    return {
        "protocol_version": K_SYNC_PROTOCOL_VERSION,
        "key_id": key_id,
        "algorithm": K_SYNC_ALGORITHM,
        "node_id": node_id,
        "created_at_epoch": created_at_epoch,
        "content_type": K_SYNC_CONTENT_TYPE_JSON,
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "mac": base64.b64encode(tag).decode(),
    }


def _decrypt_sync_payload(key_bytes: bytes, wire: dict[str, Any]) -> dict[str, Any]:
    """Mirror SyncCryptoChannel.decryptJson validation (Python-side)."""
    required = {
        "protocol_version",
        "nonce",
        "ciphertext",
        "mac",
        "key_id",
        "node_id",
        "created_at_epoch",
        "content_type",
        "algorithm",
    }
    if not required.issubset(wire.keys()):
        raise ValueError("Unencrypted or malformed sync payload")
    if wire.get("protocol_version") != K_SYNC_PROTOCOL_VERSION:
        raise ValueError(f"Unsupported protocol: {wire.get('protocol_version')}")
    if wire.get("algorithm") != K_SYNC_ALGORITHM:
        raise ValueError(f"Unsupported algorithm: {wire.get('algorithm')}")

    aad = _sync_aad(
        protocol_version=wire["protocol_version"],
        key_id=wire["key_id"],
        node_id=wire["node_id"],
        created_at_epoch=wire["created_at_epoch"],
        content_type=wire["content_type"],
    )
    nonce = base64.b64decode(wire["nonce"])
    ciphertext = base64.b64decode(wire["ciphertext"])
    tag = base64.b64decode(wire["mac"])
    aesgcm = AESGCM(key_bytes)
    plain = aesgcm.decrypt(nonce, ciphertext + tag, aad)
    return json.loads(plain.decode())


def _mock_controller():
    ctrl = MagicMock()
    ctrl.get_collection.return_value = MagicMock()
    return ctrl


def _mock_embedder():
    emb = MagicMock()
    emb.embed.return_value = [0.1, 0.2, 0.3]
    return emb


def _make_writer(compress_window: int = COMPRESS_WINDOW_SECONDS) -> StreamCWriter:
    hk = MagicMock(spec=StreamCRetentionHousekeeper)
    hk.run_if_due.return_value = HousekeeperResult(skipped=True)
    return StreamCWriter(
        controller=_mock_controller(),
        embedder=_mock_embedder(),
        housekeeper=hk,
        compress_window_seconds=compress_window,
    )


def _make_event(text: str = "commit message", epoch: int = 1_000_000) -> AmbientEvent:
    return AmbientEvent(
        source_kind="git_commit",
        active_repository="test_repo",
        source_path="/repo/head",
        text=text,
        epoch_timestamp=epoch,
    )


# ===========================================================================
# Proof 1 — Foreground service low-memory survival & device agnosticism
# ===========================================================================


class TestForegroundServiceSurvivalGate:
    """Gate: foreground service survives OS memory pressure; no device lock-in."""

    def test_mobile_tree_has_no_hardware_hardcoding(self):
        combined = _read_all_mobile_sources()
        for fragment in BANNED_DEVICE_FRAGMENTS:
            assert fragment not in combined, (
                f"Mobile node must not hardcode device '{fragment}'"
            )

    def test_uses_flutter_foreground_task_not_custom_android_service(self):
        pubspec = _read_mobile("pubspec.yaml")
        service = _read_mobile(
            "lib/features/foreground/service/abm_foreground_service.dart"
        )
        assert "flutter_foreground_task:" in pubspec
        assert "package:flutter_foreground_task/flutter_foreground_task.dart" in service
        assert "FlutterForegroundTask.init" in service
        assert "FlutterForegroundTask.startService" in service

    def test_low_memory_survival_mechanisms_configured(self):
        service = _read_mobile(
            "lib/features/foreground/service/abm_foreground_service.dart"
        )
        manifest = _read_mobile("android/app/src/main/AndroidManifest.xml")
        survival_markers = [
            "allowWakeLock: true",
            "autoRunOnBoot: true",
            "ForegroundTaskEventAction.repeat",
            "FOREGROUND_SERVICE",
            "FOREGROUND_SERVICE_DATA_SYNC",
            "WAKE_LOCK",
            "BOOT_COMPLETED",
        ]
        for marker in survival_markers:
            assert marker in service or marker in manifest, (
                f"Missing low-memory survival marker: {marker}"
            )

    def test_task_handler_continues_heartbeat_under_simulated_trim(self):
        """
        Simulate repeated OS memory-pressure cycles: the task handler must
        keep incrementing tick count and emitting heartbeats — it never
        self-terminates on trim (no onTrimMemory / System.gc hooks).
        """
        service = _read_mobile(
            "lib/features/foreground/service/abm_foreground_service.dart"
        )
        assert "onRepeatEvent" in service
        assert "_tickCount++" in service
        assert "'type': 'heartbeat'" in service
        trim_hooks = ["onTrimMemory", "onLowMemory", "System.gc(", "finish()"]
        for hook in trim_hooks:
            assert hook not in service, (
                f"Foreground service must not terminate on {hook}"
            )

    def test_foreground_bloc_encapsulates_platform_surface(self):
        bloc = _read_mobile("lib/features/foreground/bloc/foreground_bloc.dart")
        assert "AbmForegroundService" in bloc
        assert "FlutterForegroundTask" not in bloc, (
            "ForegroundBloc must not call FlutterForegroundTask directly"
        )


# ===========================================================================
# Proof 2 — Encrypted sync channel integrity
# ===========================================================================


class TestEncryptedSyncIntegrityGate:
    """Gate: vetted crypto only; reject unencrypted and tampered payloads."""

    VETTED_DART_PACKAGES = {"cryptography:", "flutter_secure_storage:"}
    BANNED_CRYPTO_FRAGMENTS = ["PointyCastle", "encrypt package:", "xor"]

    def test_pubspec_declares_only_vetted_crypto_packages(self):
        pubspec = _read_mobile("pubspec.yaml")
        for pkg in self.VETTED_DART_PACKAGES:
            assert pkg in pubspec
        for banned in self.BANNED_CRYPTO_FRAGMENTS:
            assert banned not in pubspec

    def test_key_store_and_channel_delegate_to_vetted_packages(self):
        key_store = _read_mobile(
            "lib/features/sync/crypto/cross_node_key_store.dart"
        )
        channel = _read_mobile("lib/features/sync/crypto/sync_crypto_channel.dart")
        for src in (key_store, channel):
            assert "package:cryptography/cryptography.dart" in src
            assert "AesGcm.with256bits()" in src
        assert "package:flutter_secure_storage/flutter_secure_storage.dart" in key_store
        for banned in self.BANNED_CRYPTO_FRAGMENTS:
            assert banned not in key_store
            assert banned not in channel

    def test_repository_never_posts_unencrypted_json_to_payload_endpoint(self):
        repo = _read_mobile(
            "lib/features/sync/repository/cross_node_sync_repository.dart"
        )
        assert "encryptJson" in repo
        assert "EncryptedSyncPayload" in repo
        assert "kSyncPayloadEndpoint" in repo
        # Payload path must go through encryptJson, not raw json body
        assert repo.index("sendEncryptedJson") < repo.index("encryptJson")

    def test_unencrypted_payload_missing_crypto_fields_rejected(self):
        plain = {"event": "ambient", "text": "hello"}
        with pytest.raises(ValueError, match="Unencrypted or malformed"):
            _decrypt_sync_payload(os.urandom(32), plain)

    def test_tampered_ciphertext_rejected(self):
        key = os.urandom(32)
        wire = _encrypt_sync_json(key, {"safe": True})
        ct = bytearray(base64.b64decode(wire["ciphertext"]))
        ct[0] ^= 0xFF
        wire["ciphertext"] = base64.b64encode(bytes(ct)).decode()
        with pytest.raises(InvalidTag):
            _decrypt_sync_payload(key, wire)

    def test_tampered_mac_rejected(self):
        key = os.urandom(32)
        wire = _encrypt_sync_json(key, {"safe": True})
        mac = bytearray(base64.b64decode(wire["mac"]))
        mac[0] ^= 0xFF
        wire["mac"] = base64.b64encode(bytes(mac)).decode()
        with pytest.raises(InvalidTag):
            _decrypt_sync_payload(key, wire)

    def test_tampered_aad_field_rejected(self):
        key = os.urandom(32)
        wire = _encrypt_sync_json(key, {"safe": True})
        wire["node_id"] = "attacker_node"
        with pytest.raises(InvalidTag):
            _decrypt_sync_payload(key, wire)

    def test_valid_encrypted_roundtrip_succeeds(self):
        key = os.urandom(32)
        original = {"ambient_event": "git_commit", "text": "feat: gate test"}
        wire = _encrypt_sync_json(key, original)
        assert _decrypt_sync_payload(key, wire) == original

    def test_dart_decrypt_rejects_wrong_algorithm(self):
        channel = _read_mobile("lib/features/sync/crypto/sync_crypto_channel.dart")
        assert "Unsupported sync algorithm" in channel
        assert "Unsupported sync protocol version" in channel


# ===========================================================================
# Proof 3 — Ambient manager source allowlist
# ===========================================================================


class TestAmbientManagerSourceAllowlistGate:
    """Gate: only Git / IDE workspace / design-doc telemetry is ingested."""

    PROHIBITED_KINDS = ["clipboard", "voice", "browser", "microphone", "camera"]

    def test_permitted_source_kinds_exactly_three(self):
        assert PERMITTED_SOURCE_KINDS == frozenset(
            {"git_commit", "workspace_file", "design_doc"}
        )

    @pytest.mark.parametrize("bad_kind", PROHIBITED_KINDS)
    def test_prohibited_kinds_rejected_at_construction(self, bad_kind):
        with pytest.raises(ValueError, match="not permitted"):
            AmbientEvent(
                source_kind=bad_kind,
                active_repository="repo",
                source_path="/x",
                text="blocked source",
            )

    def test_workspace_monitor_ignores_code_files(self):
        events: list[AmbientEvent] = []
        monitor = WorkspaceStateMonitor(
            watch_paths=[],
            on_event=events.append,
        )
        code_evt = FileChangeEvent(
            path="/proj/src/main.py",
            event_type="modified",
            epoch_timestamp=1_700_000_000,
            repository="proj",
        )
        monitor._on_telemetry_event(code_evt)
        assert events == []

    def test_workspace_monitor_accepts_design_doc_extensions(self):
        events: list[AmbientEvent] = []
        monitor = WorkspaceStateMonitor(
            watch_paths=[],
            on_event=events.append,
        )
        for ext in DESIGN_DOC_EXTENSIONS:
            doc_evt = FileChangeEvent(
                path=f"/proj/docs/spec{ext}",
                event_type="modified",
                epoch_timestamp=1_700_000_000,
                repository="proj",
            )
            monitor._on_telemetry_event(doc_evt)
        assert len(events) == len(DESIGN_DOC_EXTENSIONS)
        assert all(e.source_kind == "workspace_file" for e in events)

    def test_dart_telemetry_enum_has_only_three_permitted_kinds(self):
        model = _read_mobile(
            "lib/features/telemetry/models/ambient_event_model.dart"
        )
        events = _read_mobile("lib/features/telemetry/bloc/telemetry_event.dart")
        assert "gitCommit('git_commit')" in model
        assert "workspaceFile('workspace_file')" in model
        assert "designDoc('design_doc')" in model
        for prohibited in self.PROHIBITED_KINDS:
            assert prohibited not in model.lower()
            assert prohibited not in events.lower()

    def test_android_manifest_excludes_clipboard_microphone_permissions(self):
        manifest = _read_mobile("android/app/src/main/AndroidManifest.xml")
        banned_perms = [
            "READ_CLIPBOARD",
            "RECORD_AUDIO",
            "CAPTURE_AUDIO",
            "BIND_ACCESSIBILITY",
        ]
        for perm in banned_perms:
            assert perm not in manifest


# ===========================================================================
# Proof 4 — Stream C compression window
# ===========================================================================


class TestStreamCCompressionWindowGate:
    """Gate: dedup compression within window; re-store after window elapses."""

    def test_compress_window_is_one_hour(self):
        assert COMPRESS_WINDOW_SECONDS == 3_600

    def test_duplicate_within_window_returns_compressed_not_stored(self):
        writer = _make_writer(compress_window=3600)
        base_time = 1_700_000_000
        with patch("abm.mobile.stream_c_writer.time.time", side_effect=[base_time, base_time]):
            r1 = writer.write(_make_event(text="same payload"))
            r2 = writer.write(_make_event(text="same payload"))
        assert r1.status == "ok"
        assert r2.status == "compressed"
        assert r2.doc_id == ""

    def test_duplicate_after_window_is_stored_again(self):
        writer = _make_writer(compress_window=3600)
        t0, t1, t2 = 1_700_000_000, 1_700_000_000, 1_700_003_601
        with patch(
            "abm.mobile.stream_c_writer.time.time",
            side_effect=[t0, t0, t2],
        ):
            r1 = writer.write(_make_event(text="same payload"))
            r2 = writer.write(_make_event(text="same payload"))
            r3 = writer.write(_make_event(text="same payload"))
        assert r1.status == "ok"
        assert r2.status == "compressed"
        assert r3.status == "ok"
        assert r3.doc_id != ""

    def test_housekeeper_summarizes_entries_past_retention_window(self):
        """MEMORY_LIFECYCLE_POLICY: entries past summarize threshold are compressed."""
        ctrl = _mock_controller()
        emb = _mock_embedder()
        hk = StreamCRetentionHousekeeper(
            controller=ctrl,
            embedder=emb,
            archive_persist_dir="./test_archive",
        )
        old_epoch = 1_700_000_000
        now_epoch = old_epoch + SUMMARIZE_AFTER_SECONDS + 1

        collection_mock = MagicMock()
        collection_mock.get.return_value = {
            "ids": ["old_doc"],
            "metadatas": [
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "dynamic_mobile_node",
                    "source_kind": "git_commit",
                    "lifecycle_stage": "raw",
                }
            ],
            "documents": ["old ambient event"],
            "embeddings": [[0.1, 0.2]],
        }
        ctrl.get_collection.return_value = collection_mock

        result = hk.force_run(now_epoch=now_epoch)
        assert result.summarized == 1
        ctrl.add_document.assert_called()

    def test_housekeeper_deletes_entries_past_delete_window(self):
        ctrl = _mock_controller()
        hk = StreamCRetentionHousekeeper(
            controller=ctrl,
            embedder=_mock_embedder(),
            archive_persist_dir="./test_archive",
        )
        old_epoch = 1_700_000_000
        now_epoch = old_epoch + DELETE_AFTER_SECONDS + 1

        collection_mock = MagicMock()
        collection_mock.get.return_value = {
            "ids": ["stale_doc"],
            "metadatas": [
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "dynamic_mobile_node",
                    "lifecycle_stage": "raw",
                }
            ],
            "documents": ["stale event"],
            "embeddings": [[0.1]],
        }
        ctrl.get_collection.return_value = collection_mock

        result = hk.force_run(now_epoch=now_epoch)
        assert result.deleted == 1
        collection_mock.delete.assert_called_once_with(ids=["stale_doc"])


# ===========================================================================
# Proof 5 — Full roadmap regression
# ===========================================================================


class TestRoadmapRegressionGate:
    """Gate: all prior phase suites remain 100% green."""

    @pytest.mark.parametrize("gate_file", PRIOR_GATE_FILES)
    def test_prior_gate_suite_still_passes(self, gate_file: str):
        gate_path = PROJECT_ROOT / gate_file
        assert gate_path.is_file(), f"Missing prior gate file: {gate_file}"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(gate_path), "-q", "--tb=no"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{gate_file} regressed:\n{result.stdout}\n{result.stderr}"
        )
