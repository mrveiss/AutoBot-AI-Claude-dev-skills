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


if __name__ == "__main__":
    unittest.main()
