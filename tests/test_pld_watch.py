"""Offline tests for pld-watch. No network: EOL data is stubbed."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pld_watch as pw


class TestVersionParsing(unittest.TestCase):
    def test_major_minor(self):
        self.assertEqual(pw._major_minor("v16.20.2"), "16.20")
        self.assertEqual(pw._major_minor("16"), "16")
        self.assertEqual(pw._major_minor("^12.0.0"), "12.0")
        self.assertEqual(pw._major_minor("not-a-version"), "")
        self.assertEqual(pw._major_minor(""), "")


class TestDetection(unittest.TestCase):
    def _root(self, files):
        d = Path(tempfile.mkdtemp())
        for name, body in files.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        return d

    def test_nvmrc(self):
        r = self._root({".nvmrc": "16\n"})
        got = pw.detect(r)
        self.assertEqual([(g["slug"], g["version"]) for g in got], [("nodejs", "16")])

    def test_go_mod(self):
        r = self._root({"go.mod": "module x\n\ngo 1.19\n"})
        got = pw.detect(r)
        self.assertIn(("go", "1.19"), [(g["slug"], g["version"]) for g in got])

    def test_package_json_frameworks(self):
        r = self._root({"package.json": json.dumps(
            {"dependencies": {"next": "12.0.0", "left-pad": "1.0.0"}})})
        slugs = [g["slug"] for g in pw.detect(r)]
        self.assertIn("nextjs", slugs)
        self.assertNotIn("left-pad", slugs)  # unknown packages are ignored

    def test_requirements(self):
        r = self._root({"requirements.txt": "django==3.2.0\nrequests==2.0.0\n"})
        slugs = [g["slug"] for g in pw.detect(r)]
        self.assertIn("django", slugs)

    def test_dockerfile_from(self):
        r = self._root({"Dockerfile": "FROM python:3.7-slim\nRUN echo hi\n"})
        got = pw.detect(r)
        self.assertIn(("python", "3.7"), [(g["slug"], g["version"]) for g in got])

    def test_dedup(self):
        r = self._root({".nvmrc": "16", "Dockerfile": "FROM nodejs:16\n"})
        got = pw.detect(r)
        self.assertEqual(len([g for g in got if g["slug"] == "nodejs"]), 1)

    def test_empty_project(self):
        r = self._root({"README.md": "nothing here"})
        self.assertEqual(pw.detect(r), [])


class TestAssess(unittest.TestCase):
    def setUp(self):
        self._real = pw.eol_product

    def tearDown(self):
        pw.eol_product = self._real

    def _stub(self, releases):
        pw.eol_product = lambda slug, refresh=False: {"releases": releases}

    def test_eol_flagged(self):
        self._stub([{"name": "26", "isEol": False, "eolFrom": "2029-04-30"},
                    {"name": "16", "isEol": True, "eolFrom": "2023-09-11"}])
        rows = pw.assess([{"kind": "runtime", "name": "Node.js", "slug": "nodejs",
                           "version": "16", "source": ".nvmrc"}])
        self.assertEqual(rows[0]["status"], "eol")
        self.assertEqual(rows[0]["eol_date"], "2023-09-11")
        self.assertEqual(rows[0]["latest"], "26")

    def test_supported(self):
        self._stub([{"name": "24", "isEol": False, "eolFrom": "2099-01-01"}])
        rows = pw.assess([{"kind": "runtime", "name": "Node.js", "slug": "nodejs",
                           "version": "24", "source": ".nvmrc"}])
        self.assertEqual(rows[0]["status"], "supported")

    def test_unknown_when_absent(self):
        self._stub([{"name": "99", "isEol": False, "eolFrom": None}])
        rows = pw.assess([{"kind": "runtime", "name": "Node.js", "slug": "nodejs",
                           "version": "3", "source": ".nvmrc"}])
        self.assertEqual(rows[0]["status"], "unknown")

    def test_offline_returns_unknown_not_crash(self):
        pw.eol_product = lambda slug, refresh=False: None
        rows = pw.assess([{"kind": "runtime", "name": "Node.js", "slug": "nodejs",
                           "version": "16", "source": ".nvmrc"}])
        self.assertEqual(rows[0]["status"], "unknown")


class TestConstants(unittest.TestCase):
    def test_pld_date_is_correct(self):
        # Directive (EU) 2024/2853 applies from 9 December 2026.
        self.assertEqual(pw.PLD_APPLIES, date(2026, 12, 9))


if __name__ == "__main__":
    unittest.main(verbosity=2)
