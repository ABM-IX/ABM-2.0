"""
abm/launcher.py
===============
Single entry point that starts all ABM background threads inside one process:
1. WorkspaceFileWatcher
2. Mobile Sync Server
3. Retention Housekeeper periodic loop

Groq is the sole reasoning provider. Ollama is not started, pre-warmed, or
managed by this launcher. Set GROQ_API_KEY in the environment before running.

Handles clean shutdown on SIGINT/SIGTERM to prevent orphaned threads or file locks.
"""
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import psutil
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# RAM guard — called before any explicit model load
# ---------------------------------------------------------------------------

MIN_RAM_MB_FOR_LOAD: float = 2048.0  # Minimum free RAM (MB) to attempt model load


def check_available_ram_before_load(model_name: str) -> bool:
    """
    Check whether there is sufficient free RAM to safely load ``model_name``.

    Uses psutil to read the system's available (not just free) memory.
    Returns True if enough RAM is available, False and logs a warning if not.
    Caller should skip the load if this returns False.

    Parameters
    ----------
    model_name : str
        The model we are about to load — used only for log context.
    """
    try:
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024 * 1024)
        if available_mb < MIN_RAM_MB_FOR_LOAD:
            logger.warning(
                "[ABM Launcher] check_available_ram_before_load: only %.0f MB available "
                "(minimum: %.0f MB). Skipping explicit load of '%s' to avoid OOM.",
                available_mb, MIN_RAM_MB_FOR_LOAD, model_name,
            )
            return False
        logger.info(
            "[ABM Launcher] check_available_ram_before_load: %.0f MB available — OK to load '%s'.",
            available_mb, model_name,
        )
        return True
    except Exception as exc:
        logger.warning(
            "[ABM Launcher] check_available_ram_before_load: psutil error (%s) — proceeding with load.",
            exc,
        )
        return True  # Fail open: if we can't check, don't block the boot
from http.server import HTTPServer
from pathlib import Path
from typing import Any

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.companion.watch_daemon import build_coordinator, _make_on_code_change, _make_on_telemetry_event
from abm.companion.file_watcher import WorkspaceFileWatcher

import abm.clients.web.main as web_main
from abm.clients.web.main import ThreadingHTTPServer, ABMWebAPIHandler
from abm.mobile.sync_server import SyncServerHandler, CONFIG_FILE as SYNC_CONFIG_FILE

logger = logging.getLogger(__name__)

class ABMLauncher:
    def __init__(self, project_root: str, sync_host: str = "0.0.0.0", sync_port: int = 8765, housekeeper_interval: float = 300.0) -> None:
        self.project_root = Path(project_root)
        self.sync_host = sync_host
        self.sync_port = sync_port
        self.housekeeper_interval = housekeeper_interval
        
        config = APIConfig(model_gateway_provider="groq")
        self.registry = ServiceRegistry(config)
        
        self.sync_server: HTTPServer | None = None
        self.web_server: ThreadingHTTPServer | None = None
        self.watcher = None
        self.sync_thread: threading.Thread | None = None
        self.web_thread: threading.Thread | None = None
        self.housekeeper_thread: threading.Thread | None = None
        
        self.stop_event = threading.Event()
        
        self.watch_paths: list[str] = []

    def boot(self) -> None:
        """Initialize all components but do not start background threads yet."""
        print("\n[ABM Launcher] Booting with Groq as sole reasoning provider.", flush=True)
        print("[ABM Launcher] Ollama is not started or required.", flush=True)
        
        self.registry.boot()
        
        # 1. Setup Watcher
        watch_config_path = self.project_root / ".abm_watch_paths.json"
        if watch_config_path.exists():
            with open(watch_config_path, "r", encoding="utf-8") as f:
                self.watch_paths = json.load(f).get("watch_paths", [])
        else:
            self.watch_paths = [str(self.project_root)]
            
        coordinator = build_coordinator(
            chroma_dir=self.registry._config.chroma_persist_directory,
            ollama_url=self.registry._config.ollama_base_url,
            git_path=str(self.project_root)
        )
        
        self.watcher = WorkspaceFileWatcher(
            watch_paths=self.watch_paths,
            on_code_change=_make_on_code_change(coordinator),
            on_telemetry_event=_make_on_telemetry_event(coordinator),
            debounce_seconds=1.0,
        )
        
        # 2. Setup Sync Server
        sync_config_path = self.project_root / SYNC_CONFIG_FILE
        if sync_config_path.exists():
            with open(sync_config_path, "r", encoding="utf-8") as f:
                pairing_config = json.load(f)
        else:
            pairing_config = {}
            
        SyncServerHandler.registry = self.registry
        SyncServerHandler.pairing_config = pairing_config
        self.sync_server = HTTPServer((self.sync_host, self.sync_port), SyncServerHandler)
        
        # 3. Setup Web API Server
        web_main.registry = self.registry
        self.web_server = ThreadingHTTPServer(('127.0.0.1', 8080), ABMWebAPIHandler)
        
    def start(self) -> None:
        """Start all background threads."""
        if not self.watcher or not self.sync_server:
            raise RuntimeError("Launcher not booted.")
            
        # Start watcher
        self.watcher.start()
        
        # Start sync server
        self.sync_thread = threading.Thread(target=self.sync_server.serve_forever, daemon=True)
        self.sync_thread.start()
        
        # Start Web API server
        if self.web_server:
            self.web_thread = threading.Thread(target=self.web_server.serve_forever, daemon=True)
            self.web_thread.start()
        
        # Start housekeeper loop
        def _loop() -> None:
            was_paused = False
            while not self.stop_event.is_set():
                try:
                    mem = psutil.virtual_memory()
                    available_pct = (mem.available / mem.total) * 100
                    
                    if available_pct < 15.0:
                        if not was_paused:
                            logger.warning("[ABM Launcher] Memory pressure critical (%.1f%% available). Pausing housekeeper.", available_pct)
                            was_paused = True
                    elif was_paused and available_pct < 20.0:
                        logger.info("[ABM Launcher] Memory dead zone active (%.1f%% available). Waiting for 20.0%% to resume.", available_pct)
                    else:
                        if was_paused:
                            logger.info("[ABM Launcher] Memory recovered (%.1f%% available). Resuming housekeeper.", available_pct)
                            was_paused = False
                        
                        # pylint: disable=protected-access
                        if self.registry._ambient_manager:
                            self.registry._ambient_manager._writer._housekeeper.run_if_due()
                except Exception as e:
                    logger.error("Housekeeper error: %s", e)
                
                # Check memory pressure periodically; run_if_due manages the housekeeper interval internally.
                self.stop_event.wait(15.0)
                
        self.housekeeper_thread = threading.Thread(target=_loop, daemon=True)
        self.housekeeper_thread.start()
        
        print(f"\n[ABM Launcher] Running: WorkspaceWatcher({len(self.watch_paths)} paths) | WebAPI(127.0.0.1:8080) | SyncServer({self.sync_host}:{self.sync_port}) | RetentionHousekeeper({self.housekeeper_interval}s loop)\n", flush=True)

    def stop(self) -> None:
        """Cleanly shut down all threads and release resources."""
        print("\n[ABM Launcher] Shutting down cleanly...", flush=True)
        self.stop_event.set()
        
        if self.watcher:
            self.watcher.stop()
            
        if self.sync_server:
            # shutdown() blocks until serve_forever() completes, so we run it in a thread 
            # if we are being called from a signal handler, but wait, it's safer to just run it in a thread anyway.
            threading.Thread(target=self.sync_server.shutdown, daemon=True).start()
            if self.sync_thread:
                self.sync_thread.join(timeout=2.0)
            self.sync_server.server_close()
            
        if self.web_server:
            threading.Thread(target=self.web_server.shutdown, daemon=True).start()
            if self.web_thread:
                self.web_thread.join(timeout=2.0)
            self.web_server.server_close()
            
        if self.housekeeper_thread:
            self.housekeeper_thread.join(timeout=2.0)
            
        self.registry.shutdown()
        print("[ABM Launcher] Shutdown complete.", flush=True)


def main() -> None:
    # Load .env variables before any other initialization
    load_dotenv()

    # The rest of the setup...
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    project_root = str(Path(__file__).resolve().parent.parent)
    
    launcher = ABMLauncher(project_root=project_root)
    
    try:
        launcher.boot()
        launcher.start()
    except Exception as e:
        logger.error("Failed to start ABM Launcher: %s", e)
        sys.exit(1)
        
    def _handle_signal(signum: Any, frame: Any) -> None:
        launcher.stop()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        launcher.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
