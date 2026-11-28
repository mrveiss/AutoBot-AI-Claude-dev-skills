"""pr-coordinator: slot kept until merge (owner 2026-11-28), park = draft (AutoBot-AI#20825), start-CI vs advisory runs."""
import importlib.machinery, importlib.util, json, shutil, subprocess, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")
loader = importlib.machinery.SourceFileLoader("pr_coordinator_sp", PATH)
PC = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator_sp", loader))
loader.exec_module(PC)
HEAD = "b" * 40


class FakeR:
    def __init__(self, pr_holds=(), ttl=7200): self.pr_holds, self._ttl = set(pr_holds), ttl
    def exists(self, k): return k in {f"lg:hold:pr:{n}" for n in self.pr_holds}
    def ttl(self, k): return self._ttl


def pr(n, draft=False, parked=False):
    return {"number": n, "isDraft": draft, "labels": {"nodes": [{"name": "ci-parked"}] if parked else []}}


class Base(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._sh, self._dry = PC.sh, PC.DRY
        PC.sh = lambda *a, **k: self.calls.append(a) or ""
        PC.DRY = False
        self.addCleanup(lambda: (setattr(PC, "sh", self._sh), setattr(PC, "DRY", self._dry)))


class KeptSlots(Base):
    HELD = {1: {"by": PC.ME}, 2: {"by": PC.ME}, 3: {"by": "other"}}

    def test_kept_while_open_even_when_red_or_conflicting(self):
        self.assertEqual(PC.kept_slots(self.HELD, {1, 2, 3}, FakeR()), [1, 2])

    def test_freed_by_close_or_merge(self):
        self.assertEqual(PC.kept_slots(self.HELD, {2, 3}, FakeR()), [2])

    def test_freed_by_ledger_hold(self):
        self.assertEqual(PC.kept_slots(self.HELD, {1, 2}, FakeR(pr_holds=[1])), [2])

    def test_ttl_rearmed_only_when_low(self):
        PC.kept_slots(self.HELD, {1}, FakeR(ttl=100))
        self.assertTrue(any("ci-slot:1" in c and "hold" in c for c in self.calls))
        self.calls.clear()
        PC.kept_slots(self.HELD, {1}, FakeR(ttl=7200))
        self.assertEqual(self.calls, [])


class Park(Base):
    def test_parks_non_slot_ready_pr_only(self):
        log = []
        PC.park_phase([pr(1), pr(2), pr(3, draft=True), pr(4, draft=True, parked=True)], [1], log)
        self.assertIn(("gh", "pr", "ready", "--undo", "2", "--repo", PC.REPO), self.calls)
        self.assertEqual(len([c for c in self.calls if c[:3] == ("gh", "pr", "ready")]), 1)   # not #3 (author draft), not #4
        self.assertTrue(any("--add-label" in c and "2" in c for c in self.calls))

    def test_unparks_admitted_labelled_pr(self):
        PC.park_phase([pr(1, draft=True, parked=True), pr(2, draft=True)], [1, 2], [])
        self.assertIn(("gh", "pr", "ready", "1", "--repo", PC.REPO), self.calls)
        self.assertTrue(any("--remove-label" in c and "ci-parked" in c for c in self.calls))
        self.assertFalse([c for c in self.calls if c[:4] == ("gh", "pr", "ready", "2")])   # author's draft untouched

    def test_dry_only_logs(self):
        PC.DRY, log = True, []
        PC.park_phase([pr(1), pr(2, draft=True, parked=True)], [2], log)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(log), 2)


@unittest.skipUnless(shutil.which("jq"), "jq not installed")
class StartCiIgnoresAdvisory(Base):
    def count(self, runs):
        jq = []
        def sh(*a, **k):
            if a[:2] == ("gh", "api") and "--jq" in a and "actions/runs" in a[2]:
                jq.append(a[a.index("--jq") + 1])
                return subprocess.run(["jq", jq[0]], input=json.dumps({"workflow_runs": runs}), capture_output=True,
                                      text=True).stdout.strip()
            return "[skip ci] x" if "/commits/" in " ".join(a) else ""
        PC.sh = sh
        p = {"number": 8, "headRefOid": HEAD, "total": 1, "owner": "o", "alive": "a", "headRefName": "f", "title": "t"}
        log = []
        PC.start_ci_or_report(8, p, "#8 " + HEAD[:9] + " WAIT", {}, log, [])
        return log

    def test_live_preboard_run_does_not_block_start(self):
        self.assertTrue(any("start-ci #8" in l for l in self.count([{"name": PC.PREBOARD_LANE_NAME, "status": "in_progress"}])))

    def test_live_suite_run_still_blocks_start(self):
        self.assertEqual(self.count([{"name": "Python Suite", "status": "queued"}]), [])


if __name__ == "__main__":
    unittest.main()
