import unittest
from abm.companion.file_watcher import _is_excluded

class TestFileWatcherExclusion(unittest.TestCase):
    def test_memory_is_excluded(self):
        """Verify that changes inside the memory/ directory are excluded."""
        self.assertTrue(_is_excluded("memory/chroma.sqlite3"))
        self.assertTrue(_is_excluded("memory/chroma_store/chroma.sqlite3"))
        self.assertTrue(_is_excluded("/var/lib/abm/memory/chroma_store/chroma.sqlite3"))
        self.assertTrue(_is_excluded("C:\\Projects\\ABM-2.0\\memory\\chroma_store\\chroma.sqlite3"))
        
    def test_other_paths_are_not_excluded(self):
        """Verify that standard code paths are not excluded."""
        self.assertFalse(_is_excluded("src/main.py"))
        self.assertFalse(_is_excluded("C:\\Projects\\ABM-2.0\\abm\\launcher.py"))

if __name__ == "__main__":
    unittest.main()
