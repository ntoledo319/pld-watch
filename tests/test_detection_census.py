"""Detection census: a guard against silently detecting FEWER things.

The unit tests prove each parser works in isolation. They do not catch the
failure mode that actually bit this tool: a version-regex change that still
produced a plausible report, still exited 1, and quietly dropped one runtime.
Both runs looked credible. The empty result and the silent filter-out were the
same bytes in the report.

So this file pins an exact expected census over a fixture tree that exercises
every declaration form at once. If a refactor drops a detection, the count moves
and this fails with a diff naming exactly what disappeared - not a vague
"expected 7 got 6".
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pld_watch as pw

# (slug, version) -> the declaration form that must keep producing it.
# Adding a detector means adding a line here, deliberately.
EXPECTED = {
    ("nodejs", "16.20"): ".nvmrc v-prefixed, as nvm writes it",
    ("nodejs", "18.17"): "package.json engines caret range",
    ("python", "3.7"): "Dockerfile FROM tag",
    ("go", "1.19"): "go.mod directive",
    ("nextjs", "12.3"): "package.json dependency caret range",
    ("django", "3.2"): "requirements.txt pin",
    ("react", "17.0"): "package.json dependency tilde range",
}

FIXTURE = {
    ".nvmrc": "v16.20.2\n",  # nvm writes a v-prefix
    "go.mod": "module example.com/x\n\ngo 1.19\n",
    "Dockerfile": "FROM python:3.7-slim\nRUN echo build\n",
    "requirements.txt": "django==3.2.0\nrequests==2.31.0\n",
    "package.json": (
        '{"name":"fixture","engines":{"node":"^18.17.0"},'
        '"dependencies":{"next":"^12.3.1","react":"~17.0.2","left-pad":"1.0.0"}}'
    ),
}


class TestDetectionCensus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp())
        for name, body in FIXTURE.items():
            (d / name).write_text(body)
        cls.root = d
        cls.found = {(x["slug"], x["version"]) for x in pw.detect(d)}

    def test_no_detection_silently_disappeared(self):
        missing = {k: v for k, v in EXPECTED.items() if k not in self.found}
        self.assertFalse(
            missing,
            "\n\nA declaration form stopped being detected. This is the silent-drop\n"
            "failure mode - the tool would still print a plausible report.\n"
            "Lost:\n" + "\n".join(f"  {s} {v}  <- {why}" for (s, v), why in missing.items()),
        )

    def test_no_unreviewed_detection_appeared(self):
        extra = self.found - set(EXPECTED)
        self.assertFalse(
            extra,
            "\n\nNew detections appeared that are not in the census. If intentional,\n"
            "add them to EXPECTED with the declaration form they come from.\n"
            "New:\n" + "\n".join(f"  {s} {v}" for s, v in sorted(extra)),
        )

    def test_census_count_is_pinned(self):
        # A bare count, so a swap (one lost + one gained) still trips something.
        self.assertEqual(len(self.found), len(EXPECTED))

    def test_unknown_packages_are_not_detected(self):
        # left-pad is in the fixture deliberately: unmapped packages must not appear.
        self.assertNotIn("left-pad", {s for s, _ in self.found})


class TestRegressionCaretRanges(unittest.TestCase):
    """The specific bug, pinned forever - and an honest note on its blast radius.

    The original `_major_minor` used `re.match(r"v?(\\d+)...")`, which returns ''
    for any range prefix: '^12.3.1', '~17.0.2', '>=16 <18'.

    Worth being precise about why that did not show up as an obvious outage:
    `detect()` strips non-digits before calling this for package.json
    dependencies, so caret ranges survived THAT path. The function was still
    wrong, and one refactor that removed the pre-scrub - or any new caller
    passing a raw range - turns a latent bug into silently dropped findings
    with a report that still looks credible and still exits 1.

    These assertions pin the function's own contract so that cannot happen,
    independently of what any one caller happens to sanitise today.
    """

    def test_caret_range(self):
        self.assertEqual(pw._major_minor("^12.3.1"), "12.3")

    def test_tilde_range(self):
        self.assertEqual(pw._major_minor("~17.0.2"), "17.0")

    def test_v_prefixed_as_nvm_writes_it(self):
        self.assertEqual(pw._major_minor("v16.20.2"), "16.20")

    def test_compound_range(self):
        self.assertEqual(pw._major_minor(">=16 <18"), "16")

    def test_docker_suffix_tag(self):
        self.assertEqual(pw._major_minor("3.7-slim"), "3.7")

    def test_genuinely_absent_version_is_empty(self):
        # The one case that MUST stay empty - otherwise we invent findings.
        self.assertEqual(pw._major_minor("latest"), "")
        self.assertEqual(pw._major_minor(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
