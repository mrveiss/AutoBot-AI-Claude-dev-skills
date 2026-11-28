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
    return {"number": n, "isDraft": draft, "headRefOid": HEAD, "labels": {"nodes": [{"name": "ci-parked"}] if parked else []}}


class Base(unittest.TestCase):
    fail = ()   # substrings of gh commands that return rc 1

    def setUp(self):
        self.calls = []
        self._sh, self._rc, self._dry = PC.sh, PC.sh_rc, PC.DRY
        PC.sh = lambda *a, **k: self.calls.append(a) or ""
        PC.sh_rc = self._fake_rc
        PC.DRY = False
        self.addCleanup(lambda: (setattr(PC, "sh", self._sh), setattr(PC, "sh_rc", self._rc), setattr(PC, "DRY", self._dry)))

    def _fake_rc(self, *a):
        self.calls.append(a)
        return (1, "", "boom") if any(f in " ".join(a) for f in self.fail) else (0, "", "")


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


class KeptSlotReleases(Base):
    HELD = {1: {"by": PC.ME}, 2: {"by": PC.ME}}

    def test_release_set_frees_only_those(self):
        self.assertEqual(PC.kept_slots(self.HELD, {1, 2}, FakeR(), release={1}), [2])

    def test_red_conflict_awaiting_are_not_releases(self):
        self.assertEqual(PC.kept_slots(self.HELD, {1, 2}, FakeR(), release=set()), [1, 2])


class StuckSlot(Base):
    def prs(self): return [dict(pr(1), red=["x"], owner="o", alive="a", headRefName="b", title="t")]

    def test_pages_once_after_threshold(self):
        seen, att, log = {}, [], []
        PC.stuck_slot_pages(self.prs(), [1], seen, log, att, now=1000)
        self.assertEqual(att, [])
        later = 1000 + PC.STUCK_SLOT_SECS + 1
        PC.stuck_slot_pages(self.prs(), [1], seen, log, att, now=later)
        PC.stuck_slot_pages(self.prs(), [1], seen, log, att, now=later + 60)
        self.assertEqual([a["kind"] for a in att], ["slot-stuck"])

    def test_recovery_clears_clock(self):
        seen = {}
        PC.stuck_slot_pages(self.prs(), [1], seen, [], [], now=1000)
        PC.stuck_slot_pages([pr(1)], [1], seen, [], [], now=2000)
        self.assertNotIn("1:slot-stuck-since", seen)


class ParkFailures(Base):
    def test_park_labels_before_undo(self):
        PC.park_phase([pr(2)], [], [])
        flat = [" ".join(c) for c in self.calls]
        self.assertLess(next(i for i, c in enumerate(flat) if "--add-label" in c), next(i for i, c in enumerate(flat) if "--undo" in c))

    def test_label_failure_skips_undo_and_surfaces(self):
        self.fail, log, att = ("--add-label",), [], []
        PC.park_phase([pr(2)], [], log, {}, att)
        self.assertFalse([c for c in self.calls if "--undo" in c])
        self.assertTrue(any(l.startswith("ATTENTION #2 add label") for l in log))
        self.assertEqual(att[0]["kind"], "gh-failed")

    def test_label_create_failure_skips_park(self):
        self.fail, log = ("label create",), []
        PC.park_phase([pr(2)], [], log, {}, [])
        self.assertFalse([c for c in self.calls if "--add-label" in c or "--undo" in c])
        self.assertTrue(any("label create failed" in l for l in log))

    def test_undo_failure_surfaces(self):
        self.fail, log = ("--undo",), []
        PC.park_phase([pr(2)], [], log, {}, [])
        self.assertTrue(any("gh pr ready --undo failed" in l for l in log))

    def test_unpark_keeps_label_when_ready_fails(self):
        self.fail, log = ("pr ready 1",), []
        failed = PC.park_phase([pr(1, draft=True, parked=True)], [1], log, {}, [])
        self.assertEqual(failed, {1})
        self.assertFalse([c for c in self.calls if "--remove-label" in c])
        self.assertTrue(any("gh pr ready failed" in l for l in log))

    def test_unpark_ready_before_label_removal_and_marks_unparked(self):
        p = pr(1, draft=True, parked=True)
        PC.park_phase([p], [1], [], {}, [])
        flat = [" ".join(c) for c in self.calls]
        self.assertLess(next(i for i, c in enumerate(flat) if "pr ready 1" in c), next(i for i, c in enumerate(flat) if "--remove-label" in c))
        self.assertTrue(p["unparked"])

    def test_remove_label_failure_surfaces(self):
        self.fail, log = ("--remove-label",), []
        PC.park_phase([pr(1, draft=True, parked=True)], [1], log, {}, [])
        self.assertTrue(any("remove label failed" in l for l in log))

    def test_reready_parked_pr_reparked_without_label_flap_logged_once(self):
        seen, log = {}, []
        for _ in range(2):
            PC.park_phase([pr(2, parked=True)], [], log, seen, [])
        self.assertFalse([c for c in self.calls if "--add-label" in c or "label" in c and "create" in c])
        self.assertEqual(len([c for c in self.calls if "--undo" in c]), 2)
        self.assertEqual(len([l for l in log if l.startswith("park #2")]), 1)


class FetchParkedDetails(Base):
    def test_parked_draft_gets_details_author_draft_does_not(self):
        base = {"updatedAt": "t", "mergeable": "MERGEABLE", "changedFiles": 1}
        nodes = [dict(pr(1, draft=True, parked=True), **base), dict(pr(2, draft=True), **base)]
        asked = []
        def gql(q, **v):
            if "pullRequests(" in q:
                return {"repository": {"pullRequests": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}}
            asked.append(q)
            return {"repository": {"p1": {"reviewThreads": {"nodes": [{"x": 1}]}}}}
        old, PC.gql, dry = PC.gql, gql, PC.DRY
        PC.DRY = True
        self.addCleanup(lambda: (setattr(PC, "gql", old), setattr(PC, "DRY", dry)))
        out = PC.fetch_prs()
        self.assertEqual(len(asked), 1)
        self.assertIn("p1:", asked[0])
        self.assertNotIn("p2:", asked[0])
        self.assertEqual(out[0]["reviewThreads"]["nodes"], [{"x": 1}])


class UnparkedSkipsStartCi(Base):
    def test_unparked_pr_not_started(self):
        started = []
        old = PC.start_ci_or_report
        PC.start_ci_or_report = lambda *a: started.append(a)
        self.addCleanup(lambda: setattr(PC, "start_ci_or_report", old))
        PC.sh = lambda *a, **k: "WAIT" if "ci-gate" in a[0] else ""
        old_up = PC._update_step
        PC._update_step = lambda *a: False
        self.addCleanup(lambda: setattr(PC, "_update_step", old_up))
        PC.slot_ci_phase(5, {"number": 5, "headRefOid": HEAD, "unparked": True}, False, {}, [], [])
        self.assertEqual(started, [])
        PC.slot_ci_phase(5, {"number": 5, "headRefOid": HEAD}, False, {}, [], [])
        self.assertEqual(len(started), 1)


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
