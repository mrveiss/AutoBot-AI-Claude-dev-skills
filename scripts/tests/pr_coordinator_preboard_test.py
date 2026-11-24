"""Pre-board guard lane of scripts/pr-coordinator (#49): ADVISORY only. It never gates the suite, a slot, a merge or landing."""
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


RED_ARTIFACT = {"overall": "red", "sha": HEAD, "checks": {"types": {"status": "failure"}, "own_specs": {"status": "success"},
                "guards": {"status": "red", "problems": ["env-alias-registry-gap floor 48 vs 49"]}}, "failed_tests": [{"nodeid": "t.py::x"}]}


class Advisory(Base):
    def adv(self, seen, log, att):
        return PC.preboard_advisory(7, self.p, seen, log, att)

    def test_dispatches_once_per_head_and_never_again(self):
        seen, log, att = {}, [], []
        for _ in range(4):
            self.adv(seen, log, att)
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(self.dispatched[0][-4:], ("--ref", "issue-7-x", "-f", "base=main"))
        self.assertEqual(att, [])

    def test_existing_run_is_adopted_not_redispatched(self):
        self.runs = "11\tin_progress\t"
        self.adv({}, [], [])
        self.assertEqual(self.dispatched, [])

    def test_red_lane_pages_owner_exactly_once_as_advisory(self):
        self.runs, self.artifact = "11\tcompleted\tfailure", RED_ARTIFACT
        seen, log, att = {}, [], []
        for _ in range(3):
            self.adv(seen, log, att)
        self.assertEqual([(a["kind"], a["owner"], a["advisory"]) for a in att], [("guards-advisory", "o", True)])
        self.assertEqual(att[0]["checks"], ["types=failure", "guards=red", "env-alias-registry-gap floor 48 vs 49", "t.py::x"])
        self.assertEqual(self.dispatched, [])

    def test_green_lane_pages_nobody(self):
        self.runs, self.artifact = "11\tcompleted\tsuccess", {"overall": "green_with_skips", "sha": HEAD}
        att = []
        self.adv({}, [], att)
        self.assertEqual(att, [])

    def test_broken_lane_results_are_logged_once_and_page_nobody(self):
        self.runs = "11\tcompleted\tsuccess"
        for art in (None, {"sha": HEAD}, {"overall": "green", "sha": "b" * 40}):
            self.artifact, seen, log, att = art, {}, [], []
            self.adv(seen, log, att)
            self.adv(seen, log, att)
            self.assertEqual(att, [], art)
            self.assertEqual(sum("not usable" in line for line in log), 1, art)
        self.runs, seen, log, att = "11\tcompleted\tcancelled", {}, [], []
        self.adv(seen, log, att)
        self.assertEqual((att, sum("not usable" in line for line in log)), ([], 1))

    def test_failed_dispatch_is_logged_sets_no_marker_and_is_capped(self):
        self.dispatch_rc = (1, "", "HTTP 502: bad gateway")
        seen, log, att = {}, [], []
        for _ in range(5):
            self.adv(seen, log, att)
        self.assertNotIn(prkey(7, "preboard-dispatch"), seen)
        self.assertEqual(len(self.dispatched), PC.PREBOARD_MAX_TRIES)
        self.assertTrue(any("dispatch failed (exit 1" in line and "502" in line for line in log))
        self.assertEqual(att, [])

    def test_branch_without_the_workflow_is_marked_unavailable_and_left_alone(self):
        for err in ("could not find any workflows named dispatch-preboard-guards.yml",
                    "Unexpected inputs provided: [\"base\"]", "HTTP 404: Not Found"):
            self.dispatched.clear()
            self.dispatch_rc = (1, "", err)
            seen, log = {}, []
            for _ in range(3):
                self.adv(seen, log, [])
            self.assertIn(prkey(7, "preboard-unavailable"), seen, err)
            self.assertEqual(len(self.dispatched), 1, err)

    def test_fork_pr_gets_no_lane(self):
        self.p["isCrossRepository"] = True
        self.adv({}, [], [])
        self.assertEqual(self.dispatched, [])

    def test_dry_run_dispatches_nothing(self):
        PC.DRY = True
        self.adv({}, [], [])
        self.assertEqual(self.dispatched, [])


class NeverGates(Base):
    """Whatever the lane says, the suite starter behaves exactly as before the lane existed."""

    def test_suite_starts_whatever_the_lane_state(self):
        states = {"no result": ("", None), "pending": ("11\tin_progress\t", None), "cancelled": ("11\tcompleted\tcancelled", None),
                  "unreadable": ("11\tcompleted\tsuccess", None), "red": ("11\tcompleted\tfailure", RED_ARTIFACT)}
        for name, (runs, art) in states.items():
            self.calls.clear()
            self.runs, self.artifact = runs, art
            PC.slot_ci_phase(7, self.p, False, {}, [], [])
            self.assertTrue(self.suite_started(), name)
        self.assertFalse(any("preboard" in " ".join(c) for c in self.dispatched if c[:3] != ("gh", "workflow", "run")))

    def test_recheck_and_cancelled_rerun_are_not_gated(self):
        self.runs = "11\tcompleted\tfailure"
        self.artifact = RED_ARTIFACT
        PC.RECHECK = {"7": HEAD[:9]}
        PC.sh = lambda *a, **k: (self.calls.append(a), "5\tcompleted\tfailure" if "/actions/runs?head_sha" in " ".join(a) else "")[1]
        self.assertTrue(PC.slot_ci_phase(7, self.p, False, {}, [], []))
        self.assertTrue(self.suite_started())
        PC.RECHECK, self.calls[:] = {}, []
        PC.sh = lambda *a, **k: (self.calls.append(a), "5\tcompleted\tcancelled" if "/actions/runs?head_sha" in " ".join(a) else "")[1]
        PC.slot_ci_phase(7, self.p, False, {}, [], [])
        self.assertTrue(any(c[:3] == ("gh", "run", "rerun") for c in self.calls))


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
    """main() end to end: the lane changes no slot, whatever it reports."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        PC.STATE = Path(self.tmp.name)
        self.heads = {n: chr(96 + n) * 40 for n in (1, 2, 3)}
        prs = [{"number": n, "title": f"t{n}", "createdAt": f"2026-11-0{n}T00:00:00Z", "updatedAt": "", "isDraft": False, "body": "",
                "changedFiles": 1, "headRefName": f"issue-{n}", "headRefOid": self.heads[n], "mergeable": "MERGEABLE",
                "author": {"login": "mrveiss"}, "reviewThreads": {"nodes": []}, "commits": {"nodes": []}} for n in (1, 2, 3)]
        PC.fetch_prs = lambda: [dict(p) for p in prs]
        PC.ledger_mod, PC.ci_state = FakeLedger, lambda p: ([], 0, 0)
        PC.infra_rerun, PC.owner_of = lambda p, seen, log: p["red"], lambda r, lg, p: ("o", "alive")
        PC.rabbit_threads, PC.actions_runs = lambda p: [], lambda: []
        PC.stale_pr_claims, PC.proof_blocked = lambda c, o: [], lambda *a: False
        (PC.STATE / "notified.json").write_text("{}", encoding="utf-8")

    def tick(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            PC.main()
        return next(line for line in buf.getvalue().splitlines() if line.startswith("slots="))

    def pages(self):
        f = PC.STATE / "attention.jsonl"
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def test_red_lane_pages_once_and_the_slots_do_not_move(self):
        h1 = self.heads[1]
        self.runs_by_head = {h1: "11\tcompleted\tfailure"}
        self.artifact = {**RED_ARTIFACT, "sha": h1}
        slots = [self.tick() for _ in range(3)]
        self.assertEqual({s.split(" eligible")[0] for s in slots}, {"slots=[1, 2]"})
        self.assertEqual([(a["pr"], a["kind"]) for a in self.pages()], [(1, "guards-advisory")])

    def test_each_slot_head_gets_one_dispatch_across_ticks(self):
        for _ in range(3):
            self.tick()
        self.assertEqual(sorted(c[c.index("--ref") + 1] for c in self.dispatched if "--ref" in c), ["issue-1", "issue-2"])

    def test_broken_lane_changes_nothing(self):
        self.runs_by_head = {self.heads[1]: "7\tcompleted\tcancelled\n6\tcompleted\tcancelled"}
        self.assertTrue(self.tick().startswith("slots=[1, 2]"))
        self.assertTrue(self.tick().startswith("slots=[1, 2]"))
        self.assertEqual(self.pages(), [])


def _run(name, wf, concl="FAILURE", status="COMPLETED"):
    return {"name": name, "status": status, "conclusion": concl, "startedAt": "2026-11-24T10:00:00Z", "databaseId": 1,
            "checkSuite": {"workflowRun": {"workflow": {"name": wf}}}}


def _pr(*nodes):
    return {"number": 22028, "headRefOid": HEAD, "isDraft": False,
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": list(nodes)}}}}]}}


class LaneNeverRedTest(unittest.TestCase):
    """#55: the lane's check runs ride the PR head SHA; ci_state must not count them by job name."""

    def test_lane_only_failures_are_not_red_active_or_counted(self):
        lane = PC.PREBOARD_LANE_NAME
        pr = _pr(*[_run(n, lane) for n in ("result", "guards shard 3/6", "own tests")],
                 _run("types", lane, None, "IN_PROGRESS"))
        self.assertEqual(PC.ci_state(pr), ([], 0, 0))

    def test_real_ci_failure_beside_lane_reds_is_still_red(self):
        pr = _pr(_run("result", PC.PREBOARD_LANE_NAME), _run("python-suite", "CI"), _run("lint", "CI", "SUCCESS"))
        red, active, total = PC.ci_state(pr)
        self.assertEqual((red, active, total), (["python-suite"], 0, 2))

    def test_status_context_without_workflow_is_kept(self):
        pr = _pr({"context": "legacy", "state": "FAILURE", "createdAt": "2026-11-24T10:00:00Z"})
        self.assertEqual(PC.ci_state(pr)[0], ["legacy"])


if __name__ == "__main__":
    unittest.main()
