"""safe-merge dispatches pr-blocking-findings right before the merge (Q8): merge only on success; exit 3 keeps today's behaviour."""
import os, stat, subprocess, tempfile, unittest
from pathlib import Path

SAFE = Path(__file__).resolve().parents[1] / "safe-merge"
SHA = "a" * 40


def stub(path, body):
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class SafeMerge(unittest.TestCase):
    def run_merge(self, findings_rc):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        s, b = tmp / ".claude" / "scripts", tmp / "bin"
        s.mkdir(parents=True), b.mkdir()
        log = tmp / "log"
        stub(b / "gh", f'echo "gh $*" >> {log}\n[ "$2" = view ] && echo {SHA}\nexit 0\n')
        stub(s / "ci-gate", f'echo "#7 {SHA[:9]} GREEN"')
        stub(s / "behind-ok", 'echo "#7 OK behind=0"')
        stub(s / "conflict-scan", "exit 0")
        stub(s / "pr-coordinator", f'echo "findings $*" >> {log}; echo findings-output; exit {findings_rc}')
        env = {**os.environ, "HOME": str(tmp), "PATH": f"{b}:{os.environ['PATH']}"}
        out = subprocess.run(["bash", str(SAFE), "7"], env=env, capture_output=True, text=True).stdout
        return out, log.read_text(encoding="utf-8")

    def merged(self, calls):
        return "pr merge" in calls

    def test_findings_success_merges_after_the_gate_ran(self):
        out, calls = self.run_merge(0)
        self.assertIn("MERGED", out)
        self.assertLess(calls.index("--findings-gate 7"), calls.index("pr merge"))

    def test_findings_failure_blocks_the_merge(self):
        out, calls = self.run_merge(1)
        self.assertNotIn("MERGED", out)
        self.assertIn("SKIP findings gate", out)
        self.assertFalse(self.merged(calls))

    def test_not_applicable_before_cutover_keeps_current_behaviour(self):
        out, calls = self.run_merge(3)
        self.assertIn("MERGED", out)


if __name__ == "__main__":
    unittest.main()
