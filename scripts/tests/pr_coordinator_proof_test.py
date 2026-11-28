"""Requirement-proof gate of scripts/pr-coordinator (#37): table validation, cutoff exemption, main-merge syncs."""
import importlib.machinery, importlib.util, json, os, subprocess, tempfile, time, unittest
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
ROW = "| AC1 | x holds | y holds | a.py:1-9 | because z | reviewer: holds |\n"


def body(table, heading="## Requirement proofs"):
    return f"Summary\n\n{heading}\n\n{table}\n\nMore text"


class Table(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + ROW)), "")

    def test_header_case_and_spacing_tolerant(self):
        t = "|ac|  PRECONDITION |postcondition|Establishing   Lines|argument|REVIEWER|\n|:--|:-:|--:|---|---|---|\n" + ROW
        self.assertEqual(PC.proof_table_reason(body(t, "##  requirement proofs")), "")

    def test_annotated_header_passes(self):
        t = HEAD.replace("Establishing lines", "Establishing lines (file:line)").replace("Argument", "Argument (why EVERY input satisfies it)")
        self.assertEqual(PC.proof_table_reason(body(t + ROW)), "")

    def test_annotated_wrong_base_name_fails(self):
        t = HEAD.replace("Establishing lines", "Lines (file:line)")
        self.assertIn("header", PC.proof_table_reason(body(t + ROW)))

    def test_annotation_on_every_column_passes(self):
        t = "| AC (id) | Precondition (before) | Postcondition (after) | Establishing lines (file:line) | Argument (why) | Reviewer (who) |\n|---|---|---|---|---|---|\n"
        self.assertEqual(PC.proof_table_reason(body(t + ROW)), "")

    def test_na_row_accepted(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| — | n/a | n/a | f.py:3 | pure rename | reviewer: holds |")), "")
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| - | n/a | n/a | f.py:3 | pure rename | reviewer: holds |")), "")

    def test_na_row_needs_argument(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| — | n/a | n/a | f.py:3 |  | reviewer: holds |")))

    def test_reviewer_verdict(self):
        def reason(cell):
            return PC.proof_table_reason(body(HEAD + f"| AC1 | x | y | a.py:1 | z | {cell} |"))
        for ok in ("reviewer: holds at abc123", "Holds", "REVIEWER: HOLDS AT abc", "holds \u2014 failure path covered", "verified at abc",
                   "reviewer: **verified**", "holds \u2014 failsafe covered",
                   "reviewer: holds at 35d7798355 (prior finding fixed: npm ci hint first in the FAIL headline at pr-preflight.sh:739)",
                   "reviewer (independent subagent): holds at abc", "autobot-dev-skills:reviewer \u2014 holds", "**holds**"):
            self.assertEqual(reason(ok), "", ok)
        for bad in ("autobot-dev-skills:reviewer \u2014 fails: x", "does not hold", "doesn't hold", "blocked",
                    "changes requested", "reviewer: ok", "fails: x", "not verified", "no longer holds", "reviewer: not verified",
                    "reviewer: doesn\u2019t hold"):
            self.assertIn("verdict is not 'holds'", reason(bad), bad)

    def test_missing_heading(self):
        self.assertIn("heading", PC.proof_table_reason(HEAD + ROW))

    def test_empty_cell(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | x | | a.py:1 | z | reviewer: holds |")))

    def test_unsigned_reviewer_placeholders_fail(self):
        for cell in ("pending", "TBD", " Pending ", "todo", "?", "-", "\u2014"):
            row = f"| AC1 | x | y | a.py:1 | z | {cell} |"
            self.assertEqual(PC.proof_table_reason(body(HEAD + row)), "row 1: Reviewer not signed", cell)

    def test_signed_reviewer_passes(self):
        row = "| AC1 | x | y | a.py:1 | z | reviewer: holds at abc1234 |"
        self.assertEqual(PC.proof_table_reason(body(HEAD + row)), "")

    def test_missing_reviewer(self):
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | x | y | a.py:1 | z |  |")))
        t = "| AC | Precondition | Postcondition | Establishing lines | Argument |\n|---|---|---|---|---|\n| 1 | a | b | c | d |"
        self.assertIn("header", PC.proof_table_reason(body(t)))

    def test_escaped_pipe_cell_both_directions(self):
        self.assertEqual(PC.proof_table_reason(body(HEAD + "| AC1 | a \\| b | y | f.py:1 | c \\| d | reviewer: holds |")), "")
        self.assertEqual(PC._cells("| a \\| b | c |"), ["a | b", "c"])
        self.assertIn("empty", PC.proof_table_reason(body(HEAD + "| AC1 | a | b | f.py:1 | c | d | reviewer: holds |")))

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


class PatchIdCarry(unittest.TestCase):
    """Owner 2026-11-28: an approval carries when the PR's own diff (vs its merge-base with main) is unchanged."""
    def git(self, *a):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        return subprocess.run(["git", "-C", self.work, *a], check=True, capture_output=True, text=True, env=env).stdout.strip()

    def commit(self, name, text):
        Path(self.work, name).write_text(text, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD")

    def setUp(self):
        self.mod = load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work, bare = str(Path(tmp.name, "work")), Path(tmp.name, "cache.git")
        self.git_init(bare)
        self.base = self.commit("base.txt", "base\n")
        self.git("checkout", "-q", "-b", "pr")
        self.approved = self.commit("pr.txt", "own change\n")
        self.git("checkout", "-q", "main")
        self.main2 = self.commit("main.txt", "later main\n")
        self.git("checkout", "-q", "pr")
        self.git("merge", "-q", "--no-ff", "-m", "Merge branch 'main' into pr", "main")   # a hand-made main merge
        self.merged = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.main2)
        self.git("push", "-q", str(bare), "refs/remotes/origin/main:refs/remotes/origin/main", "pr:refs/heads/pr")
        self.mod.PATCH_GIT, self.mod.PATCH_CACHE = bare, Path(tmp.name, "cache.json")
        self.mod._MAIN_FETCHED.append(1)
        self.mod.sh = lambda *a, **k: self.api.get(a[2].rsplit("/", 1)[-1], "")
        self.api = {}

    def git_init(self, bare):
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        os.makedirs(self.work)
        self.git("init", "-q", "-b", "main")

    def test_identical_patch_through_human_main_merge_carries(self):
        self.api = {self.approved: self.approved}
        self.assertTrue(self.mod.review_carries(self.approved, self.merged))
        self.assertTrue(self.mod.PATCH_CACHE.exists())   # diff ids are cached

    def test_changed_content_does_not_carry(self):
        self.git("checkout", "-q", "-b", "pr2", self.approved)
        changed = self.commit("pr.txt", "different change\n")
        self.git("push", "-q", str(self.mod.PATCH_GIT), "pr2:refs/heads/pr2")
        self.api = {self.approved: self.approved}
        self.assertFalse(self.mod.review_carries(self.approved, changed))

    def _variant(self, branch, name, data):
        """A sibling of the approved head, from the same base, writing `data` (bytes) to `name`."""
        self.git("checkout", "-q", "-b", branch, self.base)
        Path(self.work, name).write_bytes(data)
        self.git("add", name)
        self.git("commit", "-q", "-m", branch)
        sha = self.git("rev-parse", "HEAD")
        self.git("push", "-q", str(self.mod.PATCH_GIT), f"{branch}:refs/heads/{branch}")
        return sha

    def test_indentation_only_change_does_not_carry(self):
        a = self._variant("ws1", "m.py", b"def f():\n    return 1\n")
        b = self._variant("ws2", "m.py", b"def f():\n  return 1\n")
        c = self._variant("ws3", "m.py", b"def f():\n\treturn 1\n")
        self.api = {a: a}
        self.assertFalse(self.mod.review_carries(a, b))
        self.assertFalse(self.mod.review_carries(a, c))

    def test_different_binary_content_does_not_carry(self):
        a = self._variant("bin1", "x.bin", b"\x00\x01\x02\xff")
        b = self._variant("bin2", "x.bin", b"\x00\x01\x03\xff")
        self.api = {a: a}
        self.assertFalse(self.mod.review_carries(a, b))

    def test_same_diff_different_commit_carries(self):
        a = self._variant("same1", "x.bin", b"\x00\x01\x02")
        self.git("commit", "-q", "--amend", "-m", "reworded", "--allow-empty")
        b = self.git("rev-parse", "HEAD")
        self.git("push", "-q", "-f", str(self.mod.PATCH_GIT), "same1:refs/heads/same2")
        self.api = {a: a}
        self.assertNotEqual(a, b)
        self.assertTrue(self.mod.review_carries(a, b))

    def test_cache_key_has_merge_base_and_corrupt_cache_is_empty(self):
        self.mod.PATCH_CACHE.write_text("{not json", encoding="utf-8")
        self.api = {self.approved: self.approved}
        self.assertTrue(self.mod.review_carries(self.approved, self.merged))
        keys = list(json.loads(self.mod.PATCH_CACHE.read_text(encoding="utf-8")))
        self.assertTrue(all(":" in k and len(k.split(":")) == 2 for k in keys), keys)
        self.assertFalse(list(self.mod.PATCH_CACHE.parent.glob("*.tmp")))

    def test_cache_prunes_old_and_excess_entries(self):
        old = {f"k{i}": {"id": "x", "t": time.time() - 15 * 86400} for i in range(3)}
        new = {f"n{i}": {"id": "x", "t": time.time() - i} for i in range(self.mod.PATCH_CACHE_MAX_ENTRIES + 5)}
        self.mod._cache_store({**old, **new})
        kept = json.loads(self.mod.PATCH_CACHE.read_text(encoding="utf-8"))
        self.assertEqual(len(kept), self.mod.PATCH_CACHE_MAX_ENTRIES)
        self.assertFalse(any(k.startswith("k") for k in kept))

    def _shift_pair(self, main_edit):
        """PR A on c1; main moves to c2 (main_edit applied to f.txt); PR B = the same line-15 edit on c2."""
        lines = [f"line{i}\n" for i in range(1, 31)]
        self.git("checkout", "-q", "main")
        c1 = self.commit("f.txt", "".join(lines))
        edit = list(lines)
        edit[14] = "PR CHANGE\n"
        self.git("checkout", "-q", "-b", "sa", c1)
        a = self.commit("f.txt", "".join(edit))
        self.git("checkout", "-q", "main")
        c2 = self.commit("f.txt", "".join(main_edit(lines)))
        self.git("checkout", "-q", "-b", "sb", c2)
        edit2 = main_edit(lines)
        edit2[14 + (len(edit2) - len(lines))] = "PR CHANGE\n"
        b = self.commit("f.txt", "".join(edit2))
        self.git("update-ref", "refs/remotes/origin/main", c2)
        self.git("push", "-q", "-f", str(self.mod.PATCH_GIT), "refs/remotes/origin/main:refs/remotes/origin/main",
                 "sa:refs/heads/sa", "sb:refs/heads/sb")
        self.api = {a: a}
        return a, b

    def test_main_shifting_lines_above_identical_hunk_carries(self):
        a, b = self._shift_pair(lambda ls: ["new top\n", "new top2\n"] + ls)
        self.assertTrue(self.mod.review_carries(a, b))

    def test_changed_context_line_in_hunk_does_not_carry(self):
        def edit(ls):
            out = list(ls)
            out[13] = "main changed the line above\n"
            return out
        a, b = self._shift_pair(edit)
        self.assertFalse(self.mod.review_carries(a, b))

    def test_busy_lock_fails_closed(self):
        import fcntl
        self.mod.PATCH_LOCK = self.mod.PATCH_CACHE.parent / "busy.lock"
        self.mod.PATCH_LOCK_WAIT = 0.3
        self.api = {self.approved: self.approved}
        with open(self.mod.PATCH_LOCK, "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertFalse(self.mod.review_carries(self.approved, self.merged))
        self.assertTrue(self.mod.review_carries(self.approved, self.merged))   # free again: carries

    def test_cache_entry_without_id_is_a_miss(self):
        self.mod.PATCH_LOCK = self.mod.PATCH_CACHE.parent / "p.lock"
        self.api = {self.approved: self.approved}
        base = self.git("merge-base", self.merged, self.main2)
        self.mod.PATCH_CACHE.write_text(json.dumps({f"{self.approved}:{base}": {"t": time.time()}}), encoding="utf-8")
        self.assertTrue(self.mod.review_carries(self.approved, self.merged))

    def test_stale_tmp_files_are_cleaned_on_write(self):
        old = self.mod.PATCH_CACHE.with_name(self.mod.PATCH_CACHE.name + ".999.tmp")
        fresh = self.mod.PATCH_CACHE.with_name(self.mod.PATCH_CACHE.name + ".998.tmp")
        for f in (old, fresh):
            f.write_text("x", encoding="utf-8")
        os.utime(old, (time.time() - 7200,) * 2)
        self.mod._cache_store({})
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_exception_in_carry_path_fails_closed(self):
        def boom(*a, **k):
            raise RuntimeError("boom")
        self.mod._diff_id = boom
        self.api = {self.approved: self.approved}
        self.assertFalse(self.mod.review_carries(self.approved, self.merged))

    def test_failed_main_fetch_fails_closed(self):
        self.mod._MAIN_FETCHED.clear()          # origin is not configured on the cache clone: the fetch fails
        self.api = {self.approved: self.approved}
        self.assertFalse(self.mod.review_carries(self.approved, self.merged))

    def test_missing_sha_does_not_carry(self):
        gone = "f" * 40
        self.api = {gone: gone}
        self.assertFalse(self.mod.review_carries(gone, self.merged))

    def test_unresolvable_review_sha_does_not_carry(self):
        self.assertFalse(self.mod.review_carries("abc1234", self.merged))


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
