"""Requirement-proof gate of scripts/pr-coordinator (#37): table validation, cutoff exemption, main-merge syncs."""
import importlib.machinery, importlib.util, unittest
from pathlib import Path

PATH = str(Path(__file__).resolve().parents[1] / "pr-coordinator")


def load():
    loader = importlib.machinery.SourceFileLoader("pr_coordinator", PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("pr_coordinator", loader))
    loader.exec_module(mod)
    return mod


PC = load()
HEAD = "| AC | Precondition | Postcondition | Establishing lines | Argument | Reviewer |\n|---|---|---|---|---|---|\n"
ROW = "| AC1 | x holds | y holds | a.py:1-9 | because z | alice |\n"


def body(table, heading="## Requirement proofs"):
    return f"Summary\n\n{heading}\n\n{table}\n\nMore text"


class Table(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + ROW)), "")

    def test_header_case_and_spacing_tolerant(self):
        t = "|ac|  PRECONDITION |postcondition|Establishing   Lines|argument|REVIEWER|\n|:--|:-:|--:|---|---|---|\n" + ROW
        self.assertEqual(PC.proof_table_reason(body(t, "##  requirement proofs")), "")

    def test_na_row_accepted(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| — | n/a | n/a | f.py:3 | pure rename | alice |")), "")
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| - | n/a | n/a | f.py:3 | pure rename | alice |")), "")

    def test_na_row_needs_argument(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| — | n/a | n/a | f.py:3 |  | alice |")))

    def test_missing_heading(self):
        self.assertIn("heading", PC.proof_table_reason(HEAD + ROW))

    def test_empty_cell(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | x | | a.py:1 | z | alice |")))

    def test_missing_reviewer(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | x | y | a.py:1 | z |  |")))
        t = "| AC | Precondition | Postcondition | Establishing lines | Argument |\n|---|---|---|---|---|\n| 1 | a | b | c | d |"
        self.assertIn("header", PC.proof_table_reason(body(t)))

    def test_zero_rows(self):
        self.assertIn("no data row", PC.proof_table_reason(body(HEAD.rstrip("\n"))))


class Exempt(unittest.TestCase):
    """History: old(2026-11-20) <- merge M1 of main <- merge M2 of main; new work N is 2026-11-24."""
    COMMITS = {"old": ("old", "base", "2026-11-20T08:00:00Z"), "m1": ("m1", "old,mainA", "2026-11-24T08:00:00Z"),
               "m2": ("m2", "m1,mainB", "2026-11-25T08:00:00Z"), "new": ("new", "m2", "2026-11-24T09:00:00Z"),
               "base": ("base", "x", "2026-11-01T00:00:00Z")}

    def setUp(self):
        self.force = ""
        def fake(*a, **k):
            if "compare" in a[2]:
                return "ahead" if a[2].split("/")[-1].startswith("mainA") or "mainB" in a[2] else "diverged"
            if "timeline" in a[2]:
                return self.force
            return "\t".join(self.COMMITS[a[2].split("/")[-1]])
        PC.sh = fake
        PC._PROOF.clear()

    def test_only_main_merges_after_exempt_head_stays_exempt(self):
        self.assertTrue(PC.head_is_exempt(5, "m2"))

    def test_real_commit_after_cutoff_is_not_exempt(self):
        self.assertFalse(PC.head_is_exempt(5, "new"))

    def test_force_push_after_cutoff_is_not_exempt(self):
        self.force = "2026-11-23T12:00:00Z"
        self.assertFalse(PC.head_is_exempt(5, "m2"))

    def test_status_blocks_and_dedupes(self):
        p = {"number": 5, "headRefOid": "new", "headRefName": "b", "body": "", "owner": "o", "alive": "a"}
        seen, log, att = {}, [], []
        self.assertTrue(PC.proof_blocked(p, seen, log, att))
        self.assertTrue(PC.proof_blocked(p, seen, log, att))
        self.assertEqual((len(log), len(att), att[0]["kind"]), (1, 1, "proof-missing"))
        self.assertTrue(log[0].startswith("#5 blocked: requirement-proof table missing/invalid ("))

    def test_valid_table_never_blocks(self):
        p = {"number": 5, "headRefOid": "new", "headRefName": "b", "body": body(HEAD + ROW)}
        self.assertFalse(PC.proof_blocked(p, {}, [], []))


if __name__ == "__main__":
    unittest.main()
