"""External (fork) PRs in scripts/pr-coordinator (#73): slotted like own PRs; a behind fork head needs maintainer edits."""
import importlib.machinery, importlib.util, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")
loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
PC = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
loader.exec_module(PC)
HEAD = "b" * 40


def restore_after(test):
    """Put PC.sh / PC.DRY / PC.cancel / PC.RECENT back after the test (they are module globals)."""
    saved = (PC.sh, PC.DRY, PC.cancel, dict(PC.RECENT))
    def undo():
        PC.sh, PC.DRY, PC.cancel = saved[:3]
        PC.RECENT.clear(); PC.RECENT.update(saved[3])
    test.addCleanup(undo)


def mkpr(n, repo, branch="issue-1-x", head="c" * 40, **extra):
    return {"number": n, "headRefName": branch, "headRefOid": head, "headRepository": {"nameWithOwner": repo}, **extra}


class ForkUpdateStep(unittest.TestCase):
    def setUp(self):
        restore_after(self)
        PC.DRY, self.calls = False, []
        PC.sh = lambda *a, **k: self.calls.append(a) or "#7 UPDATE behind=2 reason=x"
        self.p = {"number": 7, "headRefOid": HEAD, "headRefName": "fork-br", "title": "t", "owner": "o", "alive": "a",
                  "isCrossRepository": True, "maintainerCanModify": False}

    def test_no_maintainer_edits_pages_once_and_skips_update_branch(self):
        seen, log, att = {}, [], []
        self.assertTrue(PC._update_step(7, self.p, False, seen, log, att))
        self.assertTrue(PC._update_step(7, self.p, False, seen, log, att))
        self.assertEqual([a["kind"] for a in att], ["needs manual sync"])
        self.assertFalse([c for c in self.calls if "update-branch" in " ".join(c)])

    def test_blocked_fork_pages_only_when_green(self):
        gate = {"v": "#7 abc WAIT"}
        PC.sh = lambda *a, **k: "#7 UPDATE behind=2 reason=x" if "behind-ok" in a[0] else gate["v"]
        seen, att = {}, []
        PC._update_step(7, self.p, True, seen, [], att)
        self.assertEqual(att, [])
        gate["v"] = "#7 abc GREEN"
        PC._update_step(7, self.p, True, seen, [], att)
        self.assertEqual(len(att), 1)

    def test_maintainer_edits_allowed_calls_update_branch(self):
        self.p["maintainerCanModify"] = True
        seen, log, att = {}, [], []
        self.assertTrue(PC._update_step(7, self.p, False, seen, log, att))
        self.assertFalse(att)
        self.assertTrue([c for c in self.calls if "update-branch" in " ".join(c)])

    def test_no_owner_filter_left(self):
        self.assertFalse(hasattr(PC, "OWN_AUTHORS"))


class RunAttribution(unittest.TestCase):
    """A fork branch named like an own branch must never be mistaken for it (#73)."""

    def test_same_branch_name_in_fork_and_base_resolves_by_repo(self):
        own, fork = mkpr(1, PC.REPO), mkpr(2, "someone/fork")
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, PC.REPO, [own, fork]), [own])
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, "someone/fork", [own, fork]), [fork])

    def test_two_forks_same_branch_are_narrowed_by_sha(self):
        a, b = mkpr(3, "a/fork", head="a" * 40), mkpr(4, "a/fork", head="b" * 40)
        self.assertEqual(PC.attribute_run("issue-1-x", "b" * 40, "a/fork", [a, b]), [b])
        self.assertEqual(PC.attribute_run("issue-1-x", "z" * 40, "a/fork", [a, b]), [a, b])

    def test_deleted_fork_does_not_wildcard_match_another_repo(self):
        gone = {"number": 5, "headRefName": "issue-1-x", "headRefOid": "c" * 40, "headRepository": None}
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, PC.REPO, [gone]), [])
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, "", [gone]), [gone])

    def test_protected_applies_only_to_this_repos_branches(self):
        self.assertTrue(PC.is_protected("main", PC.REPO))
        self.assertFalse(PC.is_protected("main", "someone/fork"))


class SweepRuns(unittest.TestCase):
    """The run loop shared by main() and degraded_tick()."""

    def setUp(self):
        restore_after(self)
        PC.DRY, self.cancelled = True, []
        PC.cancel = lambda rid, branch, n, reason, log: self.cancelled.append((rid, n, reason))

    def sweep(self, runs, prs, slots=(), keep=()):
        log = []
        PC.sweep_runs(runs, prs, lambda p: "" if p["number"] in slots else "no slot", set(keep), "orphan", log)
        return log

    def test_fork_run_named_like_an_own_slot_branch_does_not_ride_the_slot(self):
        own, fork = mkpr(1, PC.REPO), mkpr(2, "someone/fork")
        self.sweep([("10", "issue-1-x", "d" * 40, "pull_request", "someone/fork")], [own, fork], slots={1})
        self.assertEqual(self.cancelled, [("10", 2, "no slot")])

    def test_ambiguous_run_with_disagreeing_candidates_is_left_and_logged_once(self):
        a, b = mkpr(3, "a/fork", head="a" * 40), mkpr(4, "a/fork", head="b" * 40)
        run = ("11", "issue-1-x", "z" * 40, "pull_request", "a/fork")
        log = self.sweep([run], [a, b], slots={3})
        log += self.sweep([run], [a, b], slots={3})
        self.assertEqual(self.cancelled, [])
        self.assertEqual(len(log), 1)

    def test_ambiguous_run_with_agreeing_candidates_is_acted_on(self):
        a, b = mkpr(3, "a/fork", head="a" * 40), mkpr(4, "a/fork", head="b" * 40)
        self.sweep([("12", "issue-1-x", "z" * 40, "pull_request", "a/fork")], [a, b], slots=set())
        self.assertEqual([c[2] for c in self.cancelled], ["no slot"])

    def test_deleted_fork_run_with_null_head_repo_resolves_to_its_pr(self):
        gone = {"number": 5, "headRefName": "issue-9", "headRefOid": "c" * 40, "headRepository": None}
        self.sweep([("13", "issue-9", "c" * 40, "pull_request", "")], [gone], slots=set())
        self.assertEqual(self.cancelled, [("13", 5, "no slot")])

    def test_orphan_run_cancelled_unless_its_head_holds_a_slot(self):
        self.sweep([("14", "gone", "d" * 40, "push", PC.REPO)], [])
        self.sweep([("15", "kept", "d" * 40, "push", PC.REPO)], [], keep={(PC.REPO, "kept")})
        self.assertEqual(self.cancelled, [("14", "-", "orphan")])

    def test_protected_run_is_never_touched_but_a_fork_main_is_an_ordinary_head(self):
        fork = mkpr(6, "someone/fork", branch="main")
        self.sweep([("16", "main", "d" * 40, "push", PC.REPO), ("17", "main", "d" * 40, "pull_request", "someone/fork")], [fork])
        self.assertEqual(self.cancelled, [("17", 6, "no slot")])

    def test_degraded_tick_shapes(self):
        """5-field runs and the 4-field REST PR shape (no red, no mergeStateStatus) classify without error."""
        rest = {"number": 7, "headRefName": "b", "headRefOid": "c" * 40, "headRepository": {"nameWithOwner": PC.REPO}}
        self.sweep([("18", "b", "c" * 40, "push", PC.REPO)], [rest], slots=set())
        self.assertEqual(self.cancelled, [("18", 7, "no slot")])


class ActionsRunsParsing(unittest.TestCase):
    def test_empty_head_repository_field_keeps_the_run_with_empty_repo(self):
        restore_after(self)
        PC.sh = lambda *a, **k: "9\tissue-9\tsha\tpull_request\t\tAutoBot CI/CD Pipeline"
        self.assertEqual(PC.actions_runs()[0][:5], ["9", "issue-9", "sha", "pull_request", ""])


class ForkGates(unittest.TestCase):
    def test_behind_fork_without_maintainer_edits_is_stuck_but_not_an_own_pr(self):
        fork = {"isCrossRepository": True, "maintainerCanModify": False, "mergeStateStatus": "BEHIND"}
        self.assertTrue(PC.fork_stuck_behind(fork))
        self.assertFalse(PC.fork_stuck_behind({**fork, "maintainerCanModify": True}))
        self.assertFalse(PC.fork_stuck_behind({**fork, "mergeStateStatus": "CLEAN"}))
        self.assertFalse(PC.fork_stuck_behind({**fork, "isCrossRepository": False}))

    def test_action_required_only_on_a_fork_is_awaiting_approval_not_red(self):
        fork = {"isCrossRepository": True, "action_required": ["ci"]}
        self.assertTrue(PC.fork_awaiting_approval(fork, ["ci"]))
        self.assertFalse(PC.fork_awaiting_approval(fork, ["ci", "lint"]))
        self.assertFalse(PC.fork_awaiting_approval({**fork, "isCrossRepository": False}, ["ci"]))

    def test_owner_lookup_skips_ledger_claims_for_forks(self):
        class R:
            def hget(self, *a): return ""
            def hgetall(self, k): raise AssertionError("claim lookup for a fork")
        class L:
            def alive(self, r, n): return "a"
        self.assertEqual(PC.owner_of(R(), L(), {"number": 1, "headRefName": "x", "isCrossRepository": True}), ("-", "unknown"))

    def test_fork_start_ci_is_not_dispatched_to_the_sync(self):
        restore_after(self)
        PC.DRY, calls = False, []
        PC.sh = lambda *a, **k: calls.append(a) or "0"
        p = {"number": 8, "headRefOid": HEAD, "isCrossRepository": True, "total": 1, "owner": "o", "alive": "a",
             "headRefName": "f", "title": "t"}
        PC.start_ci_or_report(8, p, "#8 " + HEAD[:9] + " WAIT", {}, [], [])
        self.assertFalse([c for c in calls if "workflow" in c and "run" in c])


if __name__ == "__main__":
    unittest.main()
