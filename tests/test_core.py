from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from git_churn_map.core import Hotspot, collect_hotspots, parse_numstat_fields, to_json, to_markdown


class NumstatTests(unittest.TestCase):
    def test_parses_unicode_tab_and_newline_paths(self):
        rows = parse_numstat_fields([
            b"3\t1\tspace name.py",
            "2\t0\tтаб\tfile.py".encode(),
            b"1\t1\tline\nbreak.py",
            b"-\t-\tbinary.dat",
        ])
        self.assertEqual(rows, [
            ("space name.py", 3, 1),
            ("таб\tfile.py", 2, 0),
            ("line\nbreak.py", 1, 1),
        ])

    def test_invalid_and_negative_records_are_ignored(self):
        self.assertEqual(parse_numstat_fields([b"bad", b"-1\t0\tx", b"0\t-\tx"]), [])

    def test_markdown_escapes_untrusted_path_content(self):
        report = to_markdown([Hotspot("<img>|`x`\nnext.py", 2, 4, 3)], 3)
        self.assertIn("&lt;img&gt;&#124;&#96;x&#96;\\nnext.py", report)
        self.assertNotIn("<img>", report)
        self.assertNotIn("\nnext.py", report)

    def test_json_is_valid_and_deterministic(self):
        rows = [Hotspot("src/a.py", 2, 3, 1)]
        rendered = to_json(rows, 4)
        self.assertEqual(rendered, to_json(rows, 4))
        self.assertEqual(json.loads(rendered)["hotspots"][0]["churn"], 4)


class GitHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "file.txt").write_text("one\n", encoding="utf-8")
        self.commit("first")
        (self.repo / "file.txt").write_text("one\ntwo\n", encoding="utf-8")
        (self.repo / "other.txt").write_text("x\n", encoding="utf-8")
        self.commit("second")
        (self.repo / "file.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        self.commit("third")
        (self.repo / "binary.dat").write_bytes(b"\x00\x01\xff")
        self.commit("binary")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-q", "-m", message)

    def test_collects_ranked_churn_and_skips_binary_lines(self):
        rows, commits = collect_hotspots(self.repo, limit=10)
        self.assertEqual(commits, 4)
        self.assertEqual(rows[0], Hotspot("file.txt", 3, 3, 0))
        self.assertNotIn("binary.dat", [row.path for row in rows])

    def test_glob_exclusion_and_limit(self):
        rows, _ = collect_hotspots(self.repo, exclude=["file.*"])
        self.assertNotIn("file.txt", [row.path for row in rows])
        with self.assertRaises(ValueError):
            collect_hotspots(self.repo, limit=0)
        with self.assertRaises(ValueError):
            collect_hotspots(self.repo, max_commits=50_001)

    def test_rejects_non_repository_and_bad_path(self):
        with self.assertRaises(ValueError):
            collect_hotspots(self.repo.parent / "not-a-repo")

    def test_cli_emits_machine_readable_report(self):
        from git_churn_map.cli import main
        target = self.repo / "report.json"
        code = main([str(self.repo), "--format", "json", "--output", str(target)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(target.read_text())["commits_scanned"], 4)


if __name__ == "__main__":
    unittest.main()
