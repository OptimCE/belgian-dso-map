"""Download the sources into .cache/<source_id>/ and record them.

    python scripts/acquire/fetch.py [SOURCE_ID ...] [--refresh] [--record]
    python scripts/acquire/fetch.py --list

The sources are the machine-readable (M) ones and the legal (R) documents whose bytes
are recorded through this script (the decree of the Bastogne-Bertogne merger). Each is
downloaded once into its own directory, `.cache/<source_id>/`, next to a `fetch.json`
that keeps the URL, the retrieval date and the sha256 of the bytes. The cache is
git-ignored: raw files are never committed, only the normalised extracts that
`derive.py` writes into `curation/derived/`.

`--record` writes the source's row into `data/sources.csv` (role, publisher, title,
URL, `retrieved_at`, `sha256`, licence, note), keeping the other rows. `retrieved_at` is
the day the bytes were downloaded (from `fetch.json`), never the day of the record.
`--refresh` downloads again even when the cache is complete.

Nothing is ever executed from the cache, and no tool listed in CLAUDE.md as manual-only
(CWaPE Power BI, CWaPE "mon GRD", Synergrid, bpost) is in this list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import csvio  # noqa: E402
import schema  # noqa: E402

ROOT = SCRIPTS.parent
CACHE = ROOT / ".cache"
SOURCES_CSV = ROOT / "data" / "sources.csv"
USER_AGENT = "belgian-dso-map acquisition (OptimCE)"
TIMEOUT_SECONDS = 300
METADATA_NAME = "fetch.json"

# Licences as the publishers state them (ATTRIBUTION.md gives the URLs and credits).
STATBEL_LICENSE = "CC BY 4.0"
FLUVIUS_LICENSE = "Open data license - FLUVIUS"
ODWB_LICENSE = "Creative Commons - CC0 (ODWB)"
ODWB_NOTE = (
    "Export ODWB de toutes les années ; derive.py garde la dernière. Les métadonnées ODWB "
    "disent CC0 mais pointent vers la définition CC BY ; couches NGI-IGN. ORES demande "
    "d'être informé des réutilisations (indicateurs@ores.be)"
)


@dataclass(frozen=True)
class Source:
    """A downloaded source: where it is, how it is cited in sources.csv."""

    id: str
    url: str
    filename: str
    publisher: str
    title: str
    license: str
    note: str = ""
    role: str = "M"


SOURCES: dict[str, Source] = {
    source.id: source
    for source in (
        Source(
            id="geo-statbel-refnis-2025",
            url="https://statbel.fgov.be/sites/default/files/Over_Statbel_FR/Nomenclaturen/REFNIS_2025.csv",
            filename="REFNIS_2025.csv",
            publisher="Statbel",
            title="Code REFNIS 2025 (nomenclature des unités administratives)",
            license=STATBEL_LICENSE,
            note="Communes = lignes avec une Langue ; N → VLA, F et D → WAL, FN → BRU",
        ),
        Source(
            id="geo-statbel-nis6-2025",
            url="https://statbel.fgov.be/sites/default/files/files/opendata/Statistische%20sectoren/NIS6withnamefrom01012025.xlsx",
            filename="NIS6withnamefrom01012025.xlsx",
            publisher="Statbel",
            title="NIS6 avec noms à partir du 01/01/2025 (secteurs statistiques)",
            license=STATBEL_LICENSE,
            note="Noms allemands des communes (T_MUN_DE)",
        ),
        Source(
            id="geo-statbel-postcodes-2025",
            url="https://statbel.fgov.be/sites/default/files/Over_Statbel_FR/Nomenclaturen/Conversion%20Postal%20code_Refnis%20code_va01012025.xlsx",
            filename="Conversion Postal code_Refnis code_va01012025.xlsx",
            publisher="Statbel",
            title="Conversion Postal code_Refnis code (va01012025)",
            license=STATBEL_LICENSE,
            note=(
                "Dérivé par Statbel des « Postkantons » de bpost ; "
                "publié par Statbel sous CC BY 4.0"
            ),
        ),
        Source(
            id="fluvius-1-23",
            url="https://opendata.fluvius.be/api/explore/v2.1/catalog/datasets/1_23-dnb-per-gemeente-en-per-sector/exports/csv",
            filename="1_23-dnb-per-gemeente-en-per-sector.csv",
            publisher="Fluvius",
            title="Netbeheerder en gas energie-inhoud per gemeente (1_23)",
            license=FLUVIUS_LICENSE,
            note=(
                "Export CSV (jeu mis à jour le 2025-04-01 ; sa pièce jointe .xlsx datée ne "
                "contient que la légende) ; antérieur aux changements de 2026 (2070 Zwijndrecht)"
            ),
        ),
        Source(
            id="odwb-ores-elec",
            url="https://www.odwb.be/api/explore/v2.1/catalog/datasets/ores-electricite-_nb-points-prelevement-par-localite-et-type-client-tension-annu/exports/csv",
            filename="ores-electricite-localite.csv",
            publisher="ORES",
            title=(
                "ORES Électricité — points de prélèvement par localité et type de client (annuel)"
            ),
            license=ODWB_LICENSE,
            note=ODWB_NOTE,
        ),
        Source(
            id="odwb-ores-gas",
            url="https://www.odwb.be/api/explore/v2.1/catalog/datasets/ores-gaz-nombre-de-points-de-prelevement-par-localite-annuel/exports/csv",
            filename="ores-gaz-localite.csv",
            publisher="ORES",
            title="ORES Gaz — points de prélèvement par localité (annuel)",
            license=ODWB_LICENSE,
            note=ODWB_NOTE,
        ),
        Source(
            id="decret-2023-05-19-fusion-bastogne-bertogne",
            url="https://etaamb.openjustice.be/fr/decret-du-19-mai-2023_n2023203212.html",
            filename="decret-du-19-mai-2023_n2023203212.html",
            publisher="Parlement wallon (Moniteur belge)",
            title=(
                "Décret du 19 mai 2023 relatif à la fusion des communes de Bastogne et de "
                "Bertogne"
            ),
            license="",
            note=(
                "Copie etaamb.openjustice.be du Moniteur belge (MB 23/06/2023, numac "
                "2023203212) ; art. 2 : « La date de fusion est le 2 décembre 2024 » ; art. 3 : "
                "la nouvelle commune porte le nom de Bastogne ; empreinte de la page HTML"
            ),
            role="R",
        ),
    )
}


@dataclass(frozen=True)
class Fetched:
    source: Source
    path: Path
    sha256: str
    retrieved_at: str
    size: int


def download(url: str) -> bytes:
    """GET `url` over https and return its bytes."""
    if not url.startswith("https://"):
        raise ValueError(f"{url}: only https URLs are fetched")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data: bytes = response.read()
    return data


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cached(source: Source, cache: Path = CACHE) -> Fetched | None:
    """The cached copy of `source`, if it is complete and its bytes match fetch.json."""
    directory = cache / source.id
    path, meta_path = directory / source.filename, directory / METADATA_NAME
    if not path.is_file() or not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_bytes().decode("utf-8"))
    data = path.read_bytes()
    digest = sha256_hex(data)
    if meta.get("url") != source.url or meta.get("sha256") != digest:
        return None
    return Fetched(source, path, digest, str(meta["retrieved_at"]), len(data))


def fetch(source: Source, *, cache: Path = CACHE, refresh: bool = False) -> Fetched:
    """Download `source` into `.cache/<id>/` (unless already cached) and describe it."""
    if not refresh:
        hit = cached(source, cache)
        if hit is not None:
            return hit
    data = download(source.url)
    directory = cache / source.id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / source.filename
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)
    fetched = Fetched(source, path, sha256_hex(data), date.today().isoformat(), len(data))
    meta = {
        "id": source.id,
        "url": source.url,
        "filename": source.filename,
        "retrieved_at": fetched.retrieved_at,
        "sha256": fetched.sha256,
        "bytes": fetched.size,
    }
    text = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (directory / METADATA_NAME).write_bytes(text.encode("utf-8"))
    return fetched


def ensure(source_id: str, *, cache: Path = CACHE) -> Path:
    """The local path of a source, downloaded first if the cache does not hold it."""
    return fetch(SOURCES[source_id], cache=cache).path


def source_row(fetched: Fetched) -> dict[str, str]:
    source = fetched.source
    return {
        "id": source.id,
        "role": source.role,
        "publisher": source.publisher,
        "title": source.title,
        "url": source.url,
        "retrieved_at": fetched.retrieved_at,
        "sha256": fetched.sha256,
        "license": source.license,
        "note": source.note,
    }


def record(items: Sequence[Fetched], sources_csv: Path = SOURCES_CSV) -> None:
    """Add or replace the rows of `items` in sources.csv; every other row is kept."""
    rows = csvio.read_csv(sources_csv, schema.SOURCES_HEADER)
    by_id = {row["id"]: row for row in rows}
    for item in items:
        by_id[item.source.id] = source_row(item)
    csvio.write_csv(sources_csv, schema.SOURCES_HEADER, [by_id[key] for key in sorted(by_id)])


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(description="Download the sources into .cache/.")
    parser.add_argument("ids", nargs="*", help="source ids (default: every source)")
    parser.add_argument("--refresh", action="store_true", help="download even when cached")
    parser.add_argument("--record", action="store_true", help="write their rows in sources.csv")
    parser.add_argument("--list", action="store_true", help="list the known sources and exit")
    parser.add_argument("--cache", type=Path, default=CACHE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.list:
        for source in SOURCES.values():
            print(f"{source.id}\t{source.url}")
        return 0
    unknown = [source_id for source_id in args.ids if source_id not in SOURCES]
    if unknown:
        parser.error(f"unknown source ids: {', '.join(unknown)}")
    items = []
    for source_id in args.ids or list(SOURCES):
        try:
            item = fetch(SOURCES[source_id], cache=args.cache, refresh=args.refresh)
        except OSError as exc:
            print(f"error: {source_id}: {exc}", file=sys.stderr)
            return 2
        items.append(item)
        print(f"{item.source.id}\t{item.retrieved_at}\t{item.size}\t{item.sha256}")
    if args.record:
        record(items)
        print(f"recorded {len(items)} sources in {SOURCES_CSV.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
