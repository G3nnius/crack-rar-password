#!/usr/bin/env python3
"""Self-check for RARNinja: cracks a known encrypted fixture and confirms
early-stop / not-found behaviour. Run:  python3 tests/test_rarninja.py

Uses the committed fixture tests/fixtures/locked.rar (password 'hunter2',
header-encrypted) so it only needs a RAR backend (this repo ships bin/unrar).
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import RARNinja as rn  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
RAR = os.path.join(FIX, "locked.rar")
WORDS = os.path.join(FIX, "words.txt")


class TestRARNinja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool, cls.family = rn.detect_backend()
        if not cls.tool:
            raise unittest.SkipTest("no RAR backend found")

    def test_finds_known_password(self):
        hit, tried, _ = rn.crack(RAR, WORDS, self.tool, self.family,
                                 workers=4, progress=False)
        self.assertEqual(hit, "hunter2")
        self.assertGreaterEqual(tried, 1)

    def test_not_found(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("nope\nwrong\nbadpass\n")
            path = f.name
        try:
            hit, tried, _ = rn.crack(RAR, path, self.tool, self.family,
                                     workers=4, progress=False)
            self.assertIsNone(hit)
            self.assertEqual(tried, 3)
        finally:
            os.unlink(path)

    def test_extraction_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = rn.make_extract_cmd(self.tool, self.family, RAR, "hunter2", d)
            import subprocess
            rc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode
            self.assertEqual(rc, 0)
            self.assertIn("secret.txt", os.listdir(d))


if __name__ == "__main__":
    unittest.main(verbosity=2)
