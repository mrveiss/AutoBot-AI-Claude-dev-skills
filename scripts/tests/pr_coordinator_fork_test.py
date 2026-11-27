"""External (fork) PRs in scripts/pr-coordinator (#73): slotted like own PRs; a behind fork head needs maintainer edits."""
import importlib.machinery, importlib.util, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")
loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
PC = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
loader.exec_module(PC)
HEAD = "b" * 40


class ForkUpdateStep(unittest.TestCase):
    def setUp(self):
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

    def pr(self, n, repo, branch="issue-1-x", head="c" * 40):
        return {"number": n, "headRefName": branch, "headRefOid": head, "headRepository": {"nameWithOwner": repo}}

    def test_same_branch_name_in_fork_and_base_resolves_by_repo(self):
        own, fork = self.pr(1, PC.REPO), self.pr(2, "someone/fork")
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, PC.REPO, [own, fork]), (own, False))
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, "someone/fork", [own, fork]), (fork, False))

    def test_two_forks_same_branch_are_narrowed_by_sha_else_ambiguous(self):
        a, b = self.pr(3, "a/fork", head="a" * 40), self.pr(4, "a/fork", head="b" * 40)
        self.assertEqual(PC.attribute_run("issue-1-x", "b" * 40, "a/fork", [a, b]), (b, False))
        self.assertEqual(PC.attribute_run("issue-1-x", "z" * 40, "a/fork", [a, b]), (None, True))

    def test_fork_run_without_open_pr_is_not_attributed_to_own_branch(self):
        self.assertEqual(PC.attribute_run("issue-1-x", "d" * 40, "other/fork", [self.pr(1, PC.REPO)]), (None, False))

    def test_protected_applies_only_to_this_repos_branches(self):
        self.assertTrue(PC.is_protected("main", PC.REPO))
        self.assertFalse(PC.is_protected("main", "someone/fork"))


if __name__ == "__main__":
    unittest.main()
