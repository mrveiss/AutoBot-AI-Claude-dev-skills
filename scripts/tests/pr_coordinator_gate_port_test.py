"""Capabilities ported from the retired pr-queue-gate into scripts/pr-coordinator (#11)."""
import importlib.machinery, importlib.util, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
    loader.exec_module(mod)
    return mod


PC = load()


class GatePort(unittest.TestCase):
    def test_required_context_publishers_exempt(self):
        for name in ("PR Blocking Findings", "No Commit Trailers", "Enforce Pre-commit Hooks", "Issue landing notes"):
            self.assertIn(name, PC.EXEMPT_WORKFLOWS)
        self.assertNotIn("AutoBot CI/CD Pipeline", PC.EXEMPT_WORKFLOWS)

    def test_stale_claims_only_for_closed_prs(self):
        out = PC.stale_pr_claims({5: "a", 6: "b"}, {5})
        self.assertEqual(len(out), 1)
        self.assertIn("#6", out[0])
        self.assertEqual(PC.stale_pr_claims({5: "a"}, {5}), [])


class AtomicState(unittest.TestCase):
    def test_write_goes_through_temp_and_replace(self):
        import os, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "notified.json"
            target.write_text("old", encoding="utf-8")
            real = os.replace
            calls = []
            with mock.patch.object(PC.os, "replace", side_effect=lambda a, b: (calls.append((str(a), str(b))), real(a, b))[1]):
                PC.write_atomic(target, "new")
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][0], str(target))
            self.assertEqual(Path(calls[0][0]).parent, Path(d))
            self.assertEqual(calls[0][1], str(target))
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertEqual(os.listdir(d), ["notified.json"])


if __name__ == "__main__":
    unittest.main()
