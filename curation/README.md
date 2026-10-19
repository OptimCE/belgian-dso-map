# Curation

Where the attributions of `data/` come from, before they become data. Everything here
is committed, published under CC BY 4.0 with the data (`LICENSE`) and checked by
`scripts/validate.py` (README.md, "Validation"), except `private/`: the full readings of
the CWaPE Power BI report, git-ignored and kept locally only ("CWaPE Power BI" below).

## Transcription worksheets: `*_designations.csv`

One file per region or vector (`wal_designations.csv`, `vla_designations.csv`,
`gas_designations.csv`, …). Each row transcribes one commune of a legal list (R) or
of a cross-check list (C), exactly as the source writes it.

```text
grd,vector,name_in_source,ins,source_id,locator
ores,elec,NAMUR,92094,cwape-avis-ores-2022,"annexe, p. 3"
```

| Column | Content |
|---|---|
| `grd` | Operator id of `data/operators.csv` designated by the source |
| `vector` | `elec` or `gas` |
| `name_in_source` | The commune's name as the source writes it (case and spelling kept) |
| `ins` | The INS code it maps to (REFNIS 2025) |
| `source_id` | Id of `data/sources.csv` |
| `locator` | Where in the source: page, annex, article, table row |

- Every R list is transcribed **twice, independently** (two worksheets, or two passes
  compared before the commit); the differences are arbitrated and the result is
  committed once.
- Validation: unknown operator, vector, INS or source = error. A worksheet row whose
  operator is not the designated DSO of that INS in `data/` (electricity) or its gas
  operator (gas) = warning, listed in REPORT.md under "Cross-check disagreements". A
  newer source can explain the disagreement (Couvin: AIESH since 2024).
- A condition written in the source (a partial territory, a term, a suspensive
  condition) follows the locator after " — ": `art. 2 — désignation temporaire …`.

The worksheets of lot A (2026-10-12), each from two independent transcriptions that
agreed:

| Worksheet | Rows | Content |
|---|---|---|
| `wal_designations.csv` | 351 | 15 Walloon electricity orders (R, 267 rows); C: the AIEG and AIESH pages, REW's history, CWaPE opinions 0892, 0905, 0913, 0948 (RESA), RESA's 2024 report (ORES in 17 eastern communes) |
| `gas_designations.csv` | 368 | 12 Walloon gas orders (R, 178 rows); C: CWaPE opinions 0900, 0893, 0904, 0906, 0914, 0943, 0949, 0976, RESA's 2024 report (17 communes) |
| `vla_designations.csv` | 571 | the 2026 tariff decisions BESL-2025-104 to 119 (285 communes, electricity and gas) and the Zondereigen restriction of BESL-2015-43 |

## Aliases: `aliases.csv`

```text
name_in_source,ins,reason
Fosse-la-ville,92048,"Coquille de l'art. 1er de l'AGW du 9 juin 2022 …"
```

A worksheet name must equal a name of its INS in `data/communes.csv` (FR, NL or DE)
under the name rule of README.md ("Blegny" is "Blégny", "Amel" is Amblève's NL name).
Any other name is listed here with its reason: a misprint, a merged commune (Bertogne,
merged into Bastogne on 02/12/2024 by the Walloon decree of 19/05/2023, now a section of
Bastogne), a section (Zondereigen). An unlisted name stops `assemble.py`. `validate.py`
reads the same file for the commune labels of the CWaPE Power BI readings (below).

## Decisions: `overrides.csv`

One row per decision that the lists alone do not make: a §5 case of the spec, a
research finding, a region-wide rule.

```text
ins,field,value,valid_from,flags,note_key,source_ids,reason
57093,elec,aieg,2026-01-01,transition,brunehaut-2026,aieg-ra-2025|ores-assets-ra-2025,"…"
```

| Column | Content |
|---|---|
| `ins` | An INS, `INS/section_key` (a section; the commune then lives in `sections.csv`), or a region (`BRU`, `VLA`, `WAL`: every commune of it) |
| `field` | `elec` (operator and designated), `elec_operator`, `elec_designated`, `gas` (`none`, `designated:<id>`, `foreign:<id>`), `nom_fr`/`nom_nl`/`nom_de`/`postcodes` (sections), `annotate` (no value), `gas_none_sources` (a region: the R sources that prove the absence of a gas DSO) |
| `valid_from`, `flags`, `note_key`, `source_ids` | Added to the row (`operator_differs` is derived, never written) |
| `reason` | Why, with the documents (required) |

## Assembly: `scripts/curate/assemble.py`

```bash
.venv/Scripts/python.exe scripts/curate/assemble.py            # writes data/assignments.csv, data/sections.csv
.venv/Scripts/python.exe scripts/curate/assemble.py --check    # exit 1 if data/ is not the assembly
```

- The R rows of the worksheets give each commune's designated operator per vector. Two
  different operators (Brunehaut, Couvin: a conditional order) need an override. No R
  gas row, in a region whose gas lists are transcribed, means `none`.
- A row cites the worksheet sources whose entry agrees with its final value, the
  ORES extracts that agree with it (an ORES commune listed by ODWB; for `none` in
  Wallonia, a commune without ORES gas access points; a section, through its own
  postcodes), the Fluvius extract when every row of the commune agrees (one row for a
  section), the CWaPE Power BI readings that show exactly its designated DSO (or no gas
  DSO for `none`: the full reading of the vector when `private/` holds it, otherwise
  `powerbi_checks.csv`, provided it compared the row's current value), and its
  overrides' sources.
- A Flemish or Walloon row without an M or C source of another publisher than its R
  sources gets `to_confirm` and the note `wal-single-source` / `vla-single-source`
  (none in lot A); a row that already has another note stops the assembly.
- The output is sorted and does not depend on the order of the inputs. Never edit
  `data/assignments.csv` or `data/sections.csv` by hand: change the curation and
  re-assemble (`tests/test_assemble.py` checks that `data/` is up to date).

## Spot checks: `spot_checks.csv`

Manual readings of tools that are never queried automatically (the CWaPE Power BI
report, read by hand; CWaPE "mon GRD", only with Eric's OK for each submission).

```text
date,tool,ins,vector,observed,matches
2026-10-12,cwape-powerbi-grd-elec-2026-10-12,25112,elec,rew,true
```

| Column | Content |
|---|---|
| `date` | Date of the reading, `YYYY-MM-DD` |
| `tool` | Id of the reading in `data/sources.csv` (`cwape-powerbi-grd-elec-2026-10-12`; a "mon GRD" reading needs its own source row first) |
| `ins` | INS of the commune checked |
| `vector` | `elec` or `gas` |
| `observed` | Operator id shown by the tool, or `none` (no gas DSO) |
| `matches` | `true` or `false`: does it match `data/`? |

The target is at least one commune per DSO, plus every commune of the spec's §5.
A reading that disagrees with `data/` (or says `matches=false`) is a warning listed in
REPORT.md, "explained" like the Power BI comparison (below).

`spot_checks.csv` (2026-10-12, 48 rows) logs the CWaPE Power BI readings of the 21
Walloon communes of the spec's §5 (G3-G12, G19), both vectors, plus Walcourt (G20) and
Marchin (G22); every DSO appears (AIEG, AIESH, ORES, RESA, REW; gas ORES and RESA). A
commune shown under two labels (Bastogne and Bertogne) gets one row per value observed.
Four rows say `matches=false`, all explained: Couvin (ORES Namur beside AIESH) and
Brunehaut (ORES Hainaut) in electricity, Saint-Vith and Comblain-au-Pont without gas on
the map.

## Derived extracts: `derived/`

Normalised, committed extracts of the machine-readable (M) sources, so validation runs
offline. The acquisition scripts (`scripts/acquire/`) write them from the raw files in
`.cache/<source_id>/` (never committed):

```bash
.venv/Scripts/python.exe scripts/acquire/fetch.py --record     # download, record in data/sources.csv
.venv/Scripts/python.exe scripts/acquire/derive.py --data-dir data
```

`derive.py` downloads what the cache lacks, refuses a source that breaks the national
facts (565 communes, 1,152 pairs, multi-INS postcodes {1040, 1050, 1804}, Bastogne and
Pajottegem after the 2025 mergers) or a row that does not join on an INS, and writes
the extracts below. With `--data-dir data` it also rewrites `data/communes.csv` and
`data/postcodes.csv`; without it (the weekly `sources.yml` run) it touches the extracts
only.

| File | Columns | Used by |
|---|---|---|
| `statbel_refnis_2025_communes.csv` | `ins,nom_fr,nom_nl,langue` | rule 1: the INS set equals REFNIS 2025, `langue` gives the region |
| `statbel_postcodes_2025.csv` | `postcode,ins` | rule 5: `data/postcodes.csv` equals the Statbel pairs |
| `fluvius_1_23.csv` | `postcode,community,ins,elec_id,gas_id,gastype` | cross-check of the Flemish rows (warnings) |
| `ores_odwb_elec.csv` | `year,postcode,localite,commune,secteur,ins` | curation: localities where ORES is the designated electricity DSO (latest year) |
| `ores_odwb_gas.csv` | `year,postcode,localite,commune,secteur,ins` | curation: localities where ORES is the gas DSO (latest year) |

The two readings of the CWaPE Power BI report, read by hand (C sources), are not in
`derived/`: see "CWaPE Power BI" below.

- `communes.csv`: `nom_fr` and `nom_nl` are REFNIS's; `nom_de` is the German name of
  Statbel's NIS6 file (`T_MUN_DE`), or REFNIS's French or Dutch name when NIS6 gives
  that one as the German name (so "Braine-l'Alleud" keeps one spelling).
- Fluvius: `community` is a sub-municipality ("Kallo (Kieldrecht)"), several per
  postcode; the INS comes from the postcode. `elec_id`/`gas_id` are operator ids
  (`Enexis Netbeheer` → `enexis`, no gas DSO → empty); `gastype` is the export's
  `gastype` column as written. Its snapshot (2025-04-01) predates 2070 Zwijndrecht's
  move to Fluvius Midden-Vlaanderen.
- ODWB: the distinct localities of the latest year; the counts, client types and
  voltages are dropped, and so are the `EXC` rows (no postcode). ODWB is keyed by the
  designated DSO: it never shows who operates a network for another DSO.

No ODWB check is in `validate.py`; `assemble.py` uses the ODWB extracts as M sources.
No BeST extract is needed: Baarle-Hertog's two sections share postcode 2387 and the app
tells them apart by name, and Bastogne's two sections follow its postcodes (6600;
6686-6688).

## CWaPE Power BI: `private/` (local) and `powerbi_checks.csv` (committed)

The CWaPE's Power BI report « GRD par commune » (https://www.cwape.be/node/6468) is
never queried automatically (CLAUDE.md). On 2026-10-12 it was read **by hand**, once per
vector, through the visual's accessible table view (no automation, no export, no form).
The report says "Dernière mise à jour : 04-10-2026"; its data periods are 2026-T1 for
electricity and 2026-T2 for gas. Each reading is a C source of `data/sources.csv`
(`cwape-powerbi-grd-elec-2026-10-12`, `cwape-powerbi-grd-gas-2026-10-12`, publisher
CWaPE, licence « non indiquée », no sha256).

**The full readings are not published.** Their licence is not stated, and a substantial
extract of a database is reserved to its maker (EU sui generis database right). They
stay in `private/` (`cwape_powerbi_elec.csv`, `cwape_powerbi_gas.csv`), which git
ignores; only Eric's checkout has them. The public repository keeps the two source rows,
the 48 spot checks (above) and the summary `powerbi_checks.csv`, which says per Walloon
row whether the report agrees, and what it showed only where it does not.

### The full readings: `private/cwape_powerbi_elec.csv`, `cwape_powerbi_gas.csv`

| Column | Content |
|---|---|
| `commune_label` | The commune as the report writes it (upper case, no accents: `BRAINE-L'ALLEUD`) |
| `ins` | Its 2025 INS: the label is one of its names under the name rule of README.md, or an alias of `aliases.csv` (`BERTOGNE` → 82039, merged into Bastogne) |
| `grd_label` | The GRD as the report writes it (`ORES Namur`, `AIESH`, `RESA`) |
| `grd_id` | Its operator id, `powerbi.label_to_id(grd_label)`: every `ORES …` sub-region is `ores`, any other label is its lower case (`AIESH` → `aiesh`) |
| `count` | The measure shown, « Nombre de GRD » (its meaning is not documented) |

- One row per (commune label, GRD label); sorted by `ins`, `commune_label`,
  `grd_label`. A commune shown under two GRD labels has two rows (Couvin: AIESH 30 and
  ORES Namur 10).
- The electricity table has 267 commune labels: 262 Walloon labels (261 INS: Bastogne
  and Bertogne are both 82039) and **5 Flemish border communes that are left out**:
  BIEVENE, ESPIERRES-HELCHIN, HAL, LANDEN and RHODE-SAINT-GENESE (one ORES row each,
  outside the report's region). The gas table has 172 Walloon labels; a commune absent
  from it has no gas GRD on the map.
- When they are present, `validate.py` checks them (errors, and then nothing is
  compared): rows not sorted, an INS outside Wallonia, a label that does not name its
  INS, a `grd_id` other than the id of its label, an operator that does not carry the
  vector, a count that is not positive.

### The summary: `powerbi_checks.csv`

```text
ins,section_key,vector,data,agrees,observed
57093,,elec,aieg,false,ORES Hainaut 19
82039,bertogne,gas,none,true,
```

| Column | Content |
|---|---|
| `ins`, `section_key` | The Walloon row of `data/`: an assignment (empty `section_key`) or a section (Bastogne, Bertogne) |
| `vector` | `elec` or `gas` |
| `data` | The value of the row that was compared: the designated electricity DSO, the gas DSO, or `none` |
| `agrees` | `true` when the report shows exactly that DSO (or no gas GRD for `none`), else `false` |
| `observed` | Empty when it agrees; otherwise what the report showed: its GRD labels with their counts (`AIESH 30 + ORES Namur 10`), or `none` (no GRD) |

- One row per Walloon row of `data/` and vector the report covers: 524 rows (261
  communes, Bastogne in two sections, × 2 vectors), sorted by `ins`, `section_key`,
  `vector`. A section is compared with the rows of its own label (Bertogne), else the
  commune's label.
- Written by `scripts/validate.py --ignore-acceptance --refresh-powerbi-summary`, which
  needs `private/` (it keeps the rows of a vector whose full reading is absent). Refresh
  it after a change of a Walloon row or of a reading: when `private/` is present, a
  summary that does not follow from it is a validation error.
- `validate.py` lists its disagreements as cross-check warnings, from the summary only,
  so REPORT.md is the same in CI (which has no `private/`) and locally. A summary row
  that compared another value than the row now holds, or that names no row any more,
  is a warning (refresh it); its format is checked (errors).
- `assemble.py` cites a reading on the rows it agrees with, which gives every agreeing
  Walloon row a C source from another publisher than the AGWs: from the full reading of
  the vector when present, otherwise from the summary, only if its `data` is the row's
  current value. The citations are the same with and without `private/` as long as the
  summary is up to date, so `assemble.py --check` passes in CI.
- `scripts/powerbi.py` says what a reading shows for a row: the commune's rows, or for
  a section the rows of its own label (Bertogne), else the commune's label. The report
  is compared with the designated DSO (like ODWB).
- The disagreements of 2026-10-12, all "explained": Couvin and Brunehaut (electricity,
  the report lags the transfers of 2024 and 2026), Saint-Vith (gas designated from
  01/06/2026), Habay, Ramillies, Villers-la-Ville and Comblain-au-Pont (a gas
  designation without a gas GRD on the map).
