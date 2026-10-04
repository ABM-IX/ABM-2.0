import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.clients.console.main import _repl_mode, _build_parser

class TestConsoleRepl(unittest.TestCase):
    @patch('builtins.input', side_effect=["ask what's on my plate today", "exit"])
    @patch('abm.clients.console.main._dispatch')
    def test_repl_natural_language_apostrophe(self, mock_dispatch, mock_input):
        registry = MagicMock()
        parser = _build_parser()
        
        # We need to mock print so it doesn't clutter output during testing
        with patch('builtins.print'):
            _repl_mode(registry, parser)
            
        mock_dispatch.assert_called_once()
        args = mock_dispatch.call_args[0][0]
        self.assertEqual(args.command, "ask")
        self.assertEqual(" ".join(args.question), "what's on my plate today")

if __name__ == "__main__":
    unittest.main()
