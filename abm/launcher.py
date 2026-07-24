"""
abm/launcher.py
===============
Single entry point that starts all ABM background threads inside one process:
1. WorkspaceFileWatcher
2. Mobile Sync Server
3. Retention Housekeeper periodic loop

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
from http.server import HTTPServer
from pathlib import Path
from typing import Any

from abm.api.core.registry import ServiceRegistry
from abm.companion.watch_daemon import build_coordinator, _make_on_code_change, _make_on_telemetry_event
from abm.companion.file_watcher import WorkspaceFileWatcher
from abm.mobile.sync_server import SyncServerHandler, CONFIG_FILE as SYNC_CONFIG_FILE

logger = logging.getLogger(__name__)

class ABMLauncher:
    def __init__(self, project_root: str, sync_host: str = "0.0.0.0", sync_port: int = 8765, housekeeper_interval: float = 300.0) -> None:
        self.project_root = Path(project_root)
        self.sync_host = sync_host
        self.sync_port = sync_port
        self.housekeeper_interval = housekeeper_interval
        
        self.registry = ServiceRegistry()
        self.watcher: WorkspaceFileWatcher | None = None
        self.sync_server: HTTPServer | None = None
        self.sync_thread: threading.Thread | None = None
        
        self.stop_event = threading.Event()
        self.housekeeper_thread: threading.Thread | None = None
        
        self.watch_paths: list[str] = []
        self.owns_ollama: bool = False
        self.ollama_proc: subprocess.Popen | None = None

    def boot(self) -> None:
        """Initialize all components but do not start background threads yet."""
        # 0. Ollama check, start, and pre-warm
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.0)
            print("\n[ABM Launcher] Ollama already running.", flush=True)
        except Exception:
            print("\n[ABM Launcher] Started Ollama...", flush=True)
            try:
                self.ollama_proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                print("\n[ABM Launcher] Ollama not found on PATH — install it or add it to PATH", flush=True)
                sys.exit(1)
            self.owns_ollama = True
            for _ in range(30):
                try:
                    urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.0)
                    break
                except Exception:
                    time.sleep(0.5)

        print("[ABM Launcher] Pre-warming phi3:mini...", flush=True)
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps({"model": "phi3:mini", "prompt": "hi", "stream": False}).encode(),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=30.0)
            print("[ABM Launcher] phi3:mini pre-warmed.", flush=True)
        except Exception as e:
            logger.warning(f"Pre-warming failed: {e}")

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
        
    def start(self) -> None:
        """Start all background threads."""
        if not self.watcher or not self.sync_server:
            raise RuntimeError("Launcher not booted.")
            
        # Start watcher
        self.watcher.start()
        
        # Start sync server
        self.sync_thread = threading.Thread(target=self.sync_server.serve_forever, daemon=True)
        self.sync_thread.start()
        
        # Start housekeeper loop
        def _loop() -> None:
            while not self.stop_event.is_set():
                try:
                    # pylint: disable=protected-access
                    if self.registry._ambient_manager:
                        self.registry._ambient_manager._writer._housekeeper.run_if_due()
                except Exception as e:
                    logger.error("Housekeeper error: %s", e)
                self.stop_event.wait(self.housekeeper_interval)
                
        self.housekeeper_thread = threading.Thread(target=_loop, daemon=True)
        self.housekeeper_thread.start()
        
        print(f"\n[ABM Launcher] Running: WorkspaceWatcher({len(self.watch_paths)} paths) | SyncServer({self.sync_host}:{self.sync_port}) | RetentionHousekeeper({self.housekeeper_interval}s loop)\n", flush=True)

    def stop(self) -> None:
        """Cleanly shut down all threads and release resources."""
        print("\n[ABM Launcher] Shutting down cleanly...", flush=True)
        self.stop_event.set()
        
        if self.owns_ollama and self.ollama_proc:
            print("[ABM Launcher] Stopping launcher-managed Ollama...", flush=True)
            self.ollama_proc.terminate()
            try:
                self.ollama_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.ollama_proc.kill()
        
        if self.watcher:
            self.watcher.stop()
            
        if self.sync_server:
            # shutdown() blocks until serve_forever() completes, so we run it in a thread 
            # if we are being called from a signal handler, but wait, it's safer to just run it in a thread anyway.
            threading.Thread(target=self.sync_server.shutdown, daemon=True).start()
            if self.sync_thread:
                self.sync_thread.join(timeout=2.0)
            self.sync_server.server_close()
            
        if self.housekeeper_thread:
            self.housekeeper_thread.join(timeout=2.0)
            
        self.registry.shutdown()
        print("[ABM Launcher] Shutdown complete.", flush=True)


def main() -> None:
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
