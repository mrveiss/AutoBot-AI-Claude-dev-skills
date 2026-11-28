"""CI dispatch by the coordinator (AutoBot-AI#20825, plan 2026-11-28 section 8.2) + dual mode, stop-parking, Q1/Q6, own-PR approval rule."""
import importlib.machinery, importlib.util, json, os, time, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")
loader = importlib.machinery.SourceFileLoader("pr_coordinator_dispatch", PATH)
PC = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator_dispatch", loader))
loader.exec_module(PC)
FETCH = PC.fetch_pr_rest
HEAD, BASE = "a" * 40, "b" * 40
SIX = list(PC.SUITE_WORKFLOWS + PC.META_WORKFLOWS)


def mkpr(n=7, head=HEAD, **extra):
    return {"number": n, "headRefName": f"issue-{n}-x", "headRefOid": head, "baseRefName": "main", "title": "t", "body": "b",
            "owner": "o", "alive": "a", "milestone": {"title": "M5"}, "labels": {"nodes": [{"name": "land-next"}]},
            "isCrossRepository": False, "author": {"login": "mrveiss"}, **extra}


class Base(unittest.TestCase):
    def setUp(self):
        self.posts, self.calls, self.runs, self.ahead, self.live, self.base = [], [], [], 0, None, BASE
        self.post_result = (0, "", "")          # or a dict wf -> (rc, out, err)
        self.cut, self.approved, self.dispatchable = False, set(), True
        saved = {k: getattr(PC, k) for k in ("sh", "sh_rc", "DRY", "cutover_done", "fork_approved")}
        PC.sh, PC.sh_rc, PC.DRY = self.sh, self.sh_rc, False
        PC.cutover_done = lambda: self.cut
        PC.fork_approved = lambda n, sha: (n, sha) in self.approved
        os.environ.pop("PR_COORDINATOR_DISPATCH", None)
        self.addCleanup(lambda: [setattr(PC, k, v) for k, v in saved.items()])
        self.addCleanup(os.environ.pop, "PR_COORDINATOR_DISPATCH", None)

    def sh_rc(self, *a):
        j = " ".join(a)
        if "/dispatches" in j:
            wf = next(x for x in a if "/dispatches" in x).split("/")[-2]
            inputs = {x.split("=")[0]: x.split("=")[1] for x in a if x.startswith("inputs[")}
            self.posts.append((wf, next(x for x in a if x.startswith("ref=")).split("=")[1], inputs))
            return self.post_result[wf] if isinstance(self.post_result, dict) and wf in self.post_result else (
                self.post_result if isinstance(self.post_result, tuple) else (0, "", ""))
        if "actions/runs?head_sha" in j:
            return 0, json.dumps(self.runs), ""
        if "contents/.github/workflows/ci.yml" in j:
            return 0, "on:\n  workflow_dispatch:\n" if self.dispatchable else "on:\n  pull_request:\n", ""
        self.calls.append(a)
        return 0, "", ""

    def sh(self, *a, **k):
        j = " ".join(a)
        self.calls.append(a)
        if "compare/" in j and j.endswith("...main --jq .ahead_by") or ("...main" in j and "ahead_by" in j):
            return str(self.ahead)
        if "merge_base_commit" in j:
            return self.base
        if "--jq .head.sha" in j:
            return self.live if self.live is not None else HEAD
        return ""

    def tick(self, p, seen, gen=0):
        log, att = [], []
        owned = PC.dispatch_ci(p["number"], p, seen, log, att, gen)
        return owned, log, att

    def dispatched(self):
        return [w for w, _, _ in self.posts]


class Dispatch(Base):
    def test_1_admission_dispatches_six_once(self):
        seen = {}
        self.assertTrue(self.tick(mkpr(), seen)[0])
        self.assertEqual(self.dispatched(), SIX)
        self.assertEqual(self.posts[0][2], {"inputs[pr_number]": "7", "inputs[head_sha]": HEAD, "inputs[base_sha]": BASE})
        self.posts.clear()
        self.tick(mkpr(), seen)
        self.assertEqual(self.posts, [])

    def test_2_new_head_six_body_edit_four(self):
        seen = {}
        self.tick(mkpr(), seen)
        self.posts.clear()
        new = "c" * 40
        self.live = new
        self.tick(mkpr(head=new), seen)
        self.assertEqual(self.dispatched(), SIX)
        self.posts.clear()
        self.tick(mkpr(head=new, body="edited"), seen)
        self.assertEqual(self.dispatched(), list(PC.META_WORKFLOWS))

    def test_3_grace_retry_then_one_no_ci_page(self):
        seen, att_all = {}, []
        self.tick(mkpr(), seen)
        self.posts.clear()
        self.tick(mkpr(), seen)                                   # younger than the grace, no listed run
        self.assertEqual(self.posts, [])
        for _ in range(PC.DISPATCH_MAX_TRIES + 1):
            for k, v in seen.items():
                if isinstance(v, dict):
                    v["ts"] -= PC.DISPATCH_GRACE_SECS + 1
            _, _, att = self.tick(mkpr(), seen)
            att_all += att
        self.assertEqual(len(self.posts), 6 * (PC.DISPATCH_MAX_TRIES - 1))   # tries 2 and 3, then stop
        self.assertEqual([a["kind"] for a in att_all if a["kind"] == "no-ci" and a["workflow"] == "ci.yml"], ["no-ci"])

    def test_4_listed_run_without_key_is_adopted(self):
        self.runs = [{"id": 1, "path": f".github/workflows/{w}", "status": "in_progress", "conclusion": None} for w in SIX]
        self.tick(mkpr(), {})
        self.assertEqual(self.posts, [])

    def test_5_cancelled_run_is_not_started_and_not_redispatched(self):
        runs = [{"id": 1, "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "cancelled"}]
        self.assertFalse(PC.suite_started(runs, "ci.yml"))
        self.runs = runs
        self.tick(mkpr(), {})
        self.assertNotIn("ci.yml", self.dispatched())

    def test_6_dry_dispatches_nothing_writes_no_key(self):
        PC.DRY, seen = True, {}
        _, log, _ = self.tick(mkpr(), seen)
        self.assertEqual(self.posts, [])
        self.assertFalse([k for k in seen if ":dispatch:" in k])
        self.assertTrue(any(l.startswith("dispatch #7 ci.yml") for l in log))

    def test_7_422_falls_back(self):
        err = (1, "", "gh: Workflow does not have 'workflow_dispatch' trigger (HTTP 422)")
        self.post_result = {"ci.yml": err}
        seen = {}
        self.assertFalse(self.tick(mkpr(), seen)[0])             # before cutover: legacy path, nothing else dispatched
        self.assertEqual(self.dispatched(), ["ci.yml"])
        self.assertFalse(self.tick(mkpr(), seen)[0])             # marked unavailable for this head: no second call
        self.assertEqual(self.dispatched(), ["ci.yml"])

    def test_7b_422_after_cutover_syncs_behind_or_pages(self):
        self.cut = True
        self.post_result = {"ci.yml": (1, "", "Unexpected inputs provided (HTTP 422)")}
        owned, _, att = self.tick(mkpr(), {})
        self.assertTrue(owned)
        self.assertEqual([a["kind"] for a in att], ["no-ci"])
        self.ahead, self.posts, self.calls = 0, [], []
        self.ahead = 3                                            # behind: sync first, never dispatched
        self.tick(mkpr(n=8, head="d" * 40), {})
        self.assertTrue(any("update-branch" in " ".join(c) for c in self.calls))
        self.assertEqual(self.posts, [])

    def test_8_fork_without_approval_pages_once_no_dispatch(self):
        self.cut, seen = True, {}
        fork = mkpr(isCrossRepository=True)
        PC.fork_approved = lambda n, sha: False
        a1 = self.tick(fork, seen)[2]
        a2 = self.tick(fork, seen)[2]
        self.assertEqual(self.posts, [])
        self.assertEqual(len(a1) + len(a2), 1)
        self.assertEqual(a1[0]["kind"], "fork-approval")
        self.assertIn("awaits owner approval to run with repo secrets", a1[0]["detail"])

    def test_9_fork_with_approval_mirrors_and_dispatches_on_mirror(self):
        self.cut, self.approved = True, {(7, HEAD)}
        fork = mkpr(isCrossRepository=True)
        self.tick(fork, {})
        self.assertTrue(any(c[:4] == ("gh", "api", "-X", "POST") and f"repos/{PC.REPO}/git/refs" in c and f"sha={HEAD}" in c
                            and "ref=refs/heads/ci/pr-7" in c for c in self.calls))
        self.assertEqual({r for _, r, _ in self.posts}, {"ci/pr-7"})
        self.assertIn((PC.REPO, "ci/pr-7"), PC.mirror_keep_heads([fork], [7]))
        self.assertNotIn((PC.REPO, "ci/pr-7"), PC.mirror_keep_heads([fork], []))

    def test_9b_a_new_fork_head_needs_a_new_approval(self):
        self.cut, self.approved = True, {(7, HEAD)}
        self.tick(mkpr(isCrossRepository=True, head="e" * 40), {})
        self.assertEqual(self.posts, [])

    def test_10_skip_dispatch_for_unpark_failed(self):
        PC._update_step_saved = PC._update_step
        PC._update_step = lambda *a: False
        self.addCleanup(lambda: setattr(PC, "_update_step", PC._update_step_saved))
        PC.slot_ci_phase(7, mkpr(total=1), False, {}, [], [], skip_dispatch=True)
        self.assertEqual(self.posts, [])

    def test_11_recheck_bumps_generation_same_sha_no_sync_workflow(self):
        PC.RECHECK[str(7)] = HEAD[:9]
        self.addCleanup(PC.RECHECK.pop, "7", None)
        old = PC._update_step
        PC._update_step = lambda *a: False
        self.addCleanup(lambda: setattr(PC, "_update_step", old))
        real_sh = self.sh
        PC.sh = lambda *a, **k: "1\tcompleted\tfailure" if "@tsv" in " ".join(a) else real_sh(*a, **k)
        seen = {}
        self.assertTrue(PC.slot_ci_phase(7, mkpr(total=1), False, seen, [], []))
        self.assertEqual(seen[f"7:dispatch-gen:{HEAD}"], 1)
        self.assertEqual(self.dispatched(), SIX)
        self.assertFalse([c for c in self.calls if "sync-branches-with-main.yml" in " ".join(c)])

    def test_12_head_moved_writes_no_key(self):
        self.live, seen = "f" * 40, {}
        self.tick(mkpr(), seen)
        self.assertEqual(self.posts, [])
        self.assertFalse([k for k in seen if ":dispatch:" in k])

    def test_13_kill_switch_is_legacy_only(self):
        os.environ["PR_COORDINATOR_DISPATCH"] = "0"
        self.assertFalse(self.tick(mkpr(), {})[0])
        self.assertEqual(self.posts, [])

    def test_14_merge_base_unreadable_no_dispatch_retry_next_tick(self):
        self.base, seen = "", {}
        owned, log, _ = self.tick(mkpr(), seen)
        self.assertTrue(owned)
        self.assertEqual(self.posts, [])
        self.assertTrue(any("merge base unreadable" in l for l in log))
        self.base = BASE
        self.tick(mkpr(), seen)
        self.assertEqual(self.dispatched(), SIX)

    def test_behind_head_syncs_first_when_ref_is_dispatchable_else_legacy(self):
        self.ahead = 2
        self.dispatchable = False
        self.assertFalse(self.tick(mkpr(), {})[0])               # before cutover, no dispatch inputs on the ref: legacy
        self.assertEqual(self.posts, [])
        self.dispatchable = True
        self.assertTrue(self.tick(mkpr(n=9, head="9" * 40), {})[0])
        self.assertTrue(any("update-branch" in " ".join(c) for c in self.calls))
        self.assertEqual(self.posts, [])


class Cutover(unittest.TestCase):
    def test_detection(self):
        pr_trig = "name: CI\non:\n  pull_request:\n    types: [opened]\n  workflow_dispatch:\n"
        self.assertFalse(PC.workflow_cut_over(pr_trig))
        self.assertFalse(PC.workflow_cut_over("on: [push, pull_request]\n"))
        self.assertFalse(PC.workflow_cut_over("on: pull_request_target\n"))
        self.assertTrue(PC.workflow_cut_over("on:\n  push:\n    branches: [main]\n  # pull_request: gone\n  merge_group:\n  workflow_dispatch:\n    inputs:\n      pr_number:\n        description: Pull request this run is for\n"))
        self.assertFalse(PC.workflow_cut_over("on:\n  push:\n"))          # no workflow_dispatch: not cut over
        self.assertFalse(PC.workflow_cut_over(""))                         # unreadable: not cut over

    def test_unreadable_main_is_not_cutover(self):
        saved = PC.sh_rc
        PC.sh_rc = lambda *a: (1, "", "boom")
        PC._CUT.clear()
        self.addCleanup(lambda: (setattr(PC, "sh_rc", saved), PC._CUT.clear()))
        self.assertFalse(PC.cutover_done())


class StopParking(Base):
    def parked(self, n, draft=True):
        return {"number": n, "isDraft": draft, "headRefOid": HEAD, "labels": {"nodes": [{"name": "ci-parked"}]}}

    def test_no_new_parks_ever(self):
        self.cut = True
        PC.unpark_phase([{"number": 1, "isDraft": False, "headRefOid": HEAD, "labels": {"nodes": []}}], [], [])
        self.assertEqual(self.calls, [])

    def test_before_cutover_non_slot_parked_pr_stays_parked(self):
        PC.unpark_phase([self.parked(2)], [], [])
        self.assertEqual(self.calls, [])

    def test_before_cutover_admitted_parked_pr_is_unparked(self):
        PC.unpark_phase([self.parked(2)], [2], [])
        self.assertIn(("gh", "pr", "ready", "2", "--repo", PC.REPO), self.calls)

    def test_after_cutover_every_parked_pr_is_unparked_once(self):
        self.cut = True
        PC.unpark_phase([self.parked(2), self.parked(3)], [], [])
        self.assertIn(("gh", "pr", "ready", "2", "--repo", PC.REPO), self.calls)
        self.assertIn(("gh", "pr", "ready", "3", "--repo", PC.REPO), self.calls)
        self.assertEqual(len([c for c in self.calls if "--remove-label" in c]), 2)


class FindingsGate(Base):
    def setUp(self):
        super().setUp()
        self.cut = True
        PC.fetch_pr_rest = lambda n: mkpr(n)
        self.addCleanup(lambda: setattr(PC, "fetch_pr_rest", FETCH))
        self.t = time.sleep
        PC.time.sleep = lambda s: None
        self.addCleanup(lambda: setattr(PC.time, "sleep", self.t))

    def run_gate(self, conclusion, status="completed"):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5))
        self.runs = [{"id": 1, "path": ".github/workflows/pr-blocking-findings.yml", "status": status,
                      "conclusion": conclusion, "created_at": now}]
        return PC.findings_gate_cli(7)

    def test_success_is_zero_and_dispatches_only_the_findings_workflow(self):
        self.assertEqual(self.run_gate("success"), 0)
        self.assertEqual(self.dispatched(), ["pr-blocking-findings.yml"])

    def test_failure_is_one(self):
        self.assertEqual(self.run_gate("failure"), 1)

    def test_timeout_is_one(self):
        PC.FINDINGS_WAIT_SECS = 0
        self.addCleanup(setattr, PC, "FINDINGS_WAIT_SECS", 300)
        self.assertEqual(self.run_gate(None, "in_progress"), 1)

    def test_before_cutover_and_kill_switch_are_not_applicable(self):
        self.cut = False
        self.assertEqual(self.run_gate("failure"), 3)
        self.cut = True
        os.environ["PR_COORDINATOR_DISPATCH"] = "0"
        self.assertEqual(self.run_gate("failure"), 3)
        self.assertEqual(self.posts, [])


class Misc(unittest.TestCase):
    def test_runaway_attention_at_threshold_once_a_day(self):
        seen, att = {}, []
        PC.runaway_page([1] * (PC.RUNAWAY_THRESHOLD - 1), seen, att)
        self.assertEqual(att, [])
        PC.runaway_page([1] * PC.RUNAWAY_THRESHOLD, seen, att)
        PC.runaway_page([1] * PC.RUNAWAY_THRESHOLD, seen, att)
        self.assertEqual([a["kind"] for a in att], ["pr-queue-runaway"])
        self.assertEqual(PC.RUNAWAY_THRESHOLD, 25)


class OwnPrApproval(Base):
    """Owner 2026-11-28: a ledger approve applies to EXTERNAL PRs only."""
    class R:
        def hgetall(self, k): return {}          # no ledger review at all

    def land(self, p):
        log, att, seen = [], [], {}
        saved = PC.proof_status
        PC.proof_status = lambda *a: ""
        PC.review_carries = lambda *a: False
        self.addCleanup(lambda: setattr(PC, "proof_status", saved))
        p.update(reviewThreads={"nodes": []})
        PC.slot_land_phase(p["number"], p, True, self.R(), seen, log, att)
        return log, att

    def test_own_pr_without_ledger_review_merges_when_green(self):
        log, att = self.land(mkpr())
        self.assertIn("merge #7", log)
        self.assertEqual(att, [])

    def test_external_pr_without_approval_does_not_merge(self):
        for extra in ({"isCrossRepository": True}, {"author": {"login": "someone"}}):
            log, att = self.land(mkpr(**extra))
            self.assertNotIn("merge #7", log)
            self.assertEqual([a["kind"] for a in att], ["review"])

    def test_own_pr_with_invalid_proof_does_not_merge(self):
        p = mkpr(reviewThreads={"nodes": []})
        PC.proof_status = lambda *a: "table missing"
        self.addCleanup(lambda: setattr(PC, "proof_status", PC.proof_status))
        log = []
        PC.slot_land_phase(7, p, True, self.R(), {}, log, [])
        self.assertNotIn("merge #7", log)


if __name__ == "__main__":
    unittest.main()
