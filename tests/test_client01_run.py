"""
tests/test_client01_run.py
=============================
Integration test for the 'run' command.
"""

import os
import sys
import time
import unittest
import urllib.request

import pytest

def is_ollama_running():
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.0)
        return True
    except Exception:
        return False

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.api.capabilities import runTask, RunTaskResult
from abm.api.core.registry import ServiceRegistry
from abm.api.core.config import APIConfig
from abm.strategic_wing.workflow_monitor import TaskState


class TestClient01Run(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We need a booted registry to run the real execution loop.
        cls.registry = ServiceRegistry(APIConfig())
        cls.registry.boot()
        
    @classmethod
    def tearDownClass(cls):
        cls.registry.shutdown()

    @unittest.skipIf(not is_ollama_running(), "Ollama not running")
    def test_runTask_end_to_end(self):
        # Dispatch a trivial python script
        objective = "write a python script that prints hello world"
        result = runTask(objective, registry=self.registry)
        
        self.assertIsInstance(result, RunTaskResult)
        self.assertFalse(result.degraded)
        self.assertTrue(result.task_id)
        
        # Poll the monitor to wait for the background thread to finish
        max_retries = 60
        task_finished = False
        record = None
        for _ in range(max_retries):
            # Check monitor registry
            record = self.registry.monitor._registry.get(result.task_id)
            if record and record.state in (TaskState.PASSED, TaskState.QUARANTINED):
                task_finished = True
                break
            time.sleep(1)
            
        self.assertTrue(task_finished, "Background task did not finish in time")
        
        # Verify it passed the gate
        self.assertEqual(record.state, TaskState.PASSED)
        self.assertIsNotNone(record.gate_result)
        self.assertTrue(record.gate_result.passed)
        self.assertIsNotNone(record.validation_scores)
        self.assertEqual(record.validation_scores.test_succ, 1.0)
        self.assertIsNotNone(record.execution_result)
        self.assertEqual(record.execution_result.exit_code, 0)
        self.assertIn("hello", record.execution_result.stdout.lower())
        self.assertIn("world", record.execution_result.stdout.lower())

    @unittest.skipIf(not is_ollama_running(), "Ollama not running")
    def test_answerQuestion_hallucination_prevention(self):
        from abm.api.capabilities import answerQuestion
        result = answerQuestion("what does ABM stand for?", registry=self.registry)
        
        self.assertFalse(result.degraded)
        synthesis_lower = result.synthesis.lower()
        
        # It must reference Arabang's initials OR state it doesn't have the info and ask to clarify
        is_safe = (
            ("arabang" in synthesis_lower and "initial" in synthesis_lower) or
            ("clarify" in synthesis_lower) or
            ("don't have" in synthesis_lower) or
            ("cannot answer" in synthesis_lower)
        )
        self.assertTrue(is_safe, f"Hallucination caught! Synthesis was: {result.synthesis}")

if __name__ == "__main__":
    unittest.main()
