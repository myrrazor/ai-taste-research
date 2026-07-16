# Sprint 1 Opus 4.8 Review Record

> Historical advisory transcript. This file records the invocation and reported output;
> it is not current RC0 proof and must not substitute for deterministic or hosted checks.

Sprint: Sprint 1 - Threat Model and Security Hardening
Branch: `fix/sprint-1-security-hardening`
Base: `a11e780`
Final HEAD: `0c7d20fba38f4af1a21a7f3f03b42ce935312318`
Claude Code version: `2.1.181`
Model: `claude-opus-4-8`
Dangerous permission bypass: not used
Automated remediation passes used: 1 of 2 allowed

## Pass 1

Commit reviewed: `fbd6c3446c5bff3f155a302722c62c317125cde6`
Worktree state: clean before review
Invocation note: the first CLI invocation failed before review because the prompt was not parsed as an argument. The successful run provided the prompt through stdin.
Permissions: `--safe-mode`, `--permission-mode dontAsk`, read/test tool allowlist supplied. Claude reported Bash was denied and performed a static read-only review.

### Prompt

```text
Review the NanoTaste Sprint 1 security-hardening diff from base commit a11e780 to HEAD fbd6c3446c5bff3f155a302722c62c317125cde6. Do not edit files. You may inspect files and run only the allowed read-only commands/tests. Rubric: BLOCKER, HIGH, MEDIUM, LOW. Require file/line evidence for every finding. For BLOCKER findings include a reproduction case. Treat findings as advisory evidence, not proof. Focus on threat-model/code mismatches, path and symlink handling, UTF-8 handling, size limits, byte-faithful storage versus terminal-only escaping, atomic writes, CLI error behavior, and test coverage. If no findings at a severity, say so. End with a concise recommendation: accept, accept with follow-up, or reject.
```

### Output

```text
I have Bash denied (don't-ask mode), so I could not execute the test suite or shell reproductions. The review below is static-analysis based on a full read of the diff and the surrounding call sites (all file IO in the package routes through `security.py`, which I confirmed by reading every module). Findings are advisory.

---

# NanoTaste Sprint 1 Security-Hardening Review
Range: `a11e780..fbd6c34` . scope: threat-model/code fidelity, path/symlink, UTF-8, size limits, byte-faithful storage vs terminal escaping, atomic writes, CLI error behavior, test coverage.

## Summary
The hardening is well-centralized: every read/write goes through `security.py`, symlink-escape and atomic-replace controls are implemented correctly for the *documented (non-racing)* threat, and the byte-faithful-storage vs terminal-escaping split is honored (JSON preserves raw bytes; human output escapes). No control is silently broken. The gaps are consistency and verification, not core soundness.

## BLOCKER
None. The symlink-rejection (`_reject_existing_bad_output`, `security.py:185`), root-containment (`_assert_under_root`, `security.py:174`), and atomic same-dir replace (`atomic_write_text`, `security.py:115`) controls are implemented as the threat model describes, and the acknowledged TOCTOU limits are explicitly out of scope (`THREAT_MODEL.md:92`).

## HIGH
None.

## MEDIUM

**M1 - Calibrate subcommands write diagnostics to stdout, corrupting the `--json` contract and diverging from sibling commands.**
`cli.py:158` and `cli.py:174` emit errors with bare `print(...)` (stdout):
```python
print(f"Calibration input error: {safe_for_terminal(str(err))}")
```
whereas `run`/`compare`/`propose-update` correctly use `file=sys.stderr` (`cli.py:101,117,132`). Both `calibrate prepare` and `calibrate evaluate` accept `--json`. On any input error the non-JSON error text lands on stdout, so a consumer parsing `nanotaste calibrate evaluate --json` stdout gets non-JSON garbage instead of a clean stream + stderr diagnostic. The threat model hedges ("Diagnostics go to stderr where the existing command shape already does so," `THREAT_MODEL.md:135`), but the two new calibrate paths are the exception and they support JSON, so this is a real CLI-error/JSON-contract mismatch. Evidence: compare line 158/174 (stdout) vs 101/117/132 (stderr).

**M2 - Test coverage misses several claimed controls.**
`tests/test_security.py` covers domain validation, one discovery symlink escape, one invalid-UTF-8 read, one oversized prompt-set candidate, symlink-target rejection (write + record), and terminal escaping (one ANSI + one BIDI char). Not covered, despite being named guarantees in the threat model:
- Size limits for taste file / prompt-set bytes / calibration-run bytes / human-picks bytes / candidate-file bytes / prompt bytes / **record line 1 MiB** (`THREAT_MODEL.md:100-114`) - only the in-text candidate limit is exercised.
- `--taste-dir` containment and explicit `--taste-file`-outside-project + companion-domain containment (`THREAT_MODEL.md:45-54`).
- Pick validation: winner-not-in-candidates, duplicate `item_id`, unknown `item_id` (`calibration.py:383-418`) - none tested.
- `safe_for_terminal` breadth: C1 controls `0x80-0x9F`, OSC, and the full BIDI set (`security.py:167`) - only `\x1b` and `\u202e` are asserted.
- Byte-faithful round-trip to *disk* (only in-memory JSON output is checked) and atomic-write leaving no `.tmp` on failure.

Given these are the sprint's headline security properties, the unverified surface is large enough to flag.

## LOW

**L1 - Aggregate `MAX_TASTE_RULES` (2,000) is not enforced across merged taste files.**
`_validate_rule_count` runs per file inside `TasteProfile.from_text` (`schema.py:86,206-209`), but `from_paths` (`schema.py:62-78`) merges the global `TASTE.md` and the domain file via `_merge` without re-checking the total. Two files of 2,000 rules each yield 4,000 merged rules, contradicting "Total parsed taste rules | 2,000" (`THREAT_MODEL.md:103`). Bounded by the two 256 KiB file caps, so impact is mild (extra memory/scoring work), no escape.

**L2 - A within-limits run can be silently un-recordable due to the 1 MiB record-line cap.**
Each candidate may be 100 KiB and up to 26 candidates are allowed (`THREAT_MODEL.md:109-111`), but `to_record` embeds the full selected + all rejected candidate texts (`scoring.py:56-65,126-132`). A maximal `nanotaste run --candidate ... (x26)` produces a record well over `MAX_RECORD_LINE_BYTES` (1 MiB, `security.py:148-149`), so `append_record` raises *after* selection succeeds; `_run` then catches it and exits 1 with no record (`cli.py:96-102`). Fails closed and is operator-input only, but it's an internal limit inconsistency between the candidate/count limits and the record-line limit.

**L3 - `safe_for_terminal` omits line/paragraph separators (U+2028/U+2029) and NEL is covered only as C1.**
The escape set (`security.py:29-42,167`) matches the threat model's enumerated list exactly, so this is not a TM mismatch - but U+2028/U+2029 can still affect some terminals/log viewers and are not neutralized. Minor; noting for the Sprint 4 stdout-contract work.

**L4 - `safe_read_text` reads the whole file before the post-read size check.**
`safe_resolve_file` pre-checks `st_size` (`security.py:83-85`), but `safe_read_text` then does `resolved.read_bytes()` and only afterward re-checks `len(data)` (`security.py:98-100`). For normal local files the `st_size` gate bounds this; under the explicitly out-of-scope "lying/racing filesystem" it would read unbounded bytes into memory first. Defensible given scope; flagging as a hardening note.

## Positives worth recording
- All package file IO is funneled through `security.py`; no module performs raw `open`/`read_text`/`write_text` (verified across `cli/records/update/schema/calibration/discovery`).
- Strict UTF-8 decode with faithful re-encode preserves bytes; control chars are stored, not mutated, and JSON output stays machine-readable (`security.py:89-104`, `cli.py:203-212`, tests `test_cli_json_output_preserves_decoded_candidate_text`).
- Symlink-escape rejection on resolved targets and on output/record targets is correctly fail-closed and aborts discovery rather than skipping.
- Pick validation rejects unknown/duplicate item IDs and winners outside the candidate set (`calibration.py:383-418`) - good defense even though untested.

## Recommendation
**Accept with follow-up.** No BLOCKER or HIGH; the core path/symlink/atomic/UTF-8 controls match the threat model. Before merge or as immediate follow-up: fix M1 (route calibrate errors to stderr so `--json` stdout stays clean) and close the M2 coverage gaps for size limits, taste-dir containment, and pick validation. L1-L4 can be scheduled into the Sprint 4 stdout-contract/limits work. Note: I was unable to run the test suite in this environment (Bash disabled), so I did not independently confirm the existing tests pass - that should be verified in CI.
```

### Remediation

Committed as `0c7d20f`:

- M1: moved `calibrate prepare` and `calibrate evaluate` input diagnostics to stderr.
- M2: added tests for size limits, explicit taste companion containment, `--taste-dir` containment, record-line rejection, JSONL byte-faithful storage, and broader terminal controls. Existing pick-validation tests were already present in `tests/test_calibration.py`.
- L1: enforced merged `MAX_TASTE_RULES` after `TasteProfile.from_paths`.
- L2: raised record-line limit to 4 MiB and updated the threat model.
- L3: escaped U+2028 and U+2029 in terminal rendering and updated the threat model.
- L4: bounded `safe_read_text` to `limit_bytes + 1` after the stat check.

## Pass 2

Commit reviewed: `0c7d20fba38f4af1a21a7f3f03b42ce935312318`
Worktree state: clean before review
Permissions: `--safe-mode`, `--permission-mode auto`, read/test tool allowlist supplied. Claude reported it reproduced the unit suite and diff check.

### Prompt

```text
Second-pass review for NanoTaste Sprint 1 after remediation. Base commit a11e780, current HEAD 0c7d20fba38f4af1a21a7f3f03b42ce935312318. Do not edit files. Review the integrated diff and especially verify remediation of: calibrate errors to stderr for --json, expanded security tests, merged taste-rule limit, record-line limit consistency, bounded reads, and terminal escaping for C1/BIDI/separators. Rubric: BLOCKER, HIGH, MEDIUM, LOW. Require file/line evidence for each finding; BLOCKER needs reproduction. Treat findings as advisory evidence, not proof. If no blockers/highs remain, say so clearly. End with accept, accept with follow-up, or reject. Local verification already run by Codex: PYTHONPATH=src python3 -m unittest discover -s tests passed 58 tests; git diff --check HEAD passed; wheel build/install/smoke passed from a repo-local venv.
```

### Output

```text
I have completed a thorough second-pass review. All six remediation items verified against the diff, reproduced behavior, and confirmed the 58-test suite passes with a clean `git diff --check`.

---

# NanoTaste Sprint 1 - Second-Pass Review (post-remediation)

**Base** `a11e780` -> **HEAD** `0c7d20f` . diff: 12 files, +920/-69 . read-only review, no files edited.
Local checks reproduced: `unittest discover` -> **58 passed**; `git diff --check HEAD` -> clean.

## Remediation verification

| Item | Status | Evidence |
|---|---|---|
| Calibrate errors -> stderr under `--json` | PASS | `cli.py:158,174` both `file=sys.stderr`; new `test_calibrate_prepare_json_error_keeps_stdout_clean` asserts `stdout == ""` and message on stderr (`tests/test_cli_and_updates.py:222-241`). Six existing calibrate tests switched to `redirect_stderr`. |
| Expanded security tests | PASS | New `tests/test_security.py` (+352): domain validation/rejection, symlink-escape on three discovery paths, invalid UTF-8, all size limits, merged rule cap, record-line cap, terminal escaping, and JSON/JSONL round-trip fidelity. |
| Merged taste-rule limit | PASS | `schema.py:_validate_rule_count` now sums across **all** merged sections and is called in both `from_paths` (post-merge) and `from_text` (`schema.py:74,87,206-210`). `test_merged_taste_profile_enforces_total_rule_limit` proves 1001+1000 > 2000 raises (single files of 1000 would each pass). |
| Record-line limit consistency | PASS | `MAX_RECORD_LINE_BYTES = 4*MiB` enforced in `append_jsonl_record` (`security.py:148-152`). Headroom is correct: worst-case legitimate record (`selected` + up to 25 rejected candidate texts at `MAX_CANDIDATE_BYTES`=100 KiB ~= 2.7 MiB) stays under 4 MiB, so no valid run is rejected. `test_record_line_limit_rejects_oversized_jsonl_record` covers the reject path. |
| Bounded reads | PASS | `safe_resolve_file` stat-checks `st_size` first, then `safe_read_text` opens **binary** and reads `limit_bytes+1`, re-checking length before decode - bounds memory even if `stat` lies (`security.py:88-104`). Decode is explicit UTF-8 with labeled error. |
| Terminal escaping C1/BIDI/separators | PASS | `safe_for_terminal` escapes C0 (`<32`), DEL (`127`), C1 (`0x80-0x9F`, incl. NEL/OSC-string-terminator), the 12 BIDI controls, and U+2028/U+2029; preserves `\n`/`\t` (`security.py:155-172`). Applied to all human-readable sinks (`cli.py:144,210,212`). JSON sink deliberately left raw - `json.dumps` (ensure_ascii) neutralizes control chars and `test_cli_json_output_preserves_decoded_candidate_text` / `..._on_disk` confirm lossless round-trip. |

## Findings

**BLOCKER:** none.
**HIGH:** none.
**MEDIUM:** none.

I specifically probed the highest-risk regression candidate - that the new security validators in `_load_agent` could raise *outside* the `try` blocks in `_compare`/`_propose_update`/`_calibrate_prepare`, bypassing `safe_for_terminal` and dumping a traceback. **Not exploitable:** `TasteAgent.from_paths` is lazy; `discover_taste_paths` + `TasteProfile.from_paths` only execute inside `TasteRouter.resolve`, which is called within the try blocks. Reproduced with an oversized `--taste-file` on both `run` and `compare` -> both return `1` with a clean `Input error:` on stderr (no traceback).

**LOW**
- `records.py:14-17` - payload is `json.dumps`-serialized twice (the "cheap serializability check" plus the encode inside `append_jsonl_record`). Harmless but wasteful on multi-MB records; the check could pass the encoded line through instead.
- `cli.py:97,118,157,173` - handlers now catch the broad `except (OSError, ValueError)`. Since `SecurityInputError`/`CalibrationInputError` both subclass `ValueError` this is correct for input errors, but it will also mask any genuine internal `ValueError` bug as "Input error". Acceptable, worth noting.
- `security.py:142-152` (`append_jsonl_record`) - `_reject_existing_bad_output` rejects a *pre-existing* symlink (proven by `test_run_record_refuses_symlink_target`), but the subsequent `open("a")` follows symlinks, leaving a TOCTOU window. `atomic_write_text` is not affected (its `os.replace` replaces the link itself). Within the documented local single-user threat boundary this is not an escalation, but it's the one spot where the symlink guard isn't atomic.
- `security.py:_escape_codepoint` - a literal backslash in input is not itself escaped, so rendered output is not unambiguously reversible. Cosmetic only.

## Verdict

**Accept with follow-up.**

All six targeted remediations are present, correctly scoped, and backed by tests; no blockers, highs, or mediums remain. The LOW items (double-serialization, broad catch, append TOCTOU, backslash ambiguity) are advisory polish for a future sprint and do not block merge. Findings are evidence-based, not proof - the TOCTOU and broad-catch notes in particular warrant a maintainer glance before closing them out.
```
