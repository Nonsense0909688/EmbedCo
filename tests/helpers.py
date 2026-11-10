import shutil
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_home():
    """A throwaway project home with the real blocks, boards and UI."""
    home = Path(tempfile.mkdtemp(prefix="cf_test_"))
    shutil.copytree(ROOT / "blocks", home / "blocks")
    shutil.copy(ROOT / "boards.yaml", home / "boards.yaml")
    (home / "ui").mkdir()
    shutil.copy(ROOT / "ui" / "index.html", home / "ui" / "index.html")
    return home


class HomeTestCase(unittest.TestCase):
    def setUp(self):
        self.home = make_home()
        self.addCleanup(shutil.rmtree, self.home, True)
