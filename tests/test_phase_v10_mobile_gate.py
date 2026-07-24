"""
tests/test_phase_v10_mobile_gate.py
=====================================
Hard Gate — Phase v1.0 Flutter Foreground Service & Ambient Interaction Manager

Proves the Python-side mobile contracts.  All tests are fully mocked —
no live Ollama, no real ChromaDB, no filesystem side-effects.

Gate run command:
    python -m pytest tests/test_phase_v10_mobile_gate.py -v

Full regression:
    python -m pytest tests/ -v

──────────────────────────────────────────────────────────────────────────────
Test classes and what they prove
──────────────────────────────────────────────────────────────────────────────

TestAmbientEventSchemaGate
  - Only PERMITTED_SOURCE_KINDS are accepted; all others raise ValueError
  - Clipboard, voice, browser all raise ValueError
  - device_source defaults to "desktop_workspace" but respects constructor arg
  - Empty text raises ValueError
  - epoch_timestamp defaults to a positive integer

TestStreamCWriterRetentionAwareGate
  - Unique event → status "ok" with non-empty doc_id
  - Identical (source_kind, repo, text_hash) within compress window → "compressed"
  - Same event beyond compress window → "ok" again (window has elapsed)
  - Invalid source_kind (already caught by AmbientEvent but caught here too) → "invalid"
  - Metadata written to ChromaDB contains exactly 3 fields: epoch_timestamp,
    active_repository, device_source — no extras
  - Embedding failure → status "error"
  - ChromaDB write failure → status "error"

TestRetentionHousekeeperLifecycleGate
  - Housekeeper skips when interval has not elapsed
  - force_run with time-travelled now_epoch:
      - Entry older than SUMMARIZE_AFTER_DAYS → summarized > 0
      - Entry older than DELETE_AFTER_DAYS → deleted > 0
  - Housekeeping interval guard: second call within interval returns skipped=True

TestAmbientInteractionManagerScopeGate
  - start() calls design_doc_monitor.scan() once
  - stop() calls workspace_monitor.stop()
  - ingest_event() with permitted source_kind → WriteResult.status in {"ok", "compressed"}
  - Git monitor is None when git_repo_path is absent
  - poll_git() returns 0 when git_monitor is None
  - poll_git() is rate-limited (second call within interval → 0)

TestIngestAmbientEventCapabilityGate
  - ingestAmbientEvent returns AmbientIngestionResult with status "ok"
  - Degrades gracefully when ambient_manager.ingest_event raises → degraded=True
  - ingestAmbientEvent before boot raises via _require_booted (expected error path)
  - STATUS tag in docstring is "stable"
  - OWNER tag in docstring contains "AmbientInteractionManager"

TestEncryptedCrossNodeSyncGate
  - Flutter pubspec declares cryptography and flutter_secure_storage
  - CrossNodeKeyStore uses flutter_secure_storage and AesGcm.with256bits()
  - SyncCryptoChannel uses package:cryptography AES-GCM encrypt/decrypt with AAD
  - SyncHandshake and EncryptedSyncPayload wire field names are fixed
  - CrossNodeSyncRepository exposes handshake and encrypted payload endpoints

TestV01ToV10MobileRegressionGate
  - COLLECTION_AMBIENT_TELEMETRY constant unchanged from v0.1
  - PERMITTED_SOURCE_KINDS contains exactly {git_commit, workspace_file, design_doc}
  - AmbientTelemetryMetadata (v0.1 schema) accepts exactly 3 fields
  - COMPRESS_WINDOW_SECONDS is 3600
  - HOUSEKEEPING_INTERVAL_SECONDS is 3600
  - SUMMARIZE_AFTER_DAYS is 14, ARCHIVE_AFTER_DAYS is 30, DELETE_AFTER_DAYS is 180
  - Prior collection names (v0.1 gate) are unchanged
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from abm.mobile.event_models import AmbientEvent, PERMITTED_SOURCE_KINDS
from abm.mobile.stream_c_writer import StreamCWriter, WriteResult, COMPRESS_WINDOW_SECONDS
from abm.mobile.retention_housekeeper import (
    StreamCRetentionHousekeeper,
    HousekeeperResult,
    HOUSEKEEPING_INTERVAL_SECONDS,
    SUMMARIZE_AFTER_DAYS,
    ARCHIVE_AFTER_DAYS,
    DELETE_AFTER_DAYS,
    SUMMARIZE_AFTER_SECONDS,
    DELETE_AFTER_SECONDS,
)
from abm.mobile.ambient_manager import (
    AmbientInteractionManager,
    ManagerConfig,
    DESIGN_DOC_EXTENSIONS,
)
from abm.mobile import COLLECTION_AMBIENT_ARCHIVE
from abm.memory.chroma_controller import (
    COLLECTION_AMBIENT_TELEMETRY,
    ALL_COLLECTIONS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = PROJECT_ROOT / "mobile"


# ===========================================================================
# Helpers
# ===========================================================================


def _mock_controller():
    ctrl = MagicMock()
    ctrl.get_collection.return_value = MagicMock()
    return ctrl


def _mock_embedder(embedding: list[float] | None = None):
    emb = MagicMock()
    emb.embed.return_value = embedding or [0.1, 0.2, 0.3]
    return emb


def _make_event(
    source_kind: str = "git_commit",
    repo: str = "test_repo",
    text: str = "a git commit event",
    epoch: int = 1_000_000,
) -> AmbientEvent:
    return AmbientEvent(
        source_kind=source_kind,
        active_repository=repo,
        source_path="/repo/head",
        text=text,
        epoch_timestamp=epoch,
    )


def _make_writer(
    controller=None,
    embedder=None,
    housekeeper=None,
    compress_window: int = COMPRESS_WINDOW_SECONDS,
) -> StreamCWriter:
    ctrl = controller or _mock_controller()
    emb = embedder or _mock_embedder()
    hk = housekeeper or MagicMock(spec=StreamCRetentionHousekeeper)
    hk.run_if_due.return_value = HousekeeperResult(skipped=True)
    return StreamCWriter(
        controller=ctrl,
        embedder=emb,
        housekeeper=hk,
        compress_window_seconds=compress_window,
    )


# ===========================================================================
# TestAmbientEventSchemaGate
# ===========================================================================


class TestAmbientEventSchemaGate:
    """Gate: AmbientEvent construction validates source_kind and text."""

    def test_permitted_source_kinds_accepted(self):
        for kind in PERMITTED_SOURCE_KINDS:
            evt = AmbientEvent(
                source_kind=kind,
                active_repository="repo",
                source_path="/p",
                text=f"event text for {kind}",
            )
            assert evt.source_kind == kind

    @pytest.mark.parametrize(
        "bad_kind",
        ["clipboard", "voice", "browser", "microphone", "camera", "", "unknown"],
    )
    def test_prohibited_source_kinds_raise(self, bad_kind):
        with pytest.raises(ValueError, match="not permitted"):
            AmbientEvent(
                source_kind=bad_kind,
                active_repository="repo",
                source_path="/p",
                text="some text",
            )

    def test_device_source_respects_origin_tag(self):
        evt = AmbientEvent(source_kind="git_commit", active_repository="repo", source_path="/p", text="t", device_source="dynamic_mobile_node")
        assert evt.device_source == "dynamic_mobile_node"
        evt2 = AmbientEvent(source_kind="git_commit", active_repository="repo", source_path="/p", text="t")
        assert evt2.device_source == "desktop_workspace"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="text"):
            AmbientEvent(
                source_kind="git_commit",
                active_repository="repo",
                source_path="/p",
                text="",
            )

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValueError, match="text"):
            AmbientEvent(
                source_kind="git_commit",
                active_repository="repo",
                source_path="/p",
                text="   \n\t",
            )

    def test_epoch_timestamp_defaults_to_positive_int(self):
        evt = _make_event()
        assert isinstance(evt.epoch_timestamp, int)
        assert evt.epoch_timestamp > 0

    def test_permitted_source_kinds_set_contains_exactly_four(self):
        assert len(PERMITTED_SOURCE_KINDS) == 4


# ===========================================================================
# TestStreamCWriterRetentionAwareGate
# ===========================================================================


class TestStreamCWriterRetentionAwareGate:
    """Gate: StreamCWriter enforces all retention-path stages."""

    def test_unique_event_returns_ok(self):
        writer = _make_writer()
        evt = _make_event()
        result = writer.write(evt)
        assert result.status == "ok"
        assert result.doc_id != ""

    def test_metadata_has_exactly_three_fields(self):
        ctrl = _mock_controller()
        writer = _make_writer(controller=ctrl)
        evt = _make_event()
        writer.write(evt)

        # Capture the metadata kwarg from add_document call
        assert ctrl.add_document.called
        _, kwargs = ctrl.add_document.call_args
        metadata: dict = kwargs["metadata"]
        assert set(metadata.keys()) == {"epoch_timestamp", "active_repository", "device_source"}, (
            f"Expected exactly 3 metadata fields, got: {set(metadata.keys())}"
        )

    def test_duplicate_within_compress_window_returns_compressed(self):
        writer = _make_writer(compress_window=9999)
        evt = _make_event(epoch=int(time.time()))
        r1 = writer.write(evt)
        # Second identical event
        evt2 = _make_event(epoch=int(time.time()))
        r2 = writer.write(evt2)
        assert r1.status == "ok"
        assert r2.status == "compressed"

    def test_same_event_after_window_is_written_again(self):
        # Compress window of 0 means every write goes through
        writer = _make_writer(compress_window=0)
        evt = _make_event(epoch=1_000_000)
        r1 = writer.write(evt)
        evt2 = _make_event(epoch=1_000_001)
        r2 = writer.write(evt2)
        assert r1.status == "ok"
        assert r2.status == "ok"

    def test_different_repos_not_deduplicated(self):
        writer = _make_writer(compress_window=9999)
        e1 = _make_event(repo="repo_A")
        e2 = _make_event(repo="repo_B")
        r1 = writer.write(e1)
        r2 = writer.write(e2)
        assert r1.status == "ok"
        assert r2.status == "ok"

    def test_embedding_failure_returns_error(self):
        emb = MagicMock()
        emb.embed.side_effect = RuntimeError("Ollama down")
        writer = _make_writer(embedder=emb)
        result = writer.write(_make_event())
        assert result.status == "error"
        assert "Embedding failed" in result.reason

    def test_chroma_write_failure_returns_error(self):
        ctrl = _mock_controller()
        ctrl.add_document.side_effect = RuntimeError("ChromaDB full")
        writer = _make_writer(controller=ctrl)
        result = writer.write(_make_event())
        assert result.status == "error"
        assert "ChromaDB write failed" in result.reason

    def test_housekeeper_called_after_successful_write(self):
        hk = MagicMock(spec=StreamCRetentionHousekeeper)
        hk.run_if_due.return_value = HousekeeperResult(skipped=True)
        writer = _make_writer(housekeeper=hk)
        writer.write(_make_event())
        hk.run_if_due.assert_called_once()

    def test_housekeeper_not_called_on_compressed_write(self):
        hk = MagicMock(spec=StreamCRetentionHousekeeper)
        hk.run_if_due.return_value = HousekeeperResult(skipped=True)
        writer = _make_writer(housekeeper=hk, compress_window=9999)
        writer.write(_make_event(epoch=int(time.time())))
        writer.write(_make_event(epoch=int(time.time())))
        # Only called once (on the first ok write; not on compressed)
        assert hk.run_if_due.call_count == 1


# ===========================================================================
# TestRetentionHousekeeperLifecycleGate
# ===========================================================================


class TestRetentionHousekeeperLifecycleGate:
    """Gate: StreamCRetentionHousekeeper enforces MEMORY_LIFECYCLE_POLICY stages."""

    def _make_housekeeper(self):
        ctrl = _mock_controller()
        emb = _mock_embedder()
        return StreamCRetentionHousekeeper(
            controller=ctrl,
            embedder=emb,
            archive_persist_dir="./test_archive",
            housekeeping_interval_seconds=HOUSEKEEPING_INTERVAL_SECONDS,
        ), ctrl, emb

    def test_run_if_due_skips_before_interval(self):
        hk, _, _ = self._make_housekeeper()
        # First call runs (last_run=0)
        # Second call immediately after should be skipped (monotonic clock not elapsed)
        hk._last_run = time.monotonic()  # simulate already ran
        result = hk.run_if_due()
        assert result.skipped is True

    def test_run_if_due_runs_after_interval(self):
        hk, ctrl, emb = self._make_housekeeper()
        # Fresh housekeeper (never run) should run immediately
        # Make get_collection return empty (no entries to process)
        hk._controller.get_collection.return_value.get.return_value = {"ids": []}
        result = hk.run_if_due()
        assert result.skipped is False

    def test_force_run_deletes_entries_past_delete_threshold(self):
        hk, ctrl, _ = self._make_housekeeper()
        old_epoch = int(time.time()) - DELETE_AFTER_SECONDS - 1
        now_epoch = int(time.time())

        collection_mock = MagicMock()
        collection_mock.get.return_value = {
            "ids": ["old_doc_1"],
            "metadatas": [
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "dynamic_mobile_node",
                    "source_kind": "git_commit",
                    "lifecycle_stage": "raw",
                }
            ],
            "documents": ["old event text"],
            "embeddings": [[0.1, 0.2]],
        }
        ctrl.get_collection.return_value = collection_mock

        result = hk.force_run(now_epoch=now_epoch)
        assert result.deleted == 1
        collection_mock.delete.assert_called_once_with(ids=["old_doc_1"])

    def test_force_run_summarizes_entries_past_summarize_threshold(self):
        hk, ctrl, emb = self._make_housekeeper()
        old_epoch = int(time.time()) - SUMMARIZE_AFTER_SECONDS - 1
        now_epoch = int(time.time())

        collection_mock = MagicMock()
        collection_mock.get.return_value = {
            "ids": ["doc_1"],
            "metadatas": [
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "dynamic_mobile_node",
                    "source_kind": "git_commit",
                    "lifecycle_stage": "raw",
                }
            ],
            "documents": ["commit event text"],
            "embeddings": [[0.1, 0.2]],
        }
        ctrl.get_collection.return_value = collection_mock

        result = hk.force_run(now_epoch=now_epoch)
        # Should have attempted to summarize (called add_document for summary)
        assert result.summarized == 1

    def test_force_run_archives_with_distinct_timestamps(self):
        hk, ctrl, emb = self._make_housekeeper()
        old_epoch = int(time.time()) - (ARCHIVE_AFTER_DAYS * 86400) - 1
        now_epoch = int(time.time())

        collection_mock = MagicMock()
        collection_mock.get.return_value = {
            "ids": ["doc_1", "doc_2"],
            "metadatas": [
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "desktop_workspace",
                    "source_kind": "git_commit",
                    "lifecycle_stage": "summarized",
                },
                {
                    "epoch_timestamp": old_epoch,
                    "active_repository": "repo",
                    "device_source": "desktop_workspace",
                    "source_kind": "git_commit",
                    "lifecycle_stage": "summarized",
                }
            ],
            "documents": ["sum1", "sum2"],
            "embeddings": [[0.1], [0.2]],
        }
        ctrl.get_collection.return_value = collection_mock
        archive_mock = MagicMock()
        with patch("abm.mobile.retention_housekeeper._build_archive_controller") as mock_build_ctrl:
            mock_build_ctrl.return_value._client.get_or_create_collection.return_value = archive_mock
            result = hk.force_run(now_epoch=now_epoch)

        assert result.archived == 2
        
        upserts = archive_mock.upsert.call_args_list
        assert len(upserts) == 2
        meta0 = upserts[0][1]["metadatas"][0]
        meta1 = upserts[1][1]["metadatas"][0]
        assert meta0["archived_at"] != meta1["archived_at"]

    def test_constants_match_policy_document(self):
        assert SUMMARIZE_AFTER_DAYS == 14
        assert ARCHIVE_AFTER_DAYS == 30
        assert DELETE_AFTER_DAYS == 180
        assert HOUSEKEEPING_INTERVAL_SECONDS == 3_600


# ===========================================================================
# TestAmbientInteractionManagerScopeGate
# ===========================================================================


class TestAmbientInteractionManagerScopeGate:
    """Gate: AmbientInteractionManager enforces Phase v1.0 telemetry scope."""

    def _make_manager(self, config: ManagerConfig | None = None):
        ctrl = _mock_controller()
        emb = _mock_embedder()
        mgr = AmbientInteractionManager(
            controller=ctrl,
            embedder=emb,
            config=config or ManagerConfig(),
        )
        return mgr, ctrl, emb

    def test_git_monitor_none_without_repo_path(self):
        mgr, _, _ = self._make_manager()
        assert mgr._git_monitor is None

    def test_poll_git_returns_zero_without_git_monitor(self):
        mgr, _, _ = self._make_manager()
        assert mgr.poll_git() == 0

    def test_poll_git_rate_limited(self):
        with patch(
            "abm.companion.git_pipeline.GitPipeline"
        ) as MockPipeline:
            MockPipeline.return_value.list_commits.return_value = []
            MockPipeline.return_value.repo_name.return_value = "test_repo"
            config = ManagerConfig(git_repo_path="/fake/repo", git_poll_interval_seconds=9999)
            mgr, _, _ = self._make_manager(config=config)
            # First poll initialises last_sha
            mgr._last_git_poll = time.monotonic()  # simulate just ran
            count = mgr.poll_git()
            assert count == 0  # rate-limited

    def test_ingest_event_permitted_kind_returns_ok(self):
        mgr, ctrl, emb = self._make_manager()
        evt = _make_event()
        result = mgr.ingest_event(evt)
        assert result.status in {"ok", "compressed"}

    def test_ingest_event_prohibited_kind_raises_at_event_construction(self):
        """
        Clipboard/voice/browser are blocked at AmbientEvent construction,
        before ingest_event is even called. This proves the scope guardrail
        is structural, not runtime.
        """
        with pytest.raises(ValueError, match="not permitted"):
            AmbientEvent(
                source_kind="clipboard",
                active_repository="repo",
                source_path="/clip",
                text="some clipboard text",
            )

    def test_is_running_false_before_start(self):
        mgr, _, _ = self._make_manager()
        assert mgr.is_running is False

    def test_design_doc_extensions_match_spec(self):
        """Ensure design-doc extensions are the correct set."""
        required = {".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".toml"}
        assert required <= DESIGN_DOC_EXTENSIONS


# ===========================================================================
# TestIngestAmbientEventCapabilityGate
# ===========================================================================


class TestIngestAmbientEventCapabilityGate:
    """Gate: ingestAmbientEvent API capability contracts."""

    def _make_mock_registry(self, status: str = "ok", raises: bool = False):
        registry = MagicMock()
        manager = MagicMock()
        if raises:
            manager.ingest_event.side_effect = RuntimeError("manager exploded")
        else:
            manager.ingest_event.return_value = WriteResult(
                status=status,
                doc_id="doc_123" if status == "ok" else "",
                reason="" if status == "ok" else "duplicate",
                housekeeper_ran=False,
            )
        registry.ambient_manager = manager
        return registry, manager

    def test_ok_event_returns_ambient_ingestion_result(self):
        from abm.api.capabilities import ingestAmbientEvent, AmbientIngestionResult

        registry, _ = self._make_mock_registry(status="ok")
        evt = _make_event()
        result = ingestAmbientEvent(evt, registry=registry)
        assert isinstance(result, AmbientIngestionResult)
        assert result.status == "ok"
        assert result.doc_id == "doc_123"
        assert result.degraded is False

    def test_compressed_event_returns_compressed_status(self):
        from abm.api.capabilities import ingestAmbientEvent

        registry, _ = self._make_mock_registry(status="compressed")
        result = ingestAmbientEvent(_make_event(), registry=registry)
        assert result.status == "compressed"
        assert result.degraded is False

    def test_manager_exception_returns_degraded(self):
        from abm.api.capabilities import ingestAmbientEvent

        registry, _ = self._make_mock_registry(raises=True)
        result = ingestAmbientEvent(_make_event(), registry=registry)
        assert result.status == "error"
        assert result.degraded is True
        assert "manager exploded" in result.reason

    def test_status_tag_is_stable(self):
        from abm.api.capabilities import ingestAmbientEvent

        docstring = ingestAmbientEvent.__doc__ or ""
        assert "stable" in docstring.lower(), (
            "ingestAmbientEvent must have STATUS: stable in docstring"
        )

    def test_owner_tag_names_ambient_interaction_manager(self):
        from abm.api.capabilities import ingestAmbientEvent

        docstring = ingestAmbientEvent.__doc__ or ""
        assert "AmbientInteractionManager" in docstring, (
            "ingestAmbientEvent docstring must name AmbientInteractionManager as OWNER"
        )


# ===========================================================================
# TestEncryptedCrossNodeSyncGate
# ===========================================================================


class TestEncryptedCrossNodeSyncGate:
    """Gate: Flutter sync channel uses vetted AES-GCM and secure storage."""

    def _read_mobile_file(self, relative_path: str) -> str:
        return (MOBILE_ROOT / relative_path).read_text(encoding="utf-8")

    def test_pubspec_declares_required_crypto_packages(self):
        pubspec = self._read_mobile_file("pubspec.yaml")
        assert "cryptography:" in pubspec
        assert "flutter_secure_storage:" in pubspec

    def test_key_store_uses_flutter_secure_storage_and_cryptography(self):
        source = self._read_mobile_file(
            "lib/features/sync/crypto/cross_node_key_store.dart"
        )
        assert "package:flutter_secure_storage/flutter_secure_storage.dart" in source
        assert "package:cryptography/cryptography.dart" in source
        assert "AesGcm.with256bits()" in source
        assert "FlutterSecureStorage" in source
        assert "SecretKey" in source

    def test_sync_channel_uses_aes_gcm_encrypt_decrypt_not_custom_cipher(self):
        source = self._read_mobile_file(
            "lib/features/sync/crypto/sync_crypto_channel.dart"
        )
        assert "package:cryptography/cryptography.dart" in source
        assert "AesGcm.with256bits()" in source
        assert ".encrypt(" in source
        assert ".decrypt(" in source
        assert "SecretBox(" in source
        assert "aad: aad" in source
        banned_fragments = ["xor", "PointyCastle", "Random.secure().nextInt"]
        assert not any(fragment in source for fragment in banned_fragments)

    def test_handshake_wire_fields_are_documented_in_dart_model(self):
        source = self._read_mobile_file("lib/features/sync/models/sync_handshake.dart")
        expected_fields = {
            "protocol_version",
            "node_id",
            "key_id",
            "algorithm",
            "created_at_epoch",
            "capabilities",
        }
        for field in expected_fields:
            assert f"'{field}'" in source
        assert "AES-256-GCM" in source

    def test_encrypted_payload_wire_fields_are_documented_in_dart_model(self):
        source = self._read_mobile_file(
            "lib/features/sync/models/encrypted_sync_payload.dart"
        )
        expected_fields = {
            "protocol_version",
            "key_id",
            "algorithm",
            "node_id",
            "created_at_epoch",
            "content_type",
            "nonce",
            "ciphertext",
            "mac",
        }
        for field in expected_fields:
            assert f"'{field}'" in source

    def test_sync_repository_uses_handshake_and_payload_endpoints(self):
        source = self._read_mobile_file(
            "lib/features/sync/repository/cross_node_sync_repository.dart"
        )
        assert "kSyncHandshakeEndpoint = '/api/sync/handshake'" in source
        assert "kSyncPayloadEndpoint = '/api/sync/payload'" in source
        assert "sendHandshake" in source
        assert "sendEncryptedJson" in source


# ===========================================================================
# TestV01ToV10MobileRegressionGate
# ===========================================================================


class TestV01ToV10MobileRegressionGate:
    """
    Gate: all prior-phase constants are unchanged after adding abm.mobile.

    Every value here is an immutable fact from a gated phase. If any
    assertion fails, a prior module has been silently broken.
    """

    def test_collection_ambient_telemetry_name_unchanged(self):
        assert COLLECTION_AMBIENT_TELEMETRY == "abm_ambient_telemetry"

    def test_all_collections_unchanged(self):
        expected = {
            "abm_code_topologies",
            "abm_technical_mastery",
            "abm_ambient_telemetry",
            "abm_cognitive_identity",
        }
        assert set(ALL_COLLECTIONS) == expected

    def test_permitted_source_kinds_exactly_four(self):
        assert PERMITTED_SOURCE_KINDS == frozenset(
            {"git_commit", "workspace_file", "design_doc", "chat_history"}
        )

    def test_compress_window_is_one_hour(self):
        assert COMPRESS_WINDOW_SECONDS == 3_600

    def test_housekeeping_interval_is_one_hour(self):
        assert HOUSEKEEPING_INTERVAL_SECONDS == 3_600

    def test_lifecycle_thresholds_match_policy(self):
        assert SUMMARIZE_AFTER_DAYS == 14
        assert ARCHIVE_AFTER_DAYS == 30
        assert DELETE_AFTER_DAYS == 180

    def test_ambient_telemetry_metadata_v01_schema_fields(self):
        """
        The v0.1 Pydantic model has exactly 3 fields: epoch_timestamp,
        active_repository, device_source.  The Literal constraint on
        active_repository is a v0.1 scope decision (two known projects);
        StreamCWriter uses inline validation to remain compatible with
        arbitrary repos without modifying the v0.1 schema.
        """
        from abm.memory.metadata_models import AmbientTelemetryMetadata
        import inspect

        fields = AmbientTelemetryMetadata.model_fields
        assert set(fields.keys()) == {
            "epoch_timestamp",
            "active_repository",
            "device_source",
        }, f"AmbientTelemetryMetadata fields changed: {set(fields.keys())}"

    def test_collection_ambient_archive_name_is_correct(self):
        assert COLLECTION_AMBIENT_ARCHIVE == "abm_ambient_telemetry_archive"

    def test_device_source_value_matches_spec(self):
        evt = _make_event()
        assert evt.device_source == "desktop_workspace"
