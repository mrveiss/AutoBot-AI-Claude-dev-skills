"""Pre-board guard lane gate of scripts/pr-coordinator (#49): the full suite starts only at a head with a green lane result,
and a broken lane never stalls the queue."""
import contextlib, importlib.machinery, importlib.util, io, json, tempfile, time, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
    loader.exec_module(mod)
    return mod


PC = load()
HEAD = "a" * 40
CANCELLED2 = "7\tcompleted\tcancelled\n6\tcompleted\tcancelled"


def prkey(n, kind, head=HEAD):
    return f"{n}:{kind}:{head}"


class Base(unittest.TestCase):
    """`runs` is the lane's run list per head (default for any head); `artifact` is written as result.json (None: no file);
    `dispatch_rc` is what `gh workflow run` returns as (rc, stdout, stderr)."""

    def setUp(self):
        PC.DRY = False
        PC.OPEN_HEADS.clear()
        PC.OPEN_HEADS[7] = HEAD
        self.calls, self.dispatched = [], []
        self.runs, self.runs_by_head, self.artifact, self.dispatch_rc = "", {}, None, (0, "", "")
        self.p = {"number": 7, "headRefOid": HEAD, "headRefName": "issue-7-x", "title": "t", "owner": "o", "alive": "a", "total": 1}
        PC.sh, PC.sh_rc = self.fake_sh, self.fake_rc

    def fake_rc(self, *a):
        self.dispatched.append(a)
        return self.dispatch_rc

    def fake_sh(self, *a, **k):
        self.calls.append(a)
        s = " ".join(a)
        if a[0].endswith("ci-gate"):
            return "RED"
        if "workflows/dispatch-preboard-guards.yml/runs" in s:
            return next((v for h, v in self.runs_by_head.items() if f"head_sha={h}" in s), self.runs)
        if a[:3] == ("gh", "run", "download"):
            if self.artifact is not None:
                (Path(a[a.index("-D") + 1]) / "result.json").write_text(json.dumps(self.artifact), encoding="utf-8")
            return ""
        if "/commits/" in s:
            return "[skip ci] sync"
        return ""

    def phase(self, seen, log, att):
        return PC.slot_ci_phase(7, self.p, False, seen, log, att)

    def suite_started(self):
        return any(c[:4] == ("gh", "workflow", "run", "sync-branches-with-main.yml") for c in self.calls)

    def kinds(self, att):
        return [a["kind"] for a in att]


class Gate(Base):
    def test_no_result_dispatches_once_and_waits(self):
        seen, log, att = {}, [], []
        self.phase(seen, log, att)
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(self.dispatched[0][-4:], ("--ref", "issue-7-x", "-f", "base=main"))
        self.assertFalse(self.suite_started())
        self.assertEqual(att, [])

    def test_repeated_tick_does_not_dispatch_again(self):
        seen, log, att = {}, [], []
        for _ in range(4):
            self.phase(seen, log, att)
        self.assertEqual(len(self.dispatched), 1)
        self.assertFalse(self.suite_started())

    def test_pending_lane_waits_without_dispatch(self):
        self.runs = "11\tin_progress\t"
        self.phase({}, [], [])
        self.assertEqual(self.dispatched, [])
        self.assertFalse(self.suite_started())

    def test_green_result_starts_suite(self):
        for overall in ("green", "green_with_skips"):
            self.calls.clear()
            self.runs, self.artifact = "11\tcompleted\tsuccess", {"overall": overall, "sha": HEAD, "base_sha": "old"}
            self.phase({}, [], [])
            self.assertTrue(self.suite_started(), overall)
        self.assertEqual(self.dispatched, [])

    def test_red_result_pages_owner_with_guards_red_and_starts_nothing(self):
        self.runs = "11\tcompleted\tfailure"
        self.artifact = {"overall": "red", "sha": HEAD, "checks": {"types": {"status": "failure"}, "own_specs": {"status": "success"},
                         "guards": {"status": "red", "problems": ["a shard is missing"]}}, "failed_tests": [{"nodeid": "t.py::x"}]}
        seen, log, att = {}, [], []
        self.phase(seen, log, att)
        self.phase(seen, log, att)
        self.assertFalse(self.suite_started())
        self.assertEqual([(a["kind"], a["owner"]) for a in att], [("guards-red", "o")])
        self.assertEqual(att[0]["checks"], ["types=failure", "guards=red", "a shard is missing", "t.py::x"])


class Unreadable(Base):
    """An unreadable lane is the lane's fault: retried, then escalated to the coordinator, never paged as guards-red."""

    def test_unreadable_first_time_redispatches_and_pages_nobody(self):
        self.runs, self.artifact = "6\tcompleted\tsuccess", None
        seen, log, att = {}, [], []
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(att, [])
        self.assertFalse(self.suite_started())

    def test_malformed_or_other_head_result_is_unreadable(self):
        self.runs = "11\tcompleted\tsuccess"
        for art in ({"sha": HEAD}, {"overall": "green", "sha": "b" * 40}, ["green"]):
            self.artifact = art
            state, _ = PC.lane_result(PC.lane_runs(HEAD), HEAD)
            self.assertEqual(state, "unreadable", art)

    def test_cancelled_lane_is_unreadable(self):
        self.runs = "11\tcompleted\tcancelled"
        self.assertEqual(PC.lane_result(PC.lane_runs(HEAD), HEAD)[0], "unreadable")

    def test_lane_unreadable_for_good_escalates_once_to_coordinator_and_parks(self):
        self.runs = CANCELLED2
        seen, log, att = {}, [], []
        for _ in range(3):
            self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))
        self.assertEqual(self.dispatched, [])                       # both tries already spent on listed runs
        self.assertEqual([(a["kind"], a["owner"]) for a in att], [("preboard-lane-broken", "pr-coordinator")])
        self.assertIn(prkey(7, "preboard-broken"), seen)
        self.assertFalse(self.suite_started())

    def test_retry_is_bounded_by_max_tries(self):
        seen, log, att = {}, [], []
        self.runs = "7\tcompleted\tcancelled"
        PC.preboard_clear(7, self.p, seen, log, att)                 # try 2 of 2
        self.assertEqual((len(self.dispatched), seen[prkey(7, "preboard-tries")]), (1, 1))
        self.runs = CANCELLED2
        seen.pop(prkey(7, "preboard-dispatch"))
        for _ in range(3):
            PC.preboard_clear(7, self.p, seen, log, att)
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(self.kinds(att), ["preboard-lane-broken"])

    def test_lost_seen_cannot_exceed_try_cap(self):
        self.runs = CANCELLED2
        for _ in range(3):
            PC.preboard_clear(7, self.p, {}, [], [])                  # `seen` is empty every time
        self.assertEqual(self.dispatched, [])

    def test_no_run_ever_appears_counts_as_a_try_then_breaks(self):
        old = int(time.time()) - PC.PREBOARD_NO_RUN_S - 5
        seen, log, att = {prkey(7, "preboard-dispatch"): old, prkey(7, "preboard-lastrun"): "", prkey(7, "preboard-tries"): 1}, [], []
        PC.preboard_clear(7, self.p, seen, log, att)
        self.assertEqual(len(self.dispatched), 1)                     # try 2
        seen[prkey(7, "preboard-dispatch")] = old
        PC.preboard_clear(7, self.p, seen, log, att)
        self.assertEqual((len(self.dispatched), self.kinds(att)), (1, ["preboard-lane-broken"]))

    def test_listing_lag_after_redispatch_does_not_redispatch(self):
        self.runs = "7\tcompleted\tcancelled"
        seen = {prkey(7, "preboard-dispatch"): int(time.time()), prkey(7, "preboard-lastrun"): "7", prkey(7, "preboard-tries"): 1}
        self.assertFalse(PC.preboard_clear(7, self.p, seen, [], []))
        self.assertEqual(self.dispatched, [])


class Dispatch(Base):
    def test_failed_dispatch_sets_no_marker_counts_a_try_and_blocks_nothing_forever(self):
        self.dispatch_rc = (1, "", "HTTP 502: bad gateway")
        seen, log, att = {}, [], []
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))
        self.assertNotIn(prkey(7, "preboard-dispatch"), seen)
        self.assertEqual(seen[prkey(7, "preboard-tries")], 1)
        self.assertTrue(any("dispatch failed (exit 1" in line and "502" in line for line in log))
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))   # try 2
        self.assertEqual(att, [])
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))   # cap spent: broken, coordinator told
        self.assertEqual(self.kinds(att), ["preboard-lane-broken"])
        self.assertEqual(len(self.dispatched), 2)

    def test_branch_without_the_workflow_fails_open(self):
        for err in ("could not find any workflows named dispatch-preboard-guards.yml",
                    "Unexpected inputs provided: [\"base\"]", "HTTP 404: Not Found"):
            self.calls.clear()
            self.dispatch_rc = (1, "", err)
            seen, log = {}, []
            self.phase(seen, log, [])
            self.assertIn(prkey(7, "preboard-unavailable"), seen, err)
            self.assertTrue(any("unavailable for branch" in line for line in log))
            self.phase(seen, log, [])                                    # the next tick starts the suite
            self.assertTrue(self.suite_started(), err)

    def test_fork_pr_fails_open_without_dispatch(self):
        self.p["isCrossRepository"] = True
        log = []
        self.assertTrue(PC.preboard_clear(7, self.p, {}, log, []))
        self.assertEqual(self.dispatched, [])
        self.assertTrue(any("fork PR" in line for line in log))

    def test_dry_run_dispatches_nothing(self):
        PC.DRY = True
        self.phase({}, [], [])
        self.assertEqual(self.dispatched, [])


class LaneDown(Base):
    def test_two_broken_prs_emit_one_lane_down_and_fail_open(self):
        h2 = "b" * 40
        p2 = {**self.p, "number": 8, "headRefOid": h2, "headRefName": "issue-8-y"}
        PC.OPEN_HEADS[8] = h2
        self.runs = CANCELLED2
        seen, log, att = {}, [], []
        self.assertFalse(PC.preboard_clear(7, self.p, seen, log, att))   # first broken PR: parked, coordinator told
        self.assertTrue(PC.preboard_clear(8, p2, seen, log, att))        # second: the lane is down, fail open
        self.assertTrue(PC.preboard_clear(7, self.p, seen, log, att))    # and so is the first, from now on
        self.assertEqual(self.kinds(att), ["preboard-lane-broken", "preboard-lane-down"])
        self.assertEqual(att[1]["prs"], [7, 8])
        self.assertTrue(any("guard stage skipped" in line for line in log))

    def test_lane_down_suite_starts_through_slot_phase(self):
        PC.OPEN_HEADS[8] = "b" * 40
        seen = {prkey(8, "preboard-broken", "b" * 40): 1}
        self.runs = CANCELLED2
        self.phase(seen, [], [])
        self.assertTrue(self.suite_started())

    def test_lane_down_clears_when_a_head_recovers(self):
        seen = {"preboard-lane-down": 1, prkey(7, "preboard-broken"): 1}
        PC.preboard_unpark([self.p], seen, [])
        self.assertNotIn("preboard-lane-down", seen)


class LaneRunsNeverCancelled(Base):
    """Rule 2, rule 4 and the degraded tick all take their runs from actions_runs(): the lane's name must be filtered there."""

    def test_lane_name_is_exempt_and_actions_runs_drops_it(self):
        self.assertEqual(PC.PREBOARD_LANE_NAME, "Dispatch Preboard Guards")
        self.assertIn(PC.PREBOARD_LANE_NAME, PC.EXEMPT_WORKFLOWS)
        PC.sh = lambda *a, **k: "1\tissue-9\tsha\tworkflow_dispatch\tDispatch Preboard Guards\n2\tissue-9\tsha\tpull_request\tAutoBot CI/CD Pipeline"
        self.assertEqual([r[0] for r in PC.actions_runs()], ["2"])


class InfraRerun(Base):
    def test_infra_rerun_stays_ungated(self):
        p = {"number": 7, "headRefOid": HEAD, "red": ["job"], "red_ids": {"job": 5}, "body": ""}
        PC.log_tail = lambda _id: "##[error]The runner has received a shutdown signal."
        PC.proof_status = lambda *a: ""
        PC.sh = lambda *a, **k: (self.calls.append(a), "99")[1]
        self.assertEqual(PC.infra_rerun(p, {}, []), [])
        self.assertTrue(any(c[:3] == ("gh", "run", "rerun") for c in self.calls))
        self.assertFalse(any("preboard" in " ".join(c) for c in self.calls))
        self.assertEqual(self.dispatched, [])


class FakeRedis:
    def exists(self, k): return False
    def scan_iter(self, pat): return iter(())
    def hgetall(self, k): return {}
    def hget(self, k, f): return None


class FakeLedger:
    def conn(self): return FakeRedis()
    def alive(self, r, name): return "alive"


class Main(Base):
    """main() end to end: parking and unparking move the slot to the next FIFO PR."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        PC.STATE = Path(self.tmp.name)
        self.heads = {n: chr(96 + n) * 40 for n in (1, 2, 3)}
        PC.OPEN_HEADS.clear()
        prs = [{"number": n, "title": f"t{n}", "createdAt": f"2026-11-0{n}T00:00:00Z", "updatedAt": "", "isDraft": False, "body": "",
                "changedFiles": 1, "headRefName": f"issue-{n}", "headRefOid": self.heads[n], "mergeable": "MERGEABLE",
                "author": {"login": "mrveiss"}, "reviewThreads": {"nodes": []}, "commits": {"nodes": []}} for n in (1, 2, 3)]
        PC.fetch_prs = lambda: [dict(p) for p in prs]
        PC.ledger_mod, PC.ci_state = FakeLedger, lambda p: ([], 0, 0)
        PC.infra_rerun, PC.owner_of = lambda p, seen, log: p["red"], lambda r, lg, p: ("o", "alive")
        PC.rabbit_threads, PC.actions_runs = lambda p: [], lambda: []
        PC.stale_pr_claims, PC.proof_blocked = lambda c, o: [], lambda *a: False
        PC.deps = None
        self.runs_by_head = {self.heads[2]: "22\tin_progress\t", self.heads[3]: "33\tin_progress\t"}
        (PC.STATE / "notified.json").write_text("{}", encoding="utf-8")

    def tick(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            PC.main()
        return next(line for line in buf.getvalue().splitlines() if line.startswith("slots="))

    def seed(self, extra):
        f = PC.STATE / "notified.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d.update(extra)
        f.write_text(json.dumps(d), encoding="utf-8")

    def test_slow_lane_parks_then_unparks_and_the_slot_moves(self):
        h1, old = self.heads[1], int(time.time()) - PC.PREBOARD_SLOT_WAIT_S - 5
        self.runs_by_head[h1] = "11\tin_progress\t"
        self.seed({f"1:preboard-dispatch:{h1}": old, f"1:preboard-lastrun:{h1}": "", f"1:preboard-tries:{h1}": 1})
        self.assertTrue(self.tick().startswith("slots=[1, 2]"))     # PR1 holds a slot and is found slow
        self.assertTrue(self.tick().startswith("slots=[2, 3]"))     # parked: PR3, next in FIFO, takes the slot
        self.runs_by_head[h1], self.artifact = "11\tcompleted\tsuccess", {"overall": "green", "sha": h1}
        self.assertTrue(self.tick().startswith("slots=[1, 2]"))     # lane done: unparked, back in FIFO order

    def test_broken_lane_escalates_and_releases_the_slot(self):
        h1 = self.heads[1]
        self.runs_by_head[h1] = CANCELLED2
        self.assertTrue(self.tick().startswith("slots=[1, 2]"))
        self.assertTrue(self.tick().startswith("slots=[2, 3]"))
        pages = [json.loads(line) for line in (PC.STATE / "attention.jsonl").read_text(encoding="utf-8").splitlines()]
        broken = [a for a in pages if a["kind"] == "preboard-lane-broken"]
        self.assertEqual([(a["pr"], a["owner"]) for a in broken], [(1, "pr-coordinator")])
        self.assertFalse(any(a["kind"] == "guards-red" for a in pages))


if __name__ == "__main__":
    unittest.main()
