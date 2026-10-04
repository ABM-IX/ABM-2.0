"""
tests/test_memory_pressure_launcher.py
========================================
Gate: ABMLauncher housekeeper memory pressure logic.

Verifies:
  1. Housekeeper pauses when available RAM < 15%.
  2. Housekeeper stays paused in the dead zone (15–20% RAM).
  3. Housekeeper resumes above 20%.
  4. Ollama is never contacted during memory pressure (no unload call).
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.launcher import ABMLauncher


class TestMemoryPressureLauncher(unittest.TestCase):
    @patch('abm.launcher.psutil.virtual_memory')
    def test_memory_pressure_pauses_and_resumes(self, mock_vm):
        # Simulate memory changes: 1st loop low memory, 2nd loop normal memory, 3rd loop exit
        mock_mem_low = MagicMock()
        mock_mem_low.total = 100
        mock_mem_low.available = 10  # 10%
        
        mock_mem_normal = MagicMock()
        mock_mem_normal.total = 100
        mock_mem_normal.available = 50  # 50%
        
        mock_vm.side_effect = [mock_mem_low, mock_mem_normal, mock_mem_normal]

        launcher = ABMLauncher(project_root=".")
        launcher.watcher = MagicMock()
        launcher.sync_server = MagicMock()
        launcher.web_server = MagicMock()
        
        launcher.registry = MagicMock()
        mock_housekeeper = MagicMock()
        launcher.registry._ambient_manager = MagicMock()
        launcher.registry._ambient_manager._writer._housekeeper = mock_housekeeper

        loop_count = [0]
        def side_effect(timeout):
            loop_count[0] += 1
            if loop_count[0] >= 2:
                launcher.stop_event.set()
        
        with patch.object(launcher.stop_event, 'wait', side_effect=side_effect):
            launcher.start()
            if launcher.housekeeper_thread:
                launcher.housekeeper_thread.join(timeout=2.0)

        # Housekeeper should be called once (during normal memory loop)
        mock_housekeeper.run_if_due.assert_called_once()

    @patch('abm.launcher.psutil.virtual_memory')
    def test_memory_pressure_hysteresis_dead_zone(self, mock_vm):
        # Simulate memory changes: 
        # 1. low memory (10%) -> pause
        # 2. hover memory (18%) -> dead zone (no resume)
        # 3. normal memory (30%) -> resume
        mock_mem_low = MagicMock()
        mock_mem_low.total = 100
        mock_mem_low.available = 10
        
        mock_mem_hover = MagicMock()
        mock_mem_hover.total = 100
        mock_mem_hover.available = 18

        mock_mem_normal = MagicMock()
        mock_mem_normal.total = 100
        mock_mem_normal.available = 30
        
        mock_vm.side_effect = [mock_mem_low, mock_mem_hover, mock_mem_normal, mock_mem_normal]

        launcher = ABMLauncher(project_root=".")
        launcher.watcher = MagicMock()
        launcher.sync_server = MagicMock()
        launcher.web_server = MagicMock()
        
        launcher.registry = MagicMock()
        mock_housekeeper = MagicMock()
        launcher.registry._ambient_manager = MagicMock()
        launcher.registry._ambient_manager._writer._housekeeper = mock_housekeeper

        loop_count = [0]
        def side_effect(timeout):
            loop_count[0] += 1
            if loop_count[0] >= 3:
                launcher.stop_event.set()
        
        with patch.object(launcher.stop_event, 'wait', side_effect=side_effect):
            with self.assertLogs('abm.launcher', level='INFO') as log:
                launcher.start()
                if launcher.housekeeper_thread:
                    launcher.housekeeper_thread.join(timeout=2.0)

        mock_housekeeper.run_if_due.assert_called_once()
        dead_zone_logged = any("Memory dead zone active" in message for message in log.output)
        self.assertTrue(dead_zone_logged)

    @patch('abm.launcher.psutil.virtual_memory')
    def test_memory_pressure_does_not_contact_ollama(self, mock_vm):
        """Under memory pressure, the launcher must NOT call Ollama's API to unload model."""
        mock_mem_low = MagicMock()
        mock_mem_low.total = 100
        mock_mem_low.available = 5  # 5% — critical pressure
        
        mock_mem_normal = MagicMock()
        mock_mem_normal.total = 100
        mock_mem_normal.available = 50

        mock_vm.side_effect = [mock_mem_low, mock_mem_normal]

        launcher = ABMLauncher(project_root=".")
        launcher.watcher = MagicMock()
        launcher.sync_server = MagicMock()
        launcher.web_server = MagicMock()
        launcher.registry = MagicMock()
        launcher.registry._ambient_manager = None

        loop_count = [0]
        def side_effect(timeout):
            loop_count[0] += 1
            launcher.stop_event.set()

        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch.object(launcher.stop_event, 'wait', side_effect=side_effect):
            launcher.start()
            if launcher.housekeeper_thread:
                launcher.housekeeper_thread.join(timeout=2.0)

        # Ollama should never be called during memory pressure
        mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
