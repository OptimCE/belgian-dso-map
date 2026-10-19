# Mini fixture

A small, realistic dataset in the format of `data/`, with real INS codes. It is what
the website and dso-lookup develop against before the real data exist:

```bash
.venv/Scripts/python.exe scripts/build.py --fixture --draft --out .build/mini
```

| INS | Commune | Postcodes | Why |
|---|---|---|---|
| 21004 | Bruxelles | 1000, 1040, 1050 | Sibelga; 1040 and 1050 are shared (choose_commune) |
| 21005 | Etterbeek | 1040 | |
| 21009 | Ixelles | 1050 | address fallback when the postcode is another commune's |
| 25112 | Wavre | 1300, 1301 | electricity REW, gas ORES |
| 92094 | Namur | 5000, 5003, 5020, 5024 | sections: AIEG operates Flawinne, Marche-les-Dames and Saint-Marc, ORES is designated (`transition\|operator_differs\|to_confirm`) |
| 13002 | Baarle-Hertog | 2387 | sections sharing one postcode: gas Enexis in the enclaves, Fluvius Kempen in Zondereigen |

- The attributions follow the spec's §5 but are **not curated data**: never copy rows
  from here into `data/`. The sha256 of some sources is computed from their id, and
  the URL of `agw-rew-wavre` is a placeholder.
- `operators.csv` is a byte copy of `data/operators.csv` (a test keeps them equal).
- `notes.csv` has all four languages and no acceptance: `namur-aieg-sections` is
  reported as PENDING, so the fixture only builds as a draft.
- `vectors.csv` exercises every status, the ignore rule of the filters, the commune
  name rule, TRIM (spaces, NBSP, BOM, em space, full-width digits) and the EAN check.
- `curation/` holds one worksheet and one spot check, to exercise those checks.
- `release.json` (`2026.10.0`, `2026-10-12`) is the fixture's own: `--fixture` reads it
  instead of the root one, so bumping the real version never moves `.build/mini`.
