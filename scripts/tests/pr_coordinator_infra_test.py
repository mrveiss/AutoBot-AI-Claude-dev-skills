"""is_infra_failure / infra_rerun of scripts/pr-coordinator (#35): infra log tails classify as infra, code failures never do."""
import importlib.machinery, importlib.util, sys, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
    loader.exec_module(mod)
    return mod


PC = load()
INFRA = {
    "apt": "Err:1 http://azure.archive.ubuntu.com/ubuntu jammy InRelease\n  Temporary failure resolving 'azure.archive.ubuntu.com'\nE: Failed to fetch http://x\n##[error]Process completed with exit code 100.",
    "dns": "curl: (6) Could not resolve host: github.com\n##[error]Process completed with exit code 6.",
    "shutdown": "##[error]The runner has received a shutdown signal. This can happen when the runner service is stopped.",
    "disk": "OSError: [Errno 28] No space left on device\n##[error]Process completed with exit code 1.",
    "action": "##[error]Failed to download action 'https://api.github.com/repos/actions/checkout/tarball/abc'.",
}
CODE = {
    "pytest": "FAILED tests/test_a.py::test_x - AssertionError: assert 1 == 2\n== 1 failed, 40 passed in 3.2s ==",
    "vitest": 'Error: [vitest] No export is defined on the "@/utils/x" mock. Did you want to return the actual module?\nTest Files  1 failed (3)',
    "bare error": "ERROR: something broke\nconnection timeout in test fixture\n##[error]Process completed with exit code 1.",
    "empty": "",
    "infra word plus test failure": "Temporary failure resolving 'x' (retried)\nFAILED tests/test_a.py::test_x - assert False\n1 failed, 2 passed in 1s",
}


class Classify(unittest.TestCase):
    def test_infra(self):
        for name, tail in INFRA.items():
            self.assertTrue(PC.is_infra_failure(tail), name)

    def test_code(self):
        for name, tail in CODE.items():
            self.assertFalse(PC.is_infra_failure(tail), name)


TS = "2026-11-23T09:12:03.1234567Z "


def stamped(text):
    return "\n".join(TS + line for line in text.splitlines())


class Timestamped(unittest.TestCase):
    def classify(self, text):
        return PC.is_infra_failure(PC.clean_log(stamped(text)))

    def test_apt_is_infra(self):
        self.assertTrue(self.classify(INFRA["apt"]))

    def test_pytest_lines_without_summary_are_code(self):
        self.assertFalse(self.classify("FAILED a::b - boom\nTemporary failure resolving 'x'"))
        self.assertFalse(self.classify("E   assert 1 == 2\nTemporary failure resolving 'x'"))

    def test_prefix_stripped(self):
        self.assertEqual(PC.clean_log(TS + "hello"), "hello")


class Rerun(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.tails = {1: INFRA["apt"], 2: INFRA["dns"], 3: CODE["pytest"]}
        PC.log_tail = lambda job: self.tails[job]
        PC.sh = lambda *a, **k: (self.calls.append(a), "777")[1]
        PC.DRY = False
        self.log, self.seen = [], {}

    def pr(self, red):
        ok = "## Requirement proofs\n\n| AC | Precondition | Postcondition | Establishing lines | Argument | Reviewer |\n|---|---|---|---|---|---|\n| 1 | a | b | c | d | e |"
        return {"number": 9, "headRefOid": "abc", "body": ok, "red": red, "red_ids": {c: i for c, i in red_ids.items() if c in red}}

    def test_once_then_red(self):
        p = self.pr(["a"])
        self.assertEqual(PC.infra_rerun(p, self.seen, self.log), [])
        self.assertTrue(self.log[0].startswith("INFRA-RERUN #9 a"))
        self.assertIn(("gh", "run", "rerun", "777", "--failed", "--repo", PC.REPO), self.calls)
        self.assertEqual(PC.infra_rerun(p, self.seen, self.log), ["a"])   # second failure at same head: red

    def test_any_code_failure_keeps_red_and_does_not_rerun(self):
        self.assertEqual(PC.infra_rerun(self.pr(["a", "c"]), self.seen, self.log), ["a", "c"])
        self.assertFalse(any(c[:3] == ("gh", "run", "rerun") for c in self.calls))
        self.assertEqual(self.seen, {})


red_ids = {"a": 1, "b": 2, "c": 3}

if __name__ == "__main__":
    unittest.main()
