"""
tests/test_launcher.py
Test for abm/launcher.py proving all three components start and stop cleanly.
"""
import threading
import time
from unittest.mock import patch, MagicMock

from abm.launcher import ABMLauncher

def test_launcher_starts_and_stops_cleanly(tmp_path):
    # Mock the ServiceRegistry and other dependencies so we don't actually bind to Ollama or ChromaDB
    with patch("abm.launcher.ServiceRegistry") as mock_registry_cls, \
         patch("abm.launcher.build_coordinator") as mock_build_coord, \
         patch("abm.launcher.WorkspaceFileWatcher") as mock_watcher_cls, \
         patch("abm.launcher.HTTPServer") as mock_http_server_cls, \
         patch("abm.launcher.psutil.virtual_memory") as mock_vm:
             
        mock_mem = MagicMock()
        mock_mem.total = 100
        mock_mem.available = 50
        mock_vm.return_value = mock_mem
        
        mock_registry = MagicMock()
        mock_registry_cls.return_value = mock_registry
        
        mock_watcher = MagicMock()
        mock_watcher_cls.return_value = mock_watcher
        
        mock_http_server = MagicMock()
        mock_http_server_cls.return_value = mock_http_server
        
        # We need a custom serve_forever that just blocks until shutdown is called
        serve_event = threading.Event()
        def fake_serve_forever():
            serve_event.wait()
            
        def fake_shutdown():
            serve_event.set()
            
        mock_http_server.serve_forever = fake_serve_forever
        mock_http_server.shutdown = fake_shutdown
        
        # We want to verify that run_if_due is called. 
        # But wait, our housekeeper thread loops every X seconds. Let's make it 0.1s for the test.
        launcher = ABMLauncher(
            project_root=str(tmp_path), 
            sync_host="127.0.0.1", 
            sync_port=9999, 
            housekeeper_interval=0.1
        )
        
        launcher.boot()
        
        assert launcher.watcher == mock_watcher
        assert launcher.sync_server == mock_http_server
        
        launcher.start()
        
        # Verify components started
        mock_watcher.start.assert_called_once()
        assert launcher.sync_thread is not None
        assert launcher.sync_thread.is_alive()
        assert launcher.housekeeper_thread is not None
        assert launcher.housekeeper_thread.is_alive()
        
        # Wait a tiny bit for the housekeeper loop to spin at least once
        time.sleep(0.25)
        
        # It should have called run_if_due at least once or twice
        # Since it's mocked, let's check if the mocked run_if_due was called
        # The registry was mocked, so we can assert on the mock path
        mock_run_if_due = mock_registry._ambient_manager._writer._housekeeper.run_if_due
        assert mock_run_if_due.called
        
        # Now stop
        launcher.stop()
        
        # Verify components stopped cleanly
        mock_watcher.stop.assert_called_once()
        mock_http_server.server_close.assert_called_once()
        
        # Threads should be dead
        launcher.sync_thread.join(timeout=1.0)
        launcher.housekeeper_thread.join(timeout=1.0)
        assert not launcher.sync_thread.is_alive()
        assert not launcher.housekeeper_thread.is_alive()
        mock_registry.shutdown.assert_called_once()
