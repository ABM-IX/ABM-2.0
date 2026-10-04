"""
tests/test_client01_ingest.py
=============================
Tests manual document ingestion for the ABM console client.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.api.core.registry import ServiceRegistry
from abm.clients.console.commands import cmd_ingest
from abm.memory.chroma_controller import (
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY,
)

class TestClient01IngestGate(unittest.TestCase):
    def setUp(self):
        self.registry = MagicMock(spec=ServiceRegistry)
        self.registry.controller = MagicMock()
        self.registry.embedder = MagicMock()
        self.registry.embedder.embed.return_value = [0.1] * 768

    @patch("abm.companion.ingestion_coordinator.pypdf")
    def test_ingest_document_pdf(self, mock_pypdf):
        mock_pdf_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Test PDF Content."
        mock_pdf_reader.pages = [mock_page]
        mock_pypdf.PdfReader.return_value = mock_pdf_reader

        test_file = Path("test_doc.pdf")
        test_file.touch()
        try:
            output = cmd_ingest(str(test_file), registry=self.registry)
            
            # Verify Stream B (Technical Mastery)
            self.assertIn("[OK]", output)
            self.registry.controller.add_document.assert_called()
            
            call_args = self.registry.controller.add_document.call_args[0]
            collection = call_args[0]
            self.assertEqual(collection, COLLECTION_TECHNICAL_MASTERY)
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_ingest_document_code(self):
        test_file = Path("test_code.py")
        test_file.write_text("def test(): pass")
        try:
            output = cmd_ingest(str(test_file), registry=self.registry)
            
            # Verify Stream A (Code Topologies)
            self.assertIn("[OK]", output)
            self.registry.controller.add_document.assert_called()
            
            call_collections = [call.args[0] for call in self.registry.controller.add_document.call_args_list]
            self.assertIn(COLLECTION_CODE_TOPOLOGIES, call_collections)
        finally:
            if test_file.exists():
                test_file.unlink()

if __name__ == "__main__":
    unittest.main()
