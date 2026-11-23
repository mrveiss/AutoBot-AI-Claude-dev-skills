"""Pre-board guard lane gate of scripts/pr-coordinator (#49): the full suite starts only at a head with a green lane result."""
import importlib.machinery, importlib.util, json, time, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
    loader.exec_module(mod)
    return mod


PC = load()
HEAD = "a" * 40


class Base(unittest.TestCase):
    """`runs` is what the lane's run list returns; `artifact` is written as result.json (None: no file)."""
    runs, artifact = "", None

    def setUp(self):
        PC.DRY = False
        self.calls = []
        self.p = {"number": 7, "headRefOid": HEAD, "headRefName": "issue-7-x", "title": "t", "owner": "o", "alive": "a", "total": 1}
        PC.sh = self.fake_sh

    def fake_sh(self, *a, **k):
        self.calls.append(a)
        s = " ".join(a)
        if a[0].endswith("ci-gate"):
            return "RED"
        if "workflows/dispatch-preboard-guards.yml/runs" in s:
            return self.runs
        if a[:3] == ("gh", "run", "download"):
            if self.artifact is not None:
                (Path(a[a.index("-D") + 1]) / "result.json").write_text(json.dumps(self.artifact), encoding="utf-8")
            return ""
        if "/commits/" in s:
            return "[skip ci] sync"
        return ""

    def phase(self, seen, log, att):
        return PC.slot_ci_phase(7, self.p, False, seen, log, att)

    def called(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]

    def suite_started(self):
        return bool(self.called("gh", "workflow", "run", "sync-branches-with-main.yml"))

    def dispatches(self):
        return self.called("gh", "workflow", "run", PC.PREBOARD_WORKFLOW)


class Gate(Base):
    def test_no_result_dispatches_once_and_waits(self):
        seen, log, att = {}, [], []
        self.phase(seen, log, att)
        self.assertEqual(len(self.dispatches()), 1)
        self.assertEqual(self.dispatches()[0][-4:], ("--ref", "issue-7-x", "-f", "base=main"))
        self.assertFalse(self.suite_started())
        self.assertEqual(att, [])

    def test_repeated_tick_does_not_dispatch_again(self):
        seen, log, att = {}, [], []
        for _ in range(3):
            self.phase(seen, log, att)
        self.assertEqual(len(self.dispatches()), 1)
        self.assertFalse(self.suite_started())

    def test_pending_lane_waits(self):
        self.runs = "11\tin_progress\t"
        self.phase({}, [], [])
        self.assertEqual(self.dispatches(), [])
        self.assertFalse(self.suite_started())

    def test_green_result_starts_suite(self):
        for overall in ("green", "green_with_skips"):
            self.calls.clear()
            self.runs, self.artifact = "11\tcompleted\tsuccess", {"overall": overall, "sha": HEAD, "base_sha": "old"}
            self.phase({}, [], [])
            self.assertTrue(self.suite_started(), overall)
            self.assertEqual(self.dispatches(), [])

    def test_red_result_pages_and_starts_nothing(self):
        self.runs = "11\tcompleted\tfailure"
        self.artifact = {"overall": "red", "sha": HEAD, "checks": {"types": {"status": "failure"}, "own_specs": {"status": "success"},
                         "guards": {"status": "red", "problems": ["a shard is missing"]}}, "failed_tests": [{"nodeid": "t.py::x"}]}
        seen, log, att = {}, [], []
        self.phase(seen, log, att)
        self.phase(seen, log, att)
        self.assertFalse(self.suite_started())
        self.assertEqual([(a["kind"], a["pr"]) for a in att], [("guards-red", 7)])
        self.assertEqual(att[0]["checks"], ["types=failure", "guards=red", "a shard is missing", "t.py::x"])
        self.assertIn(f"7:guards-red:{HEAD}", seen)

    def test_unreadable_artifact_fails_closed(self):
        self.runs, self.artifact = "11\tcompleted\tsuccess", None
        seen, log, att = {}, [], []
        self.phase(seen, log, att)
        self.assertFalse(self.suite_started())
        self.assertTrue(any("unreadable" in line and "not readable" in line for line in log))
        self.assertEqual([a["kind"] for a in att], ["guards-red"])

    def test_malformed_or_other_head_result_fails_closed(self):
        self.runs = "11\tcompleted\tsuccess"
        for art in ({"sha": HEAD}, {"overall": "green", "sha": "b" * 40}, ["green"]):
            self.artifact = art
            self.assertFalse(PC.preboard_clear(7, self.p, {}, [], []), art)

    def test_cancelled_lane_fails_closed(self):
        self.runs = "11\tcompleted\tcancelled"
        self.assertFalse(PC.preboard_clear(7, self.p, {}, [], []))


class Slot(Base):
    def test_slow_lane_parks_pr_off_slot_and_unparks_when_done(self):
        self.runs = "11\tin_progress\t"
        seen, log = {f"7:preboard-dispatch:{HEAD}": int(time.time()) - PC.PREBOARD_SLOT_WAIT_S - 5}, []
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, []))
        self.assertIn(f"7:preboard-parked:{HEAD}", seen)
        PC.preboard_unpark([self.p], seen, log)
        self.assertIn(f"7:preboard-parked:{HEAD}", seen)      # still pending: stays parked
        self.runs = "11\tcompleted\tsuccess"
        PC.preboard_unpark([self.p], seen, log)
        self.assertNotIn(f"7:preboard-parked:{HEAD}", seen)

    def test_dispatched_but_no_run_appears_fails_closed(self):
        seen, log, att = {f"7:preboard-dispatch:{HEAD}": int(time.time()) - PC.PREBOARD_NO_RUN_S - 5}, [], []
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))
        self.assertTrue(any("no run" in line for line in log))
        self.assertEqual(self.dispatches(), [])


class Dry(Base):
    def test_dry_run_dispatches_nothing(self):
        PC.DRY = True
        self.phase({}, [], [])
        self.assertEqual(self.dispatches(), [])


if __name__ == "__main__":
    unittest.main()
