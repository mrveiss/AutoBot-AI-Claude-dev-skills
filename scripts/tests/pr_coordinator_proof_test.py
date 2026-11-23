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
START_CI = PC.START_CI_SUBJECT
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

    def test_escaped_pipe_cell_both_directions(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| AC1 | a \\| b | y | f.py:1 | c \\| d | alice |")), "")
        self.assertEqual(PC._cells("| a \\| b | c |"), ["a | b", "c"])
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | a | b | f.py:1 | c | d | alice |")))

    def test_table_under_another_heading(self):
        self.assertIn("heading", PC.proof_table_reason("## Notes\n\n" + HEAD + ROW))

    def test_prose_before_table(self):
        self.assertEqual(PC.proof_table_reason(body("Proofs below, one per AC.\n\nSecond line.\n\n" + HEAD + ROW)), "")

    def test_html_comment_before_table(self):
        self.assertEqual(PC.proof_table_reason(body("<!-- fill in -->\n\n" + HEAD + ROW)), "")

    def test_table_only_in_later_section(self):
        r = PC.proof_table_reason("## Requirement proofs\n\nnone yet\n\n## Notes\n\n" + HEAD + ROW)
        self.assertIn("no table", r)

    def test_fenced_fake_table_before_real(self):
        fake = "```\n" + HEAD + "| AC9 | bad | | | | |\n```\n\n"
        self.assertEqual(PC.proof_table_reason(body(fake + HEAD + ROW)), "")

    def test_fenced_fake_heading(self):
        fenced = "```\n## Requirement proofs\n\n" + HEAD + ROW + "```\n"
        self.assertIn("heading", PC.proof_table_reason(fenced))

    def test_bad_separator(self):
        bad = HEAD.replace("|---|---|---|---|---|---|", "|---|---|---|")
        self.assertIn("separator", PC.proof_table_reason(body(bad + ROW)))
        self.assertIn("separator", PC.proof_table_reason(body(HEAD.replace("---|---|---|---|---|---", "a|b|c|d|e|f") + ROW)))

    def test_zero_rows(self):
        self.assertIn("no data row", PC.proof_table_reason(body(HEAD.rstrip("\n"))))


class Exempt(unittest.TestCase):
    """History: old(2026-11-20) <- merge M1 of main <- merge M2 of main; new work N is 2026-11-24."""
    COMMITS = {"old": ("old", "base", "2026-11-20T08:00:00Z", "t-old", "feat: work"),
               "m1": ("m1", "old,mainA", "2026-11-24T08:00:00Z", "t-m1", "Merge main"),
               "m2": ("m2", "m1,mainB", "2026-11-25T08:00:00Z", "t-m2", "Merge main"),
               "new": ("new", "m2", "2026-11-24T09:00:00Z", "t-new", "feat: more"),
               "base": ("base", "x", "2026-11-01T00:00:00Z", "t-base", "root"),
               "ci": ("ci", "m2", "2026-11-26T08:00:00Z", "t-m2", START_CI + " (#5)"),
               "cifiles": ("cifiles", "m2", "2026-11-26T08:00:00Z", "t-other", START_CI + " (#5)"),
               "empty": ("empty", "m2", "2026-11-26T08:00:00Z", "t-m2", "chore: nothing")}

    def setUp(self):
        self.force = ""
        def fake(*a, **k):
            if "compare" in a[2]:
                return "ahead" if a[2].split("/")[-1].startswith("mainA") or "mainB" in a[2] else "diverged"
            c = self.COMMITS[a[2].split("/")[-1]]
            return c[3] if a[-1] == ".commit.tree.sha" else "\t".join(c)
        PC.sh = fake
        self.timeline_ok = True
        PC._force_push_times = lambda n: (self.timeline_ok, self.force.split())
        PC.PROOF_CUTOFF = "2026-11-23T11:36:00Z"

    def pr(self, head, created="2026-11-01T00:00:00Z"):
        return {"number": 5, "headRefOid": head, "createdAt": created, "headRefName": "b", "body": ""}

    def test_timeline_api_error_fails_closed(self):
        self.timeline_ok = False
        self.assertIsNone(PC.head_is_exempt(self.pr("m2")))
        seen = {}
        self.assertIn("failing closed", PC.proof_status(self.pr("m2"), seen))
        self.assertEqual(seen, {})

    def test_pr_created_after_cutoff_never_exempt(self):
        self.assertFalse(PC.head_is_exempt(self.pr("m2", "2026-11-23T12:00:00Z")))

    def test_plus_zero_offset_cutoff_override(self):
        PC.PROOF_CUTOFF = "2026-11-24T09:00:00+00:00"
        self.assertTrue(PC.head_is_exempt(self.pr("new")))
        PC.PROOF_CUTOFF = "2026-11-24T08:59:59+00:00"
        self.assertFalse(PC.head_is_exempt(self.pr("new")))

    def test_verdict_persisted_in_seen(self):
        seen = {}
        self.assertEqual(PC.proof_status(self.pr("m2"), seen), "")
        self.assertEqual(seen, {"5:proof-exempt:m2": 1})
        PC.sh = lambda *a, **k: self.fail("API called again")
        self.assertEqual(PC.proof_status(self.pr("m2"), seen), "")

    def test_only_main_merges_after_exempt_head_stays_exempt(self):
        self.assertTrue(PC.head_is_exempt(self.pr("m2")))

    def test_start_ci_commit_on_exempt_head_stays_exempt(self):
        self.assertTrue(PC.head_is_exempt(self.pr("ci")))

    def test_start_ci_titled_commit_with_files_is_not_skipped(self):
        self.assertFalse(PC.head_is_exempt(self.pr("cifiles")))

    def test_empty_commit_with_other_subject_is_not_skipped(self):
        self.assertFalse(PC.head_is_exempt(self.pr("empty")))

    def test_real_commit_after_cutoff_is_not_exempt(self):
        self.assertFalse(PC.head_is_exempt(self.pr("new")))

    def test_force_push_after_cutoff_is_not_exempt(self):
        self.force = "2026-11-23T12:00:00Z"
        self.assertFalse(PC.head_is_exempt(self.pr("m2")))

    def test_status_blocks_and_dedupes(self):
        p = {**self.pr("new"), "owner": "o", "alive": "a"}
        seen, log, att = {}, [], []
        self.assertTrue(PC.proof_blocked(p, seen, log, att))
        self.assertTrue(PC.proof_blocked(p, seen, log, att))
        self.assertEqual((len(log), len(att), att[0]["kind"]), (1, 1, "proof-missing"))
        self.assertTrue(log[0].startswith("#5 blocked: requirement-proof table missing/invalid ("))

    def test_valid_table_never_blocks(self):
        p = {"number": 5, "headRefOid": "new", "headRefName": "b", "body": body(HEAD + ROW)}
        self.assertFalse(PC.proof_blocked(p, {}, [], []))


class Gating(unittest.TestCase):
    """The gate bars only the CI starters: a green, approved, barred PR still merges."""
    def setUp(self):
        self.calls = []
        PC.DRY = False
        PC.sh = lambda *a, **k: (self.calls.append(a), "GREEN" if a[0].endswith("ci-gate") else "")[1]
        PC.review_carries = lambda *a: True
        PC.MIGRATION_GROUP = set()
        self.p = {"number": 7, "headRefOid": "h", "headRefName": "b", "body": "", "createdAt": "2026-11-24T00:00:00Z",
                  "reviewThreads": {"nodes": []}, "owner": "o", "alive": "a"}

    class R:
        def hgetall(self, k):
            return {"review_verdict": "approve", "review_sha": "h"}

    def test_green_barred_pr_continues_to_merge(self):
        log, att, seen = [], [], {}
        self.assertTrue(PC.proof_blocked(self.p, seen, log, att))
        self.assertFalse(PC.slot_ci_phase(7, self.p, True, seen, log, att))
        PC.slot_land_phase(7, self.p, True, self.R(), seen, log, att)
        self.assertIn("merge #7", log)
        self.assertTrue(any(c[0].endswith("safe-merge") for c in self.calls))

    def test_barred_non_green_pr_starts_no_ci(self):
        PC.sh = lambda *a, **k: (self.calls.append(a), "RED" if a[0].endswith("ci-gate") else "")[1]
        self.assertTrue(PC.slot_ci_phase(7, self.p, True, {}, [], []))
        self.assertFalse(any(c[:2] in (("gh", "run"), ("gh", "workflow")) for c in self.calls))


class CutoffEnv(unittest.TestCase):
    def test_malformed_cutoff_fails_at_import(self):
        import os
        for bad in ("yesterday", "2026-11-23T11:36:00"):
            os.environ["PR_COORDINATOR_PROOF_CUTOFF"] = bad
            try:
                with self.assertRaises(SystemExit) as cm:
                    load()
                self.assertIn("PR_COORDINATOR_PROOF_CUTOFF", str(cm.exception))
            finally:
                del os.environ["PR_COORDINATOR_PROOF_CUTOFF"]

    def test_plus_zero_cutoff_loads(self):
        import os
        os.environ["PR_COORDINATOR_PROOF_CUTOFF"] = "2026-11-23T11:36:00+00:00"
        try:
            self.assertEqual(load().PROOF_CUTOFF, "2026-11-23T11:36:00+00:00")
        finally:
            del os.environ["PR_COORDINATOR_PROOF_CUTOFF"]


class InfraRefuses(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(PC, k) for k in ("head_is_exempt", "sh", "log_tail")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(PC, k, v)

    def test_infra_rerun_refuses_barred_head(self):
        PC.log_tail = lambda job: "Temporary failure resolving 'x'\n##[error]Process completed with exit code 100."
        calls = []
        PC.sh = lambda *a, **k: (calls.append(a), "")[1]
        PC.head_is_exempt = lambda p: False
        p = {"number": 9, "headRefOid": "abc", "body": "", "red": ["a"], "red_ids": {"a": 1}}
        self.assertEqual(PC.infra_rerun(p, {}, []), ["a"])
        self.assertFalse(any(c[:2] == ("gh", "run") for c in calls))


if __name__ == "__main__":
    unittest.main()
