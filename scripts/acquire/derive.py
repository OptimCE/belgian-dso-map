"""Derive the normalised extracts of the M sources, so that validation runs offline.

    python scripts/acquire/derive.py [--out curation/derived] [--data-dir data] [--refresh]

Reads the raw files of `.cache/<source_id>/` (fetch.py downloads the missing ones) and
writes, in the repository's CSV dialect, into `--out` (curation/README.md has the columns):

- `statbel_refnis_2025_communes.csv`  REFNIS 2025 (statbel.py)
- `statbel_postcodes_2025.csv`        the Statbel postcode table (statbel.py)
- `fluvius_1_23.csv`                  Fluvius 1_23 (fluvius.py)
- `ores_odwb_elec.csv`                ORES on ODWB, electricity (odwb.py)
- `ores_odwb_gas.csv`                 ORES on ODWB, gas (odwb.py)

With `--data-dir DIR`, it also writes `DIR/communes.csv` (REFNIS names, NIS6 German
names, region and province from the INS) and `DIR/postcodes.csv` (the Statbel pairs).
Those are editable data files: the weekly sources workflow re-derives the extracts only.

It refuses sources that break the national facts (565 communes 285/261/19, 1,152 pairs,
multi-INS postcodes {1040, 1050, 1804}, Bastogne and Pajottegem after the 2025
mergers) or that do not join on the INS. Exit codes: 0 = written, 1 = a source has an
unexpected shape or content, 2 = a download or file error.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import csvio  # noqa: E402
import fetch  # noqa: E402
import fluvius  # noqa: E402
import odwb  # noqa: E402
import schema  # noqa: E402
import statbel  # noqa: E402

ROOT = SCRIPTS.parent
DEFAULT_OUT = ROOT / "curation" / "derived"
OPERATORS_CSV = ROOT / "data" / "operators.csv"

Row = Mapping[str, str]


def render(name: str, header: Sequence[str], rows: Sequence[Row]) -> bytes:
    """Rows in the repository dialect, re-read once to prove they pass csvio."""
    data = csvio.render_csv(header, rows)
    csvio.parse_csv(data, name=name, header=header)
    return data


def derive(
    *, cache: Path, operators_csv: Path, refresh: bool
) -> tuple[dict[str, bytes], dict[str, bytes], list[str]]:
    """(extract files, data files, summary lines). Downloads what the cache lacks."""

    def source(source_id: str) -> Path:
        return fetch.fetch(fetch.SOURCES[source_id], cache=cache, refresh=refresh).path

    refnis = statbel.parse_refnis(source("geo-statbel-refnis-2025").read_bytes())
    nis6 = statbel.parse_nis6(source("geo-statbel-nis6-2025"))
    pairs = statbel.parse_postcodes(source("geo-statbel-postcodes-2025"))
    if set(nis6) != {row["ins"] for row in refnis}:
        raise statbel.AcquisitionError("the INS of NIS6 differ from REFNIS")
    communes = statbel.commune_rows(refnis, nis6)
    statbel.check_national(communes, pairs)
    by_ins = {row["ins"]: row for row in communes}
    owners = statbel.postcode_owners(pairs)
    pair_rows = [{"postcode": postcode, "ins": ins} for postcode, ins in pairs]

    operators = {row["id"] for row in csvio.read_csv(operators_csv, schema.OPERATORS_HEADER)}
    fluvius_rows = fluvius.derive(
        fluvius.parse(source("fluvius-1-23").read_bytes()),
        owners=owners,
        communes=by_ins,
        operators=operators,
    )
    elec_year, elec_rows, elec_dropped = odwb.derive(
        odwb.parse(source("odwb-ores-elec").read_bytes(), "elec"), owners=owners, communes=by_ins
    )
    gas_year, gas_rows, gas_dropped = odwb.derive(
        odwb.parse(source("odwb-ores-gas").read_bytes(), "gas"), owners=owners, communes=by_ins
    )

    extracts = {
        "statbel_refnis_2025_communes.csv": render(
            "statbel_refnis_2025_communes.csv", schema.DERIVED_COMMUNES_HEADER, refnis
        ),
        "statbel_postcodes_2025.csv": render(
            "statbel_postcodes_2025.csv", schema.DERIVED_POSTCODES_HEADER, pair_rows
        ),
        "fluvius_1_23.csv": render("fluvius_1_23.csv", schema.DERIVED_FLUVIUS_HEADER, fluvius_rows),
        "ores_odwb_elec.csv": render("ores_odwb_elec.csv", odwb.HEADER, elec_rows),
        "ores_odwb_gas.csv": render("ores_odwb_gas.csv", odwb.HEADER, gas_rows),
    }
    data_files = {
        "communes.csv": render("communes.csv", schema.COMMUNES_HEADER, communes),
        "postcodes.csv": render("postcodes.csv", schema.POSTCODES_HEADER, pair_rows),
    }

    flemish = {ins for ins, row in by_ins.items() if row["region"] == "VLA"}
    flemish_postcodes = {postcode for postcode, ins in pairs if ins in flemish}
    fluvius_postcodes = {row["postcode"] for row in fluvius_rows}
    summary = [
        f"communes: {len(communes)} "
        + " ".join(
            f"{region} {sum(row['region'] == region for row in communes)}"
            for region in schema.REGIONS
        ),
        f"postcode pairs: {len(pairs)}, postcodes: {len(owners)}",
        f"fluvius: {len(fluvius_rows)} rows, {len(fluvius_postcodes)} postcodes, "
        f"{len({row['ins'] for row in fluvius_rows})}/{len(flemish)} Flemish INS; "
        f"Flemish postcodes without a row: "
        f"{', '.join(sorted(flemish_postcodes - fluvius_postcodes)) or 'none'}",
        f"odwb elec: year {elec_year}, {len(elec_rows)} rows, "
        f"{len({row['ins'] for row in elec_rows})} INS, {elec_dropped} EXC rows left out",
        f"odwb gas: year {gas_year}, {len(gas_rows)} rows, "
        f"{len({row['ins'] for row in gas_rows})} INS, {gas_dropped} EXC rows left out",
    ]
    return extracts, data_files, summary


def write_all(directory: Path, files: Mapping[str, bytes]) -> list[str]:
    lines = []
    for name, data in files.items():
        csvio.write_bytes(directory / name, data)
        rows = data.count(b"\n") - 1
        lines.append(f"{name}\t{rows} rows\t{hashlib.sha256(data).hexdigest()}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(description="Derive the extracts of the M sources.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="extracts directory")
    parser.add_argument(
        "--data-dir", type=Path, help="also write communes.csv and postcodes.csv here"
    )
    parser.add_argument("--refresh", action="store_true", help="download every source again")
    parser.add_argument("--cache", type=Path, default=fetch.CACHE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    operators_csv = (args.data_dir or OPERATORS_CSV.parent) / "operators.csv"
    try:
        extracts, data_files, summary = derive(
            cache=args.cache, operators_csv=operators_csv, refresh=args.refresh
        )
        written = write_all(args.out, extracts)
        if args.data_dir is not None:
            written += write_all(args.data_dir, data_files)
    except (statbel.AcquisitionError, csvio.CsvError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in [*summary, *written]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
