"""CLI argument handling and the pass self-lock of scripts/pr-coordinator (#57)."""
import contextlib, fcntl, importlib.machinery, importlib.util, io, os, tempfile, unittest
from pathlib import Path
from unittest import mock

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator_cli", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator_cli", loader))
    loader.exec_module(mod)
    return mod


PC = load()


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = PC.run_cli(argv)
    return code, out.getvalue()


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(PC, "LOCK_PATH", os.path.join(self.tmp.name, "lock"))
        p.start()
        self.addCleanup(p.stop)
        m = mock.patch.object(PC, "main")
        self.main = m.start()
        self.addCleanup(m.stop)

    def test_help_runs_no_pass(self):
        for flag in ("--help", "-h"):
            code, out = run([flag])
            self.assertEqual(code, 0)
            self.assertIn("usage:", out)
        self.main.assert_not_called()

    def test_unknown_arg_runs_no_pass(self):
        code, out = run(["--bogus"])
        self.assertEqual(code, 2)
        self.assertIn("usage:", out)
        self.main.assert_not_called()

    def test_live_pass_runs_and_releases_lock(self):
        self.assertIsNone(run([])[0])
        self.main.assert_called_once()
        fh = PC.take_pass_lock()
        self.assertIsNotNone(fh)
        fh.close()

    def test_live_pass_exits_when_lock_held(self):
        with open(PC.LOCK_PATH, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, out = run([])
        self.assertEqual(code, 0)
        self.assertIn("another coordinator pass is running", out)
        self.main.assert_not_called()

    def test_read_only_modes_ignore_the_lock(self):
        with open(PC.LOCK_PATH, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIsNone(run(["--dry"])[0])
            self.main.assert_called_once()
            with mock.patch.object(PC, "proof_check_cli", return_value=0) as pc:
                self.assertEqual(run(["--proof-check", "7"])[0], 0)
                pc.assert_called_once_with("7")


if __name__ == "__main__":
    unittest.main()
