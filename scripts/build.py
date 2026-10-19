"""Build a version: flatten data/ into dso_lookup.csv, stamp the content dates and write
the release files (README.md, "Release files").

    python scripts/build.py --draft [--out .build/draft]
    python scripts/build.py --release                 # writes dist/ and the root CHANGES.md
    python scripts/build.py --fixture --draft --out .build/mini

The version and date come from release.json (DATA_DIR/release.json with --fixture, so
the fixture build does not move when the real version is bumped), or --version/--date.
The previous version is the committed dist/ (or --previous DIR, --previous-ref GITREF).
When dist/ already holds the version being built, the build is a rebuild of that
version and its own previous version is read from the tag `dist/release.json`
names. The only date written anywhere is the version date (release.json or
--date): no clock, mtime or git date, so two builds are byte-identical.

Validation (validate.py) runs on every build; a build with errors writes nothing.
A draft gets `data_version=<version>-draft` and lists unaccepted notes as pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import changes
import csvio
import dates
import schema

Row = dict[str, str]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "mini"
PUBLISHED_FILES = (
    "dso_lookup.csv",
    "operators.csv",
    "notes.csv",
    "sources.csv",
    "vectors.csv",
    "CHANGES.md",
    "REPORT.md",
    "release.json",
    "ATTRIBUTION.md",
)
OUTPUT_FILES = (*PUBLISHED_FILES, "SHA256SUMS")
PREVIOUS_FILES = (
    "release.json",
    "dso_lookup.csv",
    "operators.csv",
    "notes.csv",
    "sources.csv",
    "CHANGES.md",
)
# Published tables with content dates: (data columns, key columns, CHANGES.md file label).
DATED_TABLES = {
    "dso_lookup.csv": (schema.DSO_LOOKUP_DATA_COLUMNS, schema.DSO_LOOKUP_KEY, "dso_lookup"),
    "operators.csv": (schema.OPERATORS_HEADER, ("id",), "operators"),
    "notes.csv": (schema.DIST_NOTES_DATA_COLUMNS, ("key",), "notes"),
    "sources.csv": (schema.SOURCES_HEADER, ("id",), "sources"),
}
DIST_HEADERS = {
    "dso_lookup.csv": schema.DSO_LOOKUP_HEADER,
    "operators.csv": schema.DIST_OPERATORS_HEADER,
    "notes.csv": schema.DIST_NOTES_HEADER,
    "sources.csv": schema.DIST_SOURCES_HEADER,
}


class BuildError(Exception):
    """The build cannot run: bad version, previous version or output directory."""


# --- release.json -------------------------------------------------------------------------


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    previous: str


def parse_release(data: bytes, name: str, *, published: bool) -> Release:
    """The committed release.json {version, date, previous}, or a published one (+ counts,
    and a version that may carry -draft)."""
    try:
        content = json.loads(csvio.check_text_bytes(data, name))
    except (csvio.CsvError, json.JSONDecodeError) as exc:
        raise BuildError(f"{name}: {exc}") from exc
    keys = {"version", "date", "previous", *(("counts",) if published else ())}
    if not isinstance(content, dict) or set(content) != keys:
        raise BuildError(f"{name}: expected exactly the keys {sorted(keys)}")
    version, version_date, previous = content["version"], content["date"], content["previous"]
    if not all(isinstance(value, str) for value in (version, version_date, previous)):
        raise BuildError(f"{name}: version, date and previous must be strings")
    try:
        schema.version_key(version)
        if previous:
            schema.version_key(previous)
    except ValueError as exc:
        raise BuildError(f"{name}: {exc}") from exc
    if schema.is_draft(version) and not published:
        raise BuildError(f"{name}: the committed version never carries {schema.DRAFT_SUFFIX}")
    if not schema.is_date(version_date):
        raise BuildError(f"{name}: date {version_date!r} is not YYYY-MM-DD")
    return Release(version, version_date, previous)


def release_json(
    data_version: str, version_date: str, previous: str, counts: Mapping[str, object]
) -> bytes:
    content = {
        "version": data_version,
        "date": version_date,
        "previous": previous,
        "counts": counts,
    }
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# --- Previous version ---------------------------------------------------------------------


@dataclass(frozen=True)
class Previous:
    label: str
    release: Release
    tables: dict[str, tuple[tuple[str, ...], list[Row]]]  # file -> (header, rows)
    changes: str


def previous_from_files(files: Mapping[str, bytes], label: str) -> Previous:
    release = parse_release(files["release.json"], f"{label}/release.json", published=True)
    tables = {}
    for name in DATED_TABLES:
        header, rows = csvio.parse_csv(files[name], name=f"{label}/{name}")
        if any(row.get("data_version") != release.version for row in rows):
            raise BuildError(f"{label}/{name}: data_version differs from release.json")
        tables[name] = (header, rows)
    changes_text = csvio.check_text_bytes(files["CHANGES.md"], f"{label}/CHANGES.md")
    return Previous(label=label, release=release, tables=tables, changes=changes_text)


def load_previous_dir(path: Path) -> Previous:
    missing = [name for name in PREVIOUS_FILES if not (path / name).is_file()]
    if missing:
        raise BuildError(f"previous version {path}: missing {', '.join(missing)}")
    return previous_from_files(
        {name: (path / name).read_bytes() for name in PREVIOUS_FILES}, str(path)
    )


def _git_show(root: Path, spec: str) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise BuildError("git is needed for --previous-ref and is not on PATH")
    result = subprocess.run(  # noqa: S603 -- fixed git binary, no shell
        [git, "show", spec], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise BuildError(f"git show {spec}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def load_previous_ref(ref: str, root: Path) -> Previous:
    """The dist/ committed at a git ref (blobs as stored: LF, no checkout filters)."""
    files = {name: _git_show(root, f"{ref}:dist/{name}") for name in PREVIOUS_FILES}
    return previous_from_files(files, f"{ref}:dist")


def resolve_previous(
    root: Path,
    *,
    previous_dir: Path | None,
    previous_ref: str | None,
    fixture: bool,
    version: str,
) -> Previous | None:
    if previous_dir is not None:
        return load_previous_dir(previous_dir)
    if previous_ref:
        return load_previous_ref(previous_ref, root)
    dist = root / "dist"
    if fixture or not (dist / "release.json").is_file():
        return None
    published = load_previous_dir(dist)
    if schema.version_key(published.release.version) < schema.version_key(version):
        return published
    if published.release.version == version:
        # Rebuilding the published version: compare with the version before it.
        if not published.release.previous:
            return None
        return load_previous_ref(f"refs/tags/{published.release.previous}", root)
    raise BuildError(f"dist/ holds {published.release.version}, newer than {version}")


def check_sequence(
    version: str,
    version_date: str,
    previous: Previous | None,
    *,
    release: bool,
    named_previous: str | None,
) -> None:
    """Versions and dates only move forward; a release never follows a draft."""
    if previous is None:
        if release and named_previous:
            raise BuildError(f"release.json names previous {named_previous}, which was not found")
        return
    before = previous.release
    if schema.version_key(before.version) >= schema.version_key(version):
        raise BuildError(f"version {version} is not newer than the previous {before.version}")
    if before.date > version_date:
        raise BuildError(f"date {version_date} is before the previous version's {before.date}")
    if release and schema.is_draft(before.version):
        raise BuildError(f"a release cannot follow a draft ({before.version})")
    if release and named_previous is not None and named_previous != before.version:
        raise BuildError(f"release.json names previous {named_previous!r}, found {before.version}")


# --- Flattening and the build -------------------------------------------------------------


def _unique(rows: Sequence[Row], key_columns: Sequence[str]) -> list[Row]:
    """First row of each key (validate.py reports the duplicates)."""
    seen: dict[tuple[str, ...], Row] = {}
    for row in rows:
        seen.setdefault(tuple(row[column] for column in key_columns), row)
    return list(seen.values())


def flatten(ds: schema.Dataset) -> list[Row]:
    """One row per (postcode, INS, section): every section of a sectioned INS that lists
    the postcode, otherwise the commune's assignment. Sorted by (postcode, ins, section_key).
    Pairs without a commune or an attribution are skipped (validate.py reports them)."""
    communes = {row["ins"]: row for row in ds.communes}
    assignments = {row["ins"]: row for row in ds.assignments}
    sections: dict[str, list[Row]] = {}
    for section in ds.sections:
        sections.setdefault(section["ins"], []).append(section)
    rows = []
    for pair in _unique(ds.postcodes, ("postcode", "ins")):
        commune = communes.get(pair["ins"])
        if commune is None:
            continue
        base = {
            "postcode": pair["postcode"],
            "ins": pair["ins"],
            "commune_fr": commune["nom_fr"],
            "commune_nl": commune["nom_nl"],
            "commune_de": commune["nom_de"],
            "region": commune["region"],
            "province": commune["province"],
        }
        if pair["ins"] in sections:
            for section in _unique(sections[pair["ins"]], ("section_key",)):
                if pair["postcode"] in schema.split_list(section["postcodes"]):
                    rows.append(
                        {
                            **base,
                            "section_key": section["section_key"],
                            "section_fr": section["nom_fr"],
                            "section_nl": section["nom_nl"],
                            "section_de": section["nom_de"],
                            **{column: section[column] for column in schema.ATTRIBUTION_COLUMNS},
                        }
                    )
        elif pair["ins"] in assignments:
            assignment = assignments[pair["ins"]]
            rows.append(
                {
                    **base,
                    "section_key": "",
                    "section_fr": "",
                    "section_nl": "",
                    "section_de": "",
                    **{column: assignment[column] for column in schema.ATTRIBUTION_COLUMNS},
                }
            )
    rows.sort(key=lambda row: (row["postcode"], row["ins"], row["section_key"]))
    return rows


def counts(tables: Mapping[str, Sequence[Row]]) -> dict[str, object]:
    lookup = tables["dso_lookup.csv"]
    regions = {row["ins"]: row["region"] for row in lookup}
    by_region = Counter(regions.values())
    return {
        "communes": len(regions),
        "communes_by_region": {region: by_region[region] for region in schema.REGIONS},
        "postcodes": len({row["postcode"] for row in lookup}),
        "rows": len(lookup),
        "sections": len({(row["ins"], row["section_key"]) for row in lookup if row["section_key"]}),
        "operators": len(tables["operators.csv"]),
        "notes": len(tables["notes.csv"]),
        "sources": len(tables["sources.csv"]),
    }


@dataclass(frozen=True)
class Build:
    data_version: str
    date: str
    previous_version: str
    tables: dict[str, list[Row]]  # published tables, with their date columns
    changes: dict[str, list[dates.Change]]  # CHANGES.md file label -> changes
    files: dict[str, bytes]  # every published file except REPORT.md


def make_build(
    ds: schema.Dataset,
    *,
    version: str,
    date: str,
    draft: bool,
    previous: Previous | None,
    vectors_bytes: bytes,
    attribution_bytes: bytes,
) -> Build:
    data_version = version + schema.DRAFT_SUFFIX if draft else version
    sources: list[Row] = sorted(_unique(ds.sources, ("id",)), key=lambda row: row["id"])
    notes: list[Row] = sorted(
        (
            {column: note[column] for column in schema.DIST_NOTES_DATA_COLUMNS}
            for note in _unique(ds.notes, ("key",))
        ),
        key=lambda row: row["key"],
    )
    current = {
        "dso_lookup.csv": flatten(ds),
        "operators.csv": _unique(ds.operators, ("id",)),  # file order is the display order
        "notes.csv": notes,
        "sources.csv": sources,
    }
    tables: dict[str, list[Row]] = {}
    all_changes: dict[str, list[dates.Change]] = {}
    for name, rows in current.items():
        data_columns, key_columns, label = DATED_TABLES[name]
        tables[name], all_changes[label] = dates.stamp(
            rows,
            data_columns=data_columns,
            key_columns=key_columns,
            version_date=date,
            data_version=data_version,
            previous=previous.tables[name] if previous else None,
            label=name,
        )
    section = changes.new_section(version, date, all_changes, initial=previous is None)
    changes_md = changes.prepend(previous.changes if previous else None, section)
    previous_version = previous.release.version if previous else ""
    files = {name: csvio.render_csv(DIST_HEADERS[name], tables[name]) for name in DIST_HEADERS}
    files["vectors.csv"] = vectors_bytes
    files["CHANGES.md"] = changes_md.encode("utf-8")
    files["release.json"] = release_json(data_version, date, previous_version, counts(tables))
    files["ATTRIBUTION.md"] = attribution_bytes
    return Build(data_version, date, previous_version, tables, all_changes, files)


def sha256sums(files: Mapping[str, bytes]) -> bytes:
    """`sha256sum` format (two spaces), sorted by file name."""
    lines = [f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)]
    return "".join(lines).encode("utf-8")


def finalize(build: Build, report_text: str) -> dict[str, bytes]:
    files = {**build.files, "REPORT.md": report_text.encode("utf-8")}
    files["SHA256SUMS"] = sha256sums(files)
    return files


def write_outputs(out: Path, files: Mapping[str, bytes]) -> None:
    """Write a version into `out`, which may only hold the files of an earlier build.
    SHA256SUMS is written last, so an interrupted write never leaves it matching."""
    if out.exists():
        unknown = sorted(
            path.name
            for path in out.iterdir()
            if path.name not in OUTPUT_FILES or not path.is_file()
        )
        if unknown:
            raise BuildError(f"{out} holds files a build does not write: {', '.join(unknown)}")
    for name in sorted(files, key=lambda name: (name == "SHA256SUMS", name)):
        csvio.write_bytes(out / name, files[name])


# --- Context shared with validate.py -------------------------------------------------------


@dataclass(frozen=True)
class Context:
    root: Path
    data_dir: Path
    curation_dir: Path | None
    fixture: bool
    version: str
    date: str
    named_previous: str | None  # "previous" of release.json, when the version came from it
    previous: Previous | None
    dataset: schema.Dataset
    vectors: list[Row]
    vectors_bytes: bytes
    attribution_bytes: bytes


def _version_argument(value: str) -> str:
    if not schema.VERSION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not YYYY.MM.N (a draft is built with --draft, not a suffix)"
        )
    return value


def _date_argument(value: str) -> str:
    if not schema.is_date(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a YYYY-MM-DD date")
    return value


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir", type=Path, help="default: data/ (tests/fixtures/mini with --fixture)"
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="a small test dataset with its own release.json, vectors.csv and curation/: "
        "skips the national checks of rules 1, 5 and 10",
    )
    parser.add_argument(
        "--vectors",
        type=Path,
        help="default: tests/vectors.csv (DATA_DIR/vectors.csv with --fixture)",
    )
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--previous", type=Path, metavar="DIR", help="previous version directory")
    previous.add_argument(
        "--previous-ref", metavar="GITREF", help="previous version = dist/ at a git ref"
    )
    parser.add_argument(
        "--version", type=_version_argument, help="override release.json (YYYY.MM.N)"
    )
    parser.add_argument("--date", type=_date_argument, help="override release.json (YYYY-MM-DD)")


def load_context(args: argparse.Namespace, *, release: bool, root: Path = ROOT) -> Context:
    data_dir: Path = args.data_dir or (DEFAULT_FIXTURE if args.fixture else root / "data")
    # A fixture carries its own release.json: bumping the real version moves no fixture build.
    release_path = (data_dir if args.fixture else root) / "release.json"
    committed = parse_release(release_path.read_bytes(), str(release_path), published=False)
    version = args.version or committed.version
    version_date = args.date or committed.date
    try:
        schema.version_key(version)
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    if schema.is_draft(version):
        raise BuildError(f"--version {version}: use --draft instead of the suffix")
    if not schema.is_date(version_date):
        raise BuildError(f"date {version_date!r} is not YYYY-MM-DD")
    if version[:7] != version_date[:7].replace("-", "."):
        raise BuildError(f"version {version} and date {version_date} are not in the same month")
    named_previous = committed.previous if args.version is None else None
    previous = resolve_previous(
        root,
        previous_dir=args.previous,
        previous_ref=args.previous_ref,
        fixture=args.fixture,
        version=version,
    )
    check_sequence(version, version_date, previous, release=release, named_previous=named_previous)

    vectors_path: Path = args.vectors or (
        data_dir / "vectors.csv" if args.fixture else root / "tests" / "vectors.csv"
    )
    vectors_bytes = vectors_path.read_bytes()
    _, vectors = csvio.parse_csv(
        vectors_bytes,
        name=vectors_path.name,
        header=schema.VECTORS_HEADER,
        raw_columns=schema.VECTOR_INPUT_COLUMNS,
    )
    attribution_bytes = (root / "ATTRIBUTION.md").read_bytes()
    csvio.check_text_bytes(attribution_bytes, "ATTRIBUTION.md")
    curation_dir = data_dir / "curation" if args.fixture else root / "curation"
    return Context(
        root=root,
        data_dir=data_dir,
        curation_dir=curation_dir if curation_dir.is_dir() else None,
        fixture=args.fixture,
        version=version,
        date=version_date,
        named_previous=named_previous,
        previous=previous,
        dataset=schema.load_dataset(data_dir),
        vectors=vectors,
        vectors_bytes=vectors_bytes,
        attribution_bytes=attribution_bytes,
    )


BUILD_ERRORS = (BuildError, csvio.CsvError, dates.DatesError, changes.ChangesError)


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(
        description="Build a version of the data (see the module docstring)."
    )
    add_common_arguments(parser)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--draft", action="store_true", help="data_version=<version>-draft; acceptance pending"
    )
    mode.add_argument(
        "--release", action="store_true", help="strict validation; default --out dist/"
    )
    parser.add_argument("--out", type=Path, help="default: .build/out (dist/ with --release)")
    args = parser.parse_args(argv)
    if args.fixture and args.release and args.out is None:
        parser.error("--fixture --release needs --out: a fixture never goes to dist/")

    import validate  # validate.py imports this module

    try:
        ctx = load_context(args, release=args.release)
        outcome = validate.build_and_check(
            ctx,
            draft=args.draft,
            release=args.release,
            ignore_acceptance=args.draft,
            as_of=ctx.date,
        )
    except BUILD_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = outcome.findings
    for finding in findings.errors:
        print(f"error {finding}", file=sys.stderr)
    if not findings.ok:
        print(f"build refused: {len(findings.errors)} validation errors", file=sys.stderr)
        return 1
    out: Path = args.out or (ctx.root / "dist" if args.release else ctx.root / ".build" / "out")
    try:
        write_outputs(out, outcome.files)
        if args.release and args.out is None:
            csvio.write_bytes(ctx.root / "CHANGES.md", outcome.files["CHANGES.md"])
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    build = outcome.build
    print(
        f"{build.data_version} ({build.date}): {len(build.tables['dso_lookup.csv'])} rows, "
        f"{len(findings.warnings)} warnings, {len(findings.pending)} pending acceptances -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
