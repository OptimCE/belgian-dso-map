# CLAUDE.md

Rules for Claude in this repository. README.md holds the data contract; read it first.

The repository is **public** (since 2026-10-19): the data are licensed under CC BY 4.0
by OptimCE (`LICENSE`), the scripts under Apache-2.0 (`LICENSE-CODE`). Everything
committed is published.

## Never

- **Never fill `accepted_by` or `accepted_on`** in `data/notes.csv`, not even with a
  placeholder. Acceptance is Eric's decision. Tests that need an accepted note build
  it in memory.
- **Never commit, push, tag, stash, reset or create a branch.** Hand over file groups
  with a commit message file per group for `git commit -F` (`.claude/commit-messages/`,
  git-ignored) and a pull request description (`.claude/pr/`). Eric commits, pushes,
  tags and creates the GitHub releases.
- **Never query automatically** the CWaPE Power BI report, CWaPE "mon GRD", Synergrid
  or bpost: no scraping, no scripted requests. Reading the Power BI report by hand is
  fine; log each reading in `curation/spot_checks.csv`. "mon GRD" is a POST form:
  every submission needs Eric's explicit OK in the conversation, or Eric does the check.
- **Never commit or publish the full Power BI readings** (licence not stated, EU sui
  generis database right): they stay in `curation/private/` (git-ignored, local only).
  Only the comparison is committed, `curation/powerbi_checks.csv`, written by
  `scripts/validate.py --refresh-powerbi-summary`; never copy the labels or counts of
  agreeing rows anywhere else (tests use made-up counts). The only real labels and
  counts quoted are the cited evidence of two `to_confirm` gas rows: Walcourt
  (« ORES Namur 2 ») and Marchin (« RESA 1 »). The code must work with and without `curation/private/`
  (CI never has it), and `dist/` must rebuild byte for byte without it.
- Never republish bpost data, never commit the raw downloads (`.cache/` is ignored),
  never edit `dist/` by hand (only `build.py --release` writes it).
- Never write a date from the clock, a file's mtime or git into a built file.

## Always

- Python 3.12: `py -3.12 -m venv .venv`, then `.venv/Scripts/python.exe …`. The
  `python` on PATH is 3.13 from the Windows Store.
- Write text files with LF endings: `open(path, "w", newline="")` or `write_bytes`,
  and `csv.writer(..., lineterminator="\n")`. On this Windows machine a plain text-mode
  write produces CRLF, which changes every hash.
- Edit the CSV files through `scripts/csvio.py` (or by hand, keeping the dialect):
  UTF-8 without BOM, LF, NFC, no padding, sorted by key.
- After a change: `pytest -q`, `ruff check .`, `ruff format --check .`, `mypy scripts`,
  `scripts/curate/assemble.py --check`, `scripts/validate.py --ignore-acceptance`, and two
  `build.py --draft` compared with `git diff --no-index --exit-code`. After a change of a
  Walloon row or of a Power BI reading, first `scripts/validate.py --ignore-acceptance
  --refresh-powerbi-summary` (validate refuses a summary the readings do not give).
- Prefer `to_confirm` with a note to a guess: a wrong DSO costs the tool its
  credibility. A Walloon row with a single R source gets `to_confirm` and the shared
  note `wal-single-source`.
- Transcribe every R list of communes twice, independently, into the worksheets of
  `curation/`, and arbitrate the differences.
- A change of `scripts/lookup.py` or of `vectors.csv` semantics is a contract change:
  the website (`assets/js/dso-lookup-core.js`) and dso-lookup (`api/dso/lookup.py`)
  must follow in the same series of pull requests.
