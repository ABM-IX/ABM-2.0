"""
abm/api/core/registry.py
========================
ServiceRegistry — boot / service-registration / shutdown lifecycle manager
for the ABM API layer.

Holds lazily-initialised singletons for every service the capability
functions depend on. Callers obtain services through typed accessor
properties — they never reach into internal ABM modules directly.

Design contract (per CLIENT_01_CONSOLE.md):
  - boot()     : Create + warm-up all services in dependency order.
  - shutdown() : Stop all services, release resources.
  - health_check() : Non-destructive readiness probe (Ollama reachable?
                     ChromaDB collections initialised?).
  - Services are NOT replaced after boot; the registry is single-use per
    process lifetime.
  - This is NOT a formal DI/IoC container — that is an ARCHITECTURE_BACKLOG
    candidate (see ARCHITECTURE_BACKLOG.md: "Dependency Injection /
    Service Registry"). This is plain shared-instance management with
    lifecycle discipline sufficient for today's single-client scope.
  - Any error during boot raises RuntimeError so the console entrypoint
    can surface a clear message instead of a confusing attribute error later.

Architectural Constitution compliance:
  - Rule 9  : health_check() returns degraded status, never crashes.
  - Rule 1  : all services route through 127.0.0.1 — enforced by APIConfig.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from abm.api.core.config import APIConfig
from abm.memory.chroma_controller import ChromaController
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper
from abm.orchestrator.model_gateway import OllamaModelGateway
from abm.orchestrator.router import ClassificationRouter
from abm.strategic_wing.strategic_asset_analyzer import StrategicAssetAnalyzer
from abm.strategic_wing.workflow_monitor import WorkflowMonitor
from abm.mobile.ambient_manager import AmbientInteractionManager, ManagerConfig

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """
    Result of ``ServiceRegistry.health_check()``.

    Attributes
    ----------
    ollama_reachable : bool
        True if the local Ollama server responded to a health probe.
    chroma_ready : bool
        True if ChromaDB collections are initialised and queryable.
    degraded : bool
        True if any service is unavailable. The system can still operate in
        read-only / reduced mode (constitution rule 9).
    notes : list[str]
        Human-readable messages for each detected issue.
    """

    ollama_reachable: bool
    chroma_ready: bool
    degraded: bool
    notes: list[str]

    def __str__(self) -> str:  # pragma: no cover
        status = "DEGRADED" if self.degraded else "OK"
        lines = [f"Health: {status}"]
        lines.append(f"  Ollama : {'✓' if self.ollama_reachable else '✗ (not reachable)'}")
        lines.append(f"  ChromaDB: {'✓' if self.chroma_ready else '✗ (not ready)'}")
        for note in self.notes:
            lines.append(f"  ! {note}")
        return "\n".join(lines)


class ServiceRegistry:
    """
    Boot / service-registration / shutdown lifecycle manager.

    Usage
    -----
    ::

        config = APIConfig()
        registry = ServiceRegistry(config)
        registry.boot()        # ← creates all services
        # … use registry.router, registry.embedder, etc. …
        registry.shutdown()    # ← releases resources

    Services are accessed through read-only properties after ``boot()``.
    Accessing them before ``boot()`` raises ``RuntimeError``.
    """

    def __init__(self, config: APIConfig | None = None) -> None:
        self._config: APIConfig = config or APIConfig()
        self._booted: bool = False

        # Service singletons — populated by boot()
        self._controller: ChromaController | None = None
        self._embedder: OllamaEmbeddingWrapper | None = None
        self._gateway: OllamaModelGateway | None = None
        self._router: ClassificationRouter | None = None
        self._monitor: WorkflowMonitor | None = None
        self._analyzer: StrategicAssetAnalyzer | None = None
        self._ambient_manager: AmbientInteractionManager | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self) -> None:
        """
        Initialise all services in dependency order.

        Order matters: ChromaController and OllamaEmbeddingWrapper first
        (shared by many), then OllamaModelGateway, then ClassificationRouter
        (depends on gateway + optional controller/embedder), then higher-level
        services.

        Raises
        ------
        RuntimeError
            If boot fails for any critical service.
        """
        if self._booted:
            logger.warning("ServiceRegistry.boot: already booted — ignoring.")
            return

        logger.info("ServiceRegistry: booting …")

        # 1. ChromaDB — vector store (v0.1)
        try:
            self._controller = ChromaController(
                persist_directory=self._config.chroma_persist_directory
            )
            logger.info("ServiceRegistry: ChromaController ready.")
        except Exception as exc:
            raise RuntimeError(
                f"ServiceRegistry: ChromaController boot failed — {exc}"
            ) from exc

        # 2. Embedding wrapper — Ollama nomic-embed-text (v0.1)
        self._embedder = OllamaEmbeddingWrapper(
            base_url=self._config.ollama_base_url,
            model=self._config.embedding_model,
            connect_timeout=self._config.connect_timeout,
            read_timeout=self._config.read_timeout,
        )
        logger.info("ServiceRegistry: OllamaEmbeddingWrapper ready.")

        # 3. Model gateway — Ollama phi3:mini (v0.3)
        self._gateway = OllamaModelGateway(
            model=self._config.classification_model,
        )
        logger.info("ServiceRegistry: OllamaModelGateway ready.")

        # 4. Classification router — uses gateway + optional stream D context (v0.3)
        self._router = ClassificationRouter(
            gateway=self._gateway,
            controller=self._controller,
            embedder=self._embedder,
        )
        logger.info("ServiceRegistry: ClassificationRouter ready.")

        # 5. Workflow monitor — read-only task state aggregator (v0.5)
        self._monitor = WorkflowMonitor(
            quarantine_dir=self._config.quarantine_dir
        )
        logger.info("ServiceRegistry: WorkflowMonitor ready.")

        # 6. Strategic asset analyzer — multi-stream read-only analysis (v0.5)
        self._analyzer = StrategicAssetAnalyzer(
            controller=self._controller,
            embedder=self._embedder,
        )
        logger.info("ServiceRegistry: StrategicAssetAnalyzer ready.")

        # 7. Ambient interaction manager — Stream C retention-aware write path (v1.0)
        self._ambient_manager = AmbientInteractionManager(
            controller=self._controller,
            embedder=self._embedder,
            config=ManagerConfig(
                archive_persist_dir=self._config.chroma_persist_directory.rstrip("/") + "_archive",
            ),
        )
        logger.info("ServiceRegistry: AmbientInteractionManager ready.")

        self._booted = True
        logger.info("ServiceRegistry: boot complete.")

    def shutdown(self) -> None:
        """
        Release all held resources and mark registry as shut down.

        Safe to call even if ``boot()`` was never called or failed partway
        through. Idempotent — calling more than once is a no-op.
        """
        if not self._booted:
            return
        logger.info("ServiceRegistry: shutting down …")
        # Services in reverse dependency order
        if self._ambient_manager is not None and self._ambient_manager.is_running:
            self._ambient_manager.stop()
        self._ambient_manager = None
        self._analyzer = None
        self._monitor = None
        self._router = None
        self._gateway = None
        self._embedder = None
        self._controller = None
        self._booted = False
        logger.info("ServiceRegistry: shutdown complete.")

    def health_check(self) -> HealthStatus:
        """
        Non-destructive readiness probe.

        Returns a ``HealthStatus`` with per-service flags. Never raises —
        failures are captured into the status object (constitution rule 9).

        Returns
        -------
        HealthStatus
        """
        notes: list[str] = []

        # Ollama reachable?
        ollama_ok = False
        if self._embedder is not None:
            try:
                ollama_ok = self._embedder.health_check()
            except Exception as exc:
                notes.append(f"Ollama health probe error: {exc}")
        else:
            notes.append("Ollama embedder not initialised — call boot() first.")

        if not ollama_ok:
            notes.append(
                "Ollama is not reachable at 127.0.0.1:11434. "
                "Capabilities requiring embeddings or classification will fail gracefully."
            )

        # ChromaDB ready?
        chroma_ok = False
        if self._controller is not None:
            try:
                count = len(self._controller.registered_collections)
                chroma_ok = count == 4
                if not chroma_ok:
                    notes.append(
                        f"ChromaDB has {count}/4 collections — expected 4."
                    )
            except Exception as exc:
                notes.append(f"ChromaDB health probe error: {exc}")
        else:
            notes.append("ChromaController not initialised — call boot() first.")

        degraded = not ollama_ok or not chroma_ok
        return HealthStatus(
            ollama_reachable=ollama_ok,
            chroma_ready=chroma_ok,
            degraded=degraded,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Service accessors (typed, guarded)
    # ------------------------------------------------------------------

    def _require_booted(self, name: str) -> None:
        if not self._booted:
            raise RuntimeError(
                f"ServiceRegistry: cannot access '{name}' — call boot() first."
            )

    @property
    def config(self) -> APIConfig:
        return self._config

    @property
    def controller(self) -> ChromaController:
        self._require_booted("controller")
        assert self._controller is not None
        return self._controller

    @property
    def embedder(self) -> OllamaEmbeddingWrapper:
        self._require_booted("embedder")
        assert self._embedder is not None
        return self._embedder

    @property
    def gateway(self) -> OllamaModelGateway:
        self._require_booted("gateway")
        assert self._gateway is not None
        return self._gateway

    @property
    def router(self) -> ClassificationRouter:
        self._require_booted("router")
        assert self._router is not None
        return self._router

    @property
    def monitor(self) -> WorkflowMonitor:
        self._require_booted("monitor")
        assert self._monitor is not None
        return self._monitor

    @property
    def analyzer(self) -> StrategicAssetAnalyzer:
        self._require_booted("analyzer")
        assert self._analyzer is not None
        return self._analyzer

    @property
    def ambient_manager(self) -> AmbientInteractionManager:
        self._require_booted("ambient_manager")
        assert self._ambient_manager is not None
        return self._ambient_manager

    @property
    def is_booted(self) -> bool:
        return self._booted


__all__ = ["ServiceRegistry", "HealthStatus"]
