# belgian-dso-map

Which distribution system operator (DSO, *gestionnaire de réseau de distribution*,
*netbeheerder*) serves each Belgian municipality, for electricity and for gas, with
its sources.

This repository is the **single source of truth**. It holds the editable CSV files,
the scripts that validate and build them, and the test vectors shared with its two
consumers:

- the OptimCE website (`../website`), whose "Quel est mon GRD ?" tool and
  municipality table are generated from a pinned version;
- the `dso-lookup` service (`monorepo/dso-lookup`), which pre-fills the DSO of a meter
  in the app.

An attribution is corrected here, by a pull request, and nowhere else. The consumers
only move to a newer version, also by a pull request.

> **Principle: "to confirm" beats a wrong answer.** Every commune → DSO attribution
> cites its sources. What is not cross-checked is flagged as such, in the data and on
> screen.

**State (2026-10-12):** contract, scripts, tests and the mini fixture are in place
(lot A, step 1). The machine-readable sources are acquired (step 2). The attributions
are curated (step 3): the designation lists are transcribed in `curation/`, and
`scripts/curate/assemble.py` builds `data/assignments.csv` and `data/sections.csv` for
the 565 municipalities, with 91 sources and the FR text of 14 notes; the CWaPE Power
BI report, read by hand, cross-checks the Walloon rows (its full reading stays local,
`curation/powerbi_checks.csv` keeps the comparison). The draft validates; the notes
of the 5 `to_confirm` rows wait for Eric's acceptance before the first release.

**The repository is public** (decided on 2026-10-19): the data are licensed under
CC BY 4.0 by OptimCE, the scripts under Apache-2.0 ([Licences](#licences)). The
consumers download the release assets anonymously.

## Contents

- [Layout](#layout)
- [Quick start](#quick-start)
- [Data contract](#data-contract)
- [Lookup algorithm](#lookup-algorithm)
- [Test vectors](#test-vectors-vectorscsv)
- [Validation](#validation)
- [Build and versions](#build-and-versions)
- [Release procedure](#release-procedure)
- [Maintenance calendar](#maintenance-calendar)
- [Licences](#licences)

## Layout

```text
data/                 the 7 editable CSV files (reviewed in pull requests)
curation/             transcription worksheets, spot checks, the CWaPE Power BI summary
                      powerbi_checks.csv (see curation/README.md)
curation/derived/     normalised extracts of the machine-readable sources (committed)
curation/private/     the full CWaPE Power BI readings: git-ignored, never published
scripts/              csvio, schema, dates, changes, report, lookup, build, validate, powerbi
scripts/acquire/      fetch, statbel, fluvius, odwb, derive (curation/README.md)
scripts/curate/       assemble: worksheets + overrides -> assignments, sections
tests/                pytest suite, vectors.csv (real data), fixtures/mini/ (small dataset)
dist/                 the last published version, committed (it is the "previous version")
release.json          the version being prepared: {"version", "date", "previous"}
CHANGES.md            copy of dist/CHANGES.md, written by build.py --release
ATTRIBUTION.md        credits of the sources, shipped in every version
LICENSE               data licence: CC BY 4.0, the legal code only (scope and credit: Licences)
LICENSE-CODE          Apache-2.0, for the scripts
```

`dist/`, `CHANGES.md` and `SOURCES.md` appear with the first release.

## Quick start

Python 3.12 (`py -3.12` on Windows: the `python` on PATH is 3.13).

```bash
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt

.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy scripts

# The mini fixture, as a draft (what the website and dso-lookup develop against)
.venv/Scripts/python.exe scripts/build.py --fixture --draft --out .build/mini
.venv/Scripts/python.exe scripts/lookup.py --dist .build/mini postcode 5020
.venv/Scripts/python.exe scripts/lookup.py --dist .build/mini address 13002 --postcode 2387 --post-name Zondereigen
.venv/Scripts/python.exe scripts/lookup.py ean 541448200000000001
.venv/Scripts/python.exe scripts/lookup.py --dist .build/mini vectors

# The real data
.venv/Scripts/python.exe scripts/curate/assemble.py --check     # data/ follows curation/
.venv/Scripts/python.exe scripts/validate.py --ignore-acceptance --report .build/REPORT.md
.venv/Scripts/python.exe scripts/build.py --draft --out .build/draft

# After a change of a Walloon row or of the Power BI readings (needs curation/private/)
.venv/Scripts/python.exe scripts/validate.py --ignore-acceptance --refresh-powerbi-summary
```

On Linux and macOS, use `.venv/bin/python`.

## Data contract

The website and dso-lookup implement this contract as is. A change here is a change
in three repositories, made in the same series of pull requests.

### Files of a version

A version is a GitHub Release with exactly these assets:

| File | Content |
|---|---|
| `dso_lookup.csv` | The flat file both consumers read: one row per (postcode, INS, section) |
| `operators.csv` | The operator catalogue |
| `notes.csv` | The warnings shown with a result, in FR, NL, DE and EN |
| `sources.csv` | Every source with its role, publisher, URL, retrieval date and sha256 |
| `vectors.csv` | The shared test cases |
| `CHANGES.md` | Cumulative change log |
| `REPORT.md` | Validation report of the version |
| `release.json` | `{version, date, previous, counts}` |
| `ATTRIBUTION.md` | Credits of the sources |
| `SHA256SUMS` | `sha256sum` format, every other file, sorted by name |

`release.json` (here the mini fixture's draft, `.build/mini`; a test keeps them equal):

```json
{
  "version": "2026.10.0-draft",
  "date": "2026-10-12",
  "previous": "",
  "counts": {
    "communes": 6,
    "communes_by_region": {"BRU": 3, "VLA": 1, "WAL": 2},
    "postcodes": 10,
    "rows": 15,
    "sections": 8,
    "operators": 16,
    "notes": 3,
    "sources": 12
  }
}
```

- `counts` are counted on the published files: `communes`, `postcodes` and `sections`
  are the distinct INS, postcodes and (INS, section) of `dso_lookup.csv`, `rows` its
  rows. The real data will have 565 communes and 1,149 postcodes.

- The version is CalVer `YYYY.MM.N`. It has no day, so `date` is the date of the
  version. `previous` is the version this one was compared with (empty for the first).
- `version` equals the `data_version` of every row of every CSV file.
- **Integrity check on the consumer side:** every file present (other than
  `SHA256SUMS`) is listed and matches, and the required set is present. `REPORT.md`
  is optional: a consumer may leave it out. Never run a plain `sha256sum -c` on a
  consumer's copy.

### CSV dialect

- UTF-8 without BOM, LF line endings, a final newline, comma separator, RFC 4180
  quoting (`csv.QUOTE_MINIMAL`), one header row, exact column order.
- Lists inside a cell (`flags`, `source_ids`, `postcodes`) are separated by `|`. An
  empty cell is an empty value.
- Text is NFC, with no leading or trailing whitespace and no control characters
  (nor U+2028/U+2029, which JavaScript's `.` does not match). The input columns of
  `vectors.csv` are the only exception for padding (they test TRIM).
- Dates are `YYYY-MM-DD`.

Jekyll does not strip a BOM and splits on commas; `csvio.py` enforces the dialect on
every read and write.

### Vocabularies

| Field | Values |
|---|---|
| `region` | `BRU`, `VLA`, `WAL` |
| `province` | ISO 3166-2: `BE-VAN`, `BE-VBR`, `BE-VLI`, `BE-VOV`, `BE-VWV`, `BE-WBR`, `BE-WHT`, `BE-WLG`, `BE-WLX`, `BE-WNA`; empty in Brussels |
| regulator | from the region: `BRU` → `BE-BRU-BRUGEL`, `VLA` → `BE-VLA-VREG`, `WAL` → `BE-WAL-CWAPE` |
| operator `kind` | `grd` (distribution), `gas_foreign` (Enexis), `grtl` (local transmission, Elia) |
| `gas_status` | `designated`, `none`, `foreign` |
| `flags` | `transition`, `operator_differs`, `to_confirm`, `propane_note`, written in this order |
| source `role` | `R` legal reference, `M` machine-readable data, `C` cross-check, `X` differentiation only |

- Region and province follow the INS prefix: 1 → VAN, 21 → Brussels, 23/24 → VBR,
  25 → WBR, 3 → VWV, 4 → VOV, 5 → WHT, 6 → WLG, 7 → VLI, 8 → WLX, 9 → WNA.
- The regulator codes are those of the monorepo's `reference/regulators.json`; they
  are hard-coded and its `active` flags change nothing.
- VREG has been called "Vlaamse Nutsregulator" since 2025-01-01. The code stays.

### Editable files (`data/`)

| File | Columns |
|---|---|
| `communes.csv` | `ins,nom_fr,nom_nl,nom_de,region,province` |
| `postcodes.csv` | `postcode,ins` |
| `assignments.csv` | `ins,elec_operator,elec_designated,gas_status,gas_operator,flags,note_key,source_ids,valid_from` |
| `sections.csv` | `ins,section_key,nom_fr,nom_nl,nom_de,postcodes,elec_operator,elec_designated,gas_status,gas_operator,flags,note_key,source_ids,valid_from` |
| `operators.csv` | `id,kind,name,legal_name,region,elec,gas,website,regulator,tariffs_url,lookup,replaced_by` |
| `sources.csv` | `id,role,publisher,title,url,retrieved_at,sha256,license,note` |
| `notes.csv` | `key,fr,nl,de,en,accepted_by,accepted_on` |

- **communes.csv**: the 565 municipalities of REFNIS 2025 (285 VLA, 261 WAL, 19 BRU).
  An empty `nom_de` means "use `nom_fr`".
- **postcodes.csv**: the 1,152 Statbel (postcode, INS) pairs. Only 1040, 1050 and
  1804 belong to several INS.
- **assignments.csv**: one row per commune without sections. `elec_operator` is the
  DSO that **operates** the network (the one on the bill and the meter); it is shown
  and pre-filled. `elec_designated` is the legally designated DSO, always filled.
  They differ only with the `operator_differs` flag.
- **sections.csv**: only where a commune needs sections (Baarle-Hertog; Bastogne,
  whose former commune of Bertogne has no gas DSO; Namur had sections until the AIEG ↔
  ORES exchange of 01/07/2026, Q2). `section_key` is a stored slug of `nom_fr` that
  never changes; `postcodes` lists the section's postcodes. An empty `nom_nl` or `nom_de` means "use
  `nom_fr`". **All or nothing:** a commune is in `assignments.csv` or in
  `sections.csv`, never both, and its sections cover every one of its postcodes.
- **operators.csv**: the 16 stable ids `aieg, aiesh, ores, resa, rew, sibelga,
  fluvius-antwerpen, fluvius-halle-vilvoorde, fluvius-imewo, fluvius-kempen,
  fluvius-limburg, fluvius-midden-vlaanderen, fluvius-west, fluvius-zenne-dijle,
  enexis, elia`, never renamed. A merged operator keeps its id and gets `replaced_by`.
  - `name` is the display name, byte-identical to the app's `GRD_OPTIONS` ("ORES",
    "Fluvius Imewo"); `legal_name` is the legal entity of the designated DSO.
  - `elec`, `gas` and `lookup` are `true` or `false`.
  - `elia` is `grtl`, region WAL, `lookup:false`: a lookup never returns it. It exists
    for the manual choice in the app (a 30–70 kV connection). It is not a DSO and is
    never labelled as one.
  - `enexis` is `gas_foreign` (gas in the Baarle-Hertog enclaves).
  - The file is in display order: `grd` first in the app's `GRD_OPTIONS` order (ORES
    first), then `gas_foreign`, then `grtl` (Elia last). Validation keeps it grouped
    by kind, then region (WAL, BRU, VLA).
- **sources.csv**: `publisher` decides independence (two sources are independent if
  their publishers differ). `sha256` is the hash of the bytes fetched (evidence only
  for dynamic HTML; empty for the Power BI report, whose readings are logged in
  `curation/spot_checks.csv`). Ids starting with `geo-` are the sources of the
  geography (communes, postcodes, section names): no row cites them.
- **notes.csv**: written in FR first. `accepted_by` and `accepted_on` are filled by
  Eric only (never by a script or by Claude). Notes about a whole region are keyed
  `dataset-<bru|vla|wal>-…` and need no row to cite them.

All files except `operators.csv` are sorted by their key.

### Published files

`dso_lookup.csv` has exactly these 22 columns, sorted by (`postcode`, `ins`, `section_key`):

```text
postcode,ins,commune_fr,commune_nl,commune_de,region,province,section_key,section_fr,section_nl,section_de,
elec_operator,elec_designated,gas_status,gas_operator,flags,note_key,source_ids,valid_from,
first_seen,changed_at,data_version
```

- A commune with sections has only section rows; there is never a "whole commune"
  row next to section rows for the same (postcode, INS). Without sections,
  `section_key` and the `section_*` names are empty.
- `operators.csv` and `sources.csv` are the data columns plus
  `first_seen,changed_at,data_version`. Operators keep the file order; sources are
  sorted by id.
- `notes.csv` is `key,fr,nl,de,en,first_seen,changed_at,data_version`, sorted by key:
  **never `accepted_by`/`accepted_on`** (a personal name is not published).
- `data_version` is the same on every row of every file.

### Content dates

`first_seen` and `changed_at` follow the content, never the build:

- A row's key is (`postcode`, `ins`, `section_key`) in `dso_lookup.csv`, `id` in
  operators and sources, `key` in notes. Its fingerprint is the sha256 of its data
  columns joined with U+001F, over the columns present in both the previous and the
  current header; `first_seen`, `changed_at` and `data_version` never count. Adding a
  column moves no date. A change of a note in any language counts.
- No previous version, or a new key: `first_seen` = `changed_at` = version date.
- Same fingerprint: both dates are kept. Different fingerprint: `first_seen` is kept
  and `changed_at` = version date.
- A key that disappears is listed as removed in `CHANGES.md`, dated by its version.
- No date ever comes from the clock, a file's mtime or git. Two builds of the same
  data are byte-identical.

### CHANGES.md grammar

```text
# Changes

## 2026.11.0 — 2026-11-02
- removed dso_lookup 1301|25112| — Wavre
- changed dso_lookup 5020|92094|flawinne — Flawinne (Namur); elec_operator: aieg→ores; flags: -operator_differs
- changed operators enexis — Enexis; website
- added notes gesves-exchange

## 2026.10.0 — 2026-10-12
- initial release
```

- The file is the title `# Changes`, blank lines, version headings newest first, and
  entries. Any other line is an error (`changes.parse_changes()` is the reference
  parser; the website ports its regexes).
- Heading: `^## ([0-9]{4}\.[0-9]{2}\.[0-9]+) — ([0-9]{4}-[0-9]{2}-[0-9]{2})$`. The
  separator is an em dash (U+2014) with one space on each side. The reference parser
  also refuses a heading whose version is not `YYYY.MM.N` (month 01-12, no leading
  zero in N) or whose date is not a calendar date; `build.py` never writes one.
- Entry: `^- (added|changed|removed) (dso_lookup|operators|notes|sources) (\S+)( — .*)?$`,
  or exactly `- initial release` (first version) or `- no changes`.
- The `dso_lookup` key is `postcode|ins|section_key`, with a trailing `|` when there
  is no section. The text after the em dash is the commune or section label ("Flawinne
  (Namur)"), then for a `changed` line the changed columns (`old→new`, `∅` for an
  empty value, `-x +y` for lists). For the other files: the operator's name or the
  source's publisher, then the changed column names.
- **A removal is dated by the heading of its version.** Entries are grouped by file
  (dso_lookup, operators, notes, sources), sorted by key.
- A draft's heading carries the version being prepared, without `-draft`
  (`release.json` and `data_version` say it is a draft).

### Normalisation (identical in the three repositories)

- **TRIM** removes, at both ends, exactly: space, tab, CR, LF, U+00A0 (no-break space)
  and U+FEFF (BOM). Python's `strip()` keeps U+FEFF and JavaScript's `trim()` removes
  U+2003, so neither is used as is. JavaScript:
  `s.replace(/^[ \t\r\n\u00a0\ufeff]+|[ \t\r\n\u00a0\ufeff]+$/g, "")`.
- **Postcode**: TRIM, then `^[0-9]{4}$`. Never `\d`, which accepts full-width digits
  in Python. Anything else is "not a postcode" (`not_found`, never an HTTP 422).
- **Name**: NFKD, drop the combining marks (`\p{M}`), `lower()` (not `casefold()`),
  then delete `[^a-z0-9]`. "Marche lès Dames" and "MARCHE-LES-DAMES" both give
  `marchelesdames`. JavaScript:
  `s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]/g, "")`.
- `ins` and `section` filters, and `nis_code`, are TRIMmed and compared exactly.

## Lookup algorithm

`scripts/lookup.py` is the reference implementation; the website
(`assets/js/dso-lookup-core.js`) and dso-lookup (`api/dso/lookup.py`) port it line for
line.

**By postcode** — `resolve(postcode, ins?, section?)`, website and app:

1. A postcode that is invalid, or has no row: `not_found`.
2. A filter that matches nothing is **ignored**. The `ins` filter applies only if it
   matches a row of the postcode; the `section` filter applies only once a single INS
   remains, and only if it matches.
3. Several INS: `choose_commune`, with the communes sorted by INS.
4. One INS with several sections: `choose_section`, with the sections sorted by key.
5. Otherwise: `ok`, with the row.

**By address** — `resolve_address(nis_code, postcode, post_name)`, app (BeST address):

1. Candidates: the rows of that INS with that postcode. If there are none (no
   postcode, an invalid one, or one of another commune), every section of the INS.
   An unknown INS: `not_found`.
2. A single candidate: `ok`, whatever `post_name` says.
3. Several candidates:
   - an empty `post_name`, or one equal to the commune's FR, NL or DE name:
     `choose_section` (BeST's postal name in Flanders is often the commune's name: an
     address in Zondereigen can come back as "Baarle-Hertog");
   - a `post_name` equal to the FR, NL or DE name of exactly one candidate: `ok`;
   - anything else: `choose_section`.

**Results** (Python reference shape; the consumers may wrap it):

```text
not_found       {status, data_version}
choose_commune  {status, communes: [{ins, name: {fr, nl, de}}], data_version}
choose_section  {status, ins, commune: {fr, nl, de},
                 sections: [{section_key, name: {fr, nl, de}, elec_operator}], data_version}
ok              {status, data_version, result: {postcode, ins, commune: {fr, nl, de},
                 section: {section_key, name} | null, region, province, regulator,
                 elec: {operator, designated}, gas: {status, operator},
                 flags: [], note_key, source_ids: [], valid_from, data_version}}
```

- In `choose_section`, every section carries its `elec_operator`. The app pre-fills
  the electricity DSO when every candidate agrees (Baarle-Hertog: Fluvius Kempen for
  both sections, only the gas differs).
- The app pre-fills `result.elec.operator` only: never `designated`, never gas.
- Empty `nl`/`de` names fall back to `fr`.

**EAN check** — `check_ean(ean)`, informative, never blocking:

- `ean` is the TRIMmed input; `format` is `^[0-9]{18}$`. Inner spaces are not removed.
- `belgian_prefix`: starts with `54`.
- `gs1_check`: the 18th digit equals the GS1 check digit of the first 17 (weights 3,
  1, 3, … from the left). The dev EAN `541448200000000001` has a valid format and a
  wrong check digit (it should end in 8).
- `known_operator`: `sibelga` when the EAN starts with `5414489`. The Liège demo EANs
  (RESA) start the same way (Q7), so this is never used to decide anything.
- With an invalid format, every check is false or null.

## Test vectors (`vectors.csv`)

```text
name,kind,postcode,ins,section_key,post_name,ean,expect_status,expect_key,expect_elec,expect_gas_status,expect_gas,expect_flags
```

- `kind` is `postcode` (website and service), `address` or `ean` (service). The
  `ins` column is the filter of a postcode row and the `nis_code` of an address row.
- An `expect_*` cell that is empty means "must be empty"; `*` means "not asserted";
  `expect_flags` is an exact set (empty = no flags).
- `expect_key` is `ins` or `ins/section_key` for `ok`, the `|`-separated set of INS
  for `choose_commune`, the set of section keys for `choose_section`, and empty for
  `not_found`.
- For a `choose_*` or `not_found` result, elec, gas and flags are empty.
- EAN rows: `expect_status` is `format_ok` or `format_invalid`, `expect_flags` ⊆
  `belgian_prefix|gs1_ok`, `expect_elec` is `known_operator`.
- Rows whose expected values depend on an open `to_confirm` question are named
  `tc-…`. They change in the same pull request as the answer.
- `tests/vectors.csv` holds the real-data cases (every "verified" case of the spec's
  §5, the to_confirm cases, the edge cases and the EAN cases).
  `tests/fixtures/mini/vectors.csv` exercises every status and rule on the mini
  fixture.
- If Q4 is answered "to_confirm on every Flemish row", the flags of the Flemish
  vectors (`zwijndrecht-2070`, `addr-burcht-2070`) change in that pull request.

## Validation

`scripts/validate.py [--ignore-acceptance] [--release] [--as-of D] [--report PATH] [--sources-md PATH] [--refresh-powerbi-summary]`
runs offline on `data/`, `curation/` and `tests/vectors.csv`, against an in-memory
build. Exit codes: 0 = pass (warnings allowed), 1 = errors, 2 = usage or I/O error.

| Rule | Check |
|---|---|
| 1 | Exactly 565 INS (285 VLA, 261 WAL, 19 BRU), equal to REFNIS 2025 (`curation/derived/`; a missing extract is an error); region and province agree with the INS prefix, region with the REFNIS `Langue`. |
| 2 | Each commune has an electricity operator and an explicit `gas_status`; `none` cites an R source; `designated`/`foreign` ⇔ `gas_operator` set. |
| 3 | Each attribution cites an R source. In VLA and WAL also an M or C source from another publisher, otherwise `to_confirm` is required. |
| 4 | Each `to_confirm` has a `note_key` whose note is accepted (`accepted_by` + `accepted_on`, filled by Eric). `--ignore-acceptance` and drafts report them as PENDING. |
| 5 | Every postcode maps to a known INS, every INS has a postcode; section postcodes are pairs of their INS and cover all of them; 1,152 pairs, equal to the Statbel 2025 pairs (`curation/derived/`; a missing extract is an error), multi-INS postcodes {1040, 1050, 1804}. |
| 6 | Operator ids exist; electricity ids are `grd` with `elec` and `lookup:true`; gas ids are `grd` (or `gas_foreign` for `foreign`) with `gas`; the region matches the commune's (except foreign). `lookup:false` and replaced operators are never assigned. |
| 7 | An INS is in `assignments.csv` XOR `sections.csv`; section keys are unique per INS. |
| 8 | Every vector passes against the built `dso_lookup.csv`. |
| 8bis | Two builds are byte-identical; unchanged rows keep their dates; `first_seen` ≤ `changed_at` ≤ version date. |
| 9 | A source retrieved more than 365 days before the as-of date (default: the version date): warning. After the version date: error. |
| 10 | Warnings: Flemish communes per DSO against the spec's list (28, 29, 38, 27, 39, 21, 59, 44; the spec gives no source for it), ORES against the 2022 opinion (190) and the known changes. |

Also checked: `operator_differs` ⇔ operator ≠ designated; `transition` needs a note
(warning after a year); `propane_note` only in Wallonia; `valid_from` not after the
version date; every cited source and note exists; unused sources (other than `geo-`)
and notes (other than `dataset-`) are warnings; the FR text of each note is required,
and all four languages for a release; sorted files without duplicate keys; the
curation worksheets and spot checks agree with the data (warnings); the Fluvius
extract agrees with the Flemish rows (warnings, "explained" when the row has a
`valid_from`); the CWaPE Power BI agrees with the Walloon rows, compared with
the designated DSO (warnings, "explained" when the row has a `valid_from` or
`to_confirm`, or a gas DSO that the map does not show: a designation does not guarantee
a network). Spot checks are explained the same way.

The Power BI warnings come from the committed summary `curation/powerbi_checks.csv`
only, so `REPORT.md` and every release file come out byte-identical in CI, which never
has the full readings: they stay local in `curation/private/` (git-ignored, never
published, see [Licences](#licences)). The summary is checked (errors): sorted rows, a
Walloon INS, a vector, the value compared (a DSO carrying the vector, or `none` for
gas), `agrees`, and `observed` only on a disagreement. A summary row that compared
another value than the data now hold, or that names no row any more, is a warning: the
summary must be refreshed. When the full readings are present, they are checked too
(errors): sorted rows, a Walloon INS, a commune label that names its INS (its FR, NL or
DE name under the name rule, or an alias of `curation/aliases.csv`: BERTOGNE → 82039),
the operator id of the GRD label (`powerbi.label_to_id`: every "ORES …" label is `ores`,
any other label is its lower case), a DSO carrying the vector and a positive count; and
the summary must follow from them (an error otherwise:
`validate.py --refresh-powerbi-summary` rewrites it). Neither is required: without the
full readings nothing is reported, without the summary a warning outside `--fixture`.

`--fixture` (a small test dataset with its own `release.json`, `vectors.csv` and
`curation/`) skips the national checks of rules 1, 5 and 10: the counts, the REFNIS and
Statbel extracts, and the REFNIS `Langue`. The internal coverage checks of rule 5 still
run. `--release` requires every note accepted, in four languages, and cannot be
combined with `--ignore-acceptance`. A malformed `--version`, `--date` or `--as-of` is
a usage error (exit 2).

## Build and versions

```text
build.py (--draft | --release) [--out DIR] [--data-dir DIR] [--fixture] [--vectors PATH]
         [--previous DIR | --previous-ref GITREF] [--version YYYY.MM.N --date YYYY-MM-DD]
```

- The version and date come from `release.json` (or `--version`/`--date`). The
  version and the date are in the same month; versions and dates only move forward.
- **Previous version:** `--previous DIR`, `--previous-ref GITREF` (its `dist/`), or by
  default the committed `dist/`. When `dist/` already holds the version being built,
  the build is a rebuild of that version, compared with the tag named by
  `dist/release.json`'s `previous`. A fixture build never reads `dist/` nor the root
  `release.json`: it reads `DATA_DIR/release.json`, so bumping the real version moves
  no fixture build. `--fixture --release` needs `--out`.
- Every build runs the validation first and writes nothing if it fails. It then
  writes the ten release files, `SHA256SUMS` last.
- `--draft`: `data_version=<version>-draft`; unaccepted notes are PENDING. Default
  output `.build/out`.
- `--release`: strict validation, never after a draft. Default output `dist/`, plus a
  copy of `CHANGES.md` at the root.
- **Drafts never reach production.** The website and dso-lookup sync scripts refuse a
  `-draft` version unless given `--from-dir … --allow-draft`, and their CI refuses
  draft data.

The website and dso-lookup develop against `.build/mini` (the mini fixture) first,
then `.build/draft`, and switch to `dist/` once the first release is merged.

## Release procedure

Claude never commits, tags or accepts a note. Eric does.

1. **Data pull request.** Edit `data/` (and the worksheets). Bump `release.json` to
   the next version (`{"version": "2026.11.0", "date": "2026-11-02", "previous":
   "2026.10.0"}`) if it still names the published one. Run `validate.py
   --ignore-acceptance --report REPORT.md` and `build.py --draft`; attach `REPORT.md`
   to the pull request. Eric reads it. When the sources were retrieved again, update
   the retrieval date in `ATTRIBUTION.md` (a test compares it with `sources.csv`).
2. **Notes.** Claude writes the FR text; Eric approves it; Claude writes NL, DE and
   EN; **Eric** fills `accepted_by` and `accepted_on`.
3. **Release pull request.** `build.py --release` writes `dist/` and `CHANGES.md`.
   Commit `release.json`, `dist/` and `CHANGES.md`.
4. **Tag.** After the merge: `git tag 2026.10.0 && git push origin 2026.10.0`.
   `release.yml` checks that the tag equals `release.json` and `dist/release.json`,
   re-validates, rebuilds `dist/` byte for byte, runs `sha256sum -c`, and publishes the
   GitHub Release with `dist/*` and the newest CHANGES section as its notes. Then, if
   the secret `DSO_CONSUMERS_TOKEN` is set, it sends the `repository_dispatch` event
   `dso-data-released` (`client_payload.version` = the tag) to `OptimCE/dso-lookup` and
   `OptimCE/website`.
5. **Consumers.** The "DSO data bump" workflows of dso-lookup and the website listen to
   `dso-data-released` (their weekly runs are the safety net) and open "dso data X → Y"
   pull requests. Merge them. If the release job says "Consumers not notified" (no
   secret) or "Consumer not notified" (a dispatch failed), run those workflows by hand:
   Actions → DSO data bump → Run workflow.

**Reading a release.** The repository is public: the consumers' sync scripts download
the release assets anonymously, through the GitHub REST API. Their `DSO_MAP_TOKEN` is no
longer required; set it (any read-only token) only to raise the API rate limit of an
anonymous client (60 requests an hour).

**Secret `DSO_CONSUMERS_TOKEN`** (optional, a repository secret of belgian-dso-map; still
needed for the notification although the repository is public): a
fine-grained personal access token, or a GitHub App token, limited to the repositories
`OptimCE/dso-lookup` and `OptimCE/website` with the single permission *Contents: Read and
write*, which the GitHub API requires to create a `repository_dispatch` event. The
"Notify the consumers" step of `release.yml` never fails the release: without the
secret it writes a notice, and a refused dispatch is a warning. A token expires: check
it before each release (about every six months).

CI (`.github/workflows/`):

- `validate.yml` (push, pull request, manual): ruff, mypy, pytest, two byte-identical
  builds of the mini fixture; once `data/` has rows: `validate.py` (red until Eric
  accepts the notes: that is the gate; the next steps run even while it is red), two
  identical builds (drafts while a version
  is in preparation; otherwise a rebuild that must equal `dist/`), `dist/` unchanged
  outside release pull requests, and an informative check of source ages against
  today in the job summary.
- `release.yml` (tags `YYYY.MM.N`): as in step 4, then the optional notification of
  the consumers.
- `sources.yml` (weekly, manual): downloads every `M` source that has a sha256 and
  compares; a difference means curation is needed, it never blocks a merge.

## Maintenance calendar

From the spec's §13:

| When | What |
|---|---|
| From lot A | Namur and Gesves (the AIEG ↔ ORES exchange, Q2), Saint-Vith gas (Q3), the VREG electricity redesignations after 05/09/2026 (Q4) |
| 14/10/2027 | End of the gas designations in Flanders |
| 31/12/2027 | End of RESA's propane networks (Esneux, Comblain-au-Pont, Visé) |
| Ongoing | The Walloon single-DSO project (Déclaration de politique régionale 2024): no decree as of 30/06/2026 |
| 01/01/2031 | Next municipal mergers |
| Every 6 months | Re-run the acquisition of the M sources and `build.py`, read `REPORT.md`, publish a version, then merge the bump pull requests in the website and dso-lookup |

## Licences

- Data: **CC BY 4.0** (Creative Commons Attribution 4.0 International), licensed by
  OptimCE; `LICENSE` holds the legal code only, so GitHub recognises it. It covers the
  data compiled in this repository (`data/`, `curation/` except `curation/derived/`,
  `tests/vectors.csv`, `dist/`) and every release built from them. `curation/derived/`
  holds reformatted extracts of the sources, which keep their own licences. Credit:
  "belgian-dso-map, OptimCE, version X (date)", with a link to
  <https://github.com/OptimCE/belgian-dso-map>, and say whether you changed it. This
  licence grants no right on the sources beyond what their own terms allow.
- The sources keep their own licences and attribution requirements: they are listed in
  `ATTRIBUTION.md`, shipped in every release (its credits must be kept).
- Scripts: Apache-2.0 (`LICENSE-CODE`).
- **Not published:** the full readings of the CWaPE Power BI report. Their licence is
  not stated (« non indiquée ») and a substantial extract of a database is reserved to
  its maker (EU sui generis database right), so they stay in `curation/private/`
  (git-ignored, local only). The repository keeps the two source rows
  (`data/sources.csv`: manual reading, URL, date), the spot checks and
  `curation/powerbi_checks.csv`: per Walloon row and vector, whether the report agrees,
  and what it showed only where it does not (curation/README.md, "CWaPE Power BI").
