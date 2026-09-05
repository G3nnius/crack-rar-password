#!/usr/bin/env python3
"""Self-check for RARNinja. Run:  python3 tests/test_rarninja.py

Cracks committed encrypted fixtures (password 'hunter2' and '42'), and exercises
the dictionary generator, the iterable candidate source, and the history store.
Only needs a RAR backend (this repo ships one per platform under bin/).
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import RARNinja as rn  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
RAR = os.path.join(FIX, "locked.rar")       # pw: hunter2
WORDS = os.path.join(FIX, "words.txt")
DIGITS_RAR = os.path.join(FIX, "digits.rar")  # pw: 42


class TestCrack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool, cls.family = rn.detect_backend()
        if not cls.tool:
            raise unittest.SkipTest("no RAR backend found")

    def test_finds_known_password(self):
        hit, tried, _ = rn.crack(RAR, WORDS, self.tool, self.family, workers=4, progress=False)
        self.assertEqual(hit, "hunter2")
        self.assertGreaterEqual(tried, 1)

    def test_not_found(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("nope\nwrong\nbadpass\n")
            path = f.name
        try:
            hit, tried, _ = rn.crack(RAR, path, self.tool, self.family, workers=4, progress=False)
            self.assertIsNone(hit)
            self.assertEqual(tried, 3)
        finally:
            os.unlink(path)

    def test_extraction_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = rn.make_extract_cmd(self.tool, self.family, RAR, "hunter2", d)
            rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode
            self.assertEqual(rc, 0)
            self.assertIn("secret.txt", os.listdir(d))

    def test_crack_via_generator(self):
        # brute-force digits 1..2 must find '42' in digits.rar
        src = rn.gen_candidates("digits", 1, 2)
        hit, tried, _ = rn.crack(DIGITS_RAR, src, self.tool, self.family, workers=4, progress=False)
        self.assertEqual(hit, "42")


class TestGenerator(unittest.TestCase):
    def test_count(self):
        self.assertEqual(rn.gen_count("digits", 1, 3), 10 + 100 + 1000)
        self.assertEqual(rn.gen_count("lower", 2, 2), 26 * 26)

    def test_candidates_match_count(self):
        got = list(rn.gen_candidates("digits", 1, 2))
        self.assertEqual(len(got), rn.gen_count("digits", 1, 2))
        self.assertIn("42", got)
        self.assertEqual(got[0], "0")

    def test_iterable_source_filters_blanks(self):
        self.assertEqual(list(rn.candidates(iter(["a", "", "b", ""]))), ["a", "b"])

    def test_to_file(self):
        with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            n = rn.gen_to_file(path, "digits", 1, 1)
            self.assertEqual(n, 10)
            with open(path) as fh:
                self.assertEqual(sum(1 for _ in fh), 10)
        finally:
            os.unlink(path)


class TestHistory(unittest.TestCase):
    def setUp(self):
        self._orig = rn.history_path
        self._tmp = tempfile.mktemp(suffix=".jsonl")
        rn.history_path = lambda: self._tmp

    def tearDown(self):
        rn.history_path = self._orig
        if os.path.isfile(self._tmp):
            os.unlink(self._tmp)

    def test_add_and_list(self):
        self.assertEqual(rn.history_list(), [])
        rn.history_add("/tmp/a.rar", "secret1")
        rn.history_add("/tmp/b.rar", "secret2")
        rows = rn.history_list()
        self.assertEqual([r["password"] for r in rows], ["secret1", "secret2"])
        self.assertTrue(rows[0]["archive"].endswith("a.rar"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
