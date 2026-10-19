"""build.py: flattening, release files, determinism, SHA256SUMS and the previous version."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

import build
import csvio
import schema
import validate
from helpers import MINI, ROOT, context, edit_csv, make_args, row_of

FIXTURE_DRAFT = ["--fixture", "--draft"]


def read(out: Path, name: str) -> list[dict[str, str]]:
    _, rows = csvio.parse_csv((out / name).read_bytes(), name=name)
    return rows


@pytest.fixture(scope="module")
def mini_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("build") / "mini"
    assert build.main([*FIXTURE_DRAFT, "--out", str(out)]) == 0
    return out


def test_flatten_sorts_whatever_the_input_order() -> None:
    ds = context().dataset
    shuffled = dataclasses.replace(
        ds, postcodes=ds.postcodes[::-1], sections=ds.sections[::-1], communes=ds.communes[::-1]
    )
    assert build.flatten(shuffled) == build.flatten(ds)


def test_published_files_do_not_depend_on_the_row_order_of_data() -> None:
    ds = context().dataset
    shuffled = dataclasses.replace(
        ds, postcodes=ds.postcodes[::-1], sources=ds.sources[::-1], notes=ds.notes[::-1]
    )

    def files(dataset: schema.Dataset) -> dict[str, bytes]:
        return build.make_build(
            dataset,
            version="2026.10.0",
            date="2026-10-12",
            draft=True,
            previous=None,
            vectors_bytes=b"",
            attribution_bytes=b"",
        ).files

    assert files(shuffled) == files(ds)


def test_flatten_one_row_per_postcode_ins_section() -> None:
    rows = build.flatten(context().dataset)
    keys = [(row["postcode"], row["ins"], row["section_key"]) for row in rows]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)) == 15
    assert [key for key in keys if key[0] == "1040"] == [
        ("1040", "21004", ""),
        ("1040", "21005", ""),
    ]
    assert [key[2] for key in keys if key[0] == "2387"] == ["baarle-hertog", "zondereigen"]
    namur = [row for row in rows if row["ins"] == "92094"]
    assert all(row["section_key"] for row in namur), "a sectioned commune has no commune-level row"


def test_release_files(mini_build: Path) -> None:
    assert sorted(path.name for path in mini_build.iterdir()) == sorted(build.OUTPUT_FILES)
    for name, header in build.DIST_HEADERS.items():
        found, _ = csvio.parse_csv((mini_build / name).read_bytes(), name=name)
        assert found == header
    assert "accepted_by" not in (mini_build / "notes.csv").read_text(encoding="utf-8")
    assert (mini_build / "vectors.csv").read_bytes() == (MINI / "vectors.csv").read_bytes()
    assert (mini_build / "ATTRIBUTION.md").read_bytes() == (ROOT / "ATTRIBUTION.md").read_bytes()


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")  # fmt: skip


def test_attribution_is_written_for_the_public() -> None:
    """ATTRIBUTION.md is published as is: on the website's table page and in dso-lookup.

    Both consumers drop its first line, "# Attribution". It carries no draft marker, no
    open-question id, no repository file and no code, and it gives the date the sources
    were last retrieved (the latest `retrieved_at` of data/sources.csv). It states the
    dataset's licence (CC BY 4.0, by OptimCE) and how to credit it.
    """
    text = (ROOT / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert text.startswith("# Attribution\n\n")
    assert not re.search(r"(?i)\bdraft\b", text)
    assert not re.search(r"\b[QG][0-9]+\b", text)
    assert "`" not in text
    assert not re.search(r"\b[\w-]+\.(csv|md|json|py|yml)\b", text)
    assert "LICENSE" not in text
    assert "OptimCE" in text
    # The dataset's own licence, how to credit it, and the sources' credits kept.
    assert "licensed by OptimCE under the Creative Commons Attribution 4.0" in text
    assert "(CC BY 4.0), <https://creativecommons.org/licenses/by/4.0/>" in text
    assert '"belgian-dso-map, OptimCE"' in text
    assert "<https://github.com/OptimCE/belgian-dso-map>" in text
    assert "keep their own licences and attribution requirements" in text
    assert "later version" not in text
    sources = csvio.read_csv(ROOT / "data" / "sources.csv", schema.SOURCES_HEADER)
    year, month, day = max(row["retrieved_at"] for row in sources).split("-")
    assert f"last retrieved on {int(day)} {MONTHS[int(month) - 1]} {year}" in text


def test_draft_data_version_everywhere(mini_build: Path) -> None:
    release = json.loads((mini_build / "release.json").read_text(encoding="utf-8"))
    assert release == {
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
            "sources": 12,
        },
    }
    for name in build.DIST_HEADERS:
        assert {row["data_version"] for row in read(mini_build, name)} == {"2026.10.0-draft"}
        assert {(row["first_seen"], row["changed_at"]) for row in read(mini_build, name)} == {
            ("2026-10-12", "2026-10-12")
        }
    assert (mini_build / "CHANGES.md").read_text(encoding="utf-8") == (
        "# Changes\n\n## 2026.10.0 — 2026-10-12\n- initial release\n"
    )


def test_operators_keep_the_display_order_and_sources_are_sorted(mini_build: Path) -> None:
    ids = [row["id"] for row in read(mini_build, "operators.csv")]
    assert ids[:6] == ["ores", "resa", "aieg", "aiesh", "rew", "sibelga"]
    assert ids[-2:] == ["enexis", "elia"]
    sources = [row["id"] for row in read(mini_build, "sources.csv")]
    assert sources == sorted(sources)


def test_readme_release_json_example_is_the_mini_build(mini_build: Path) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    example = re.search(
        r"`release\.json` \(here the mini fixture's draft.*?```json\n(.*?)```", readme, re.S
    )
    assert example is not None
    assert json.loads(example.group(1)) == json.loads(
        (mini_build / "release.json").read_text(encoding="utf-8")
    )


def test_two_builds_are_byte_identical(mini_build: Path, tmp_path: Path) -> None:
    again = tmp_path / "again"
    assert build.main([*FIXTURE_DRAFT, "--out", str(again)]) == 0
    for name in build.OUTPUT_FILES:
        assert (again / name).read_bytes() == (mini_build / name).read_bytes(), name


def test_sha256sums_lists_every_other_file(mini_build: Path) -> None:
    lines = (mini_build / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    names = [line.split("  ", 1)[1] for line in lines]
    assert names == sorted(set(build.OUTPUT_FILES) - {"SHA256SUMS"})
    for line in lines:
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256((mini_build / name).read_bytes()).hexdigest()


def test_sha256sums_is_written_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[str] = []
    monkeypatch.setattr(csvio, "write_bytes", lambda path, data: written.append(path.name))
    build.write_outputs(tmp_path / "out", {name: b"x\n" for name in build.OUTPUT_FILES})
    assert sorted(written) == sorted(build.OUTPUT_FILES)
    assert written[-1] == "SHA256SUMS"


def test_every_output_is_lf_utf8_without_bom(mini_build: Path) -> None:
    for name in build.OUTPUT_FILES:
        csvio.check_text_bytes((mini_build / name).read_bytes(), name)


def test_refuses_an_output_directory_with_other_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "notes.txt").write_bytes(b"x\n")
    assert build.main([*FIXTURE_DRAFT, "--out", str(out)]) == 1
    assert "notes.txt" in capsys.readouterr().err
    assert sorted(path.name for path in out.iterdir()) == ["notes.txt"]


def test_a_mode_is_required() -> None:
    with pytest.raises(SystemExit):
        build.main(["--fixture"])


def test_validation_errors_write_nothing(mini_copy: Path, tmp_path: Path) -> None:
    edit_csv(
        mini_copy / "assignments.csv",
        lambda rows: row_of(rows, ins="25112").update(elec_operator="elia"),
    )
    out = tmp_path / "out"
    assert build.main([*FIXTURE_DRAFT, "--data-dir", str(mini_copy), "--out", str(out)]) == 1
    assert not out.exists()


def test_release_needs_accepted_notes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert build.main(["--fixture", "--release", "--out", str(tmp_path / "rel")]) == 1
    assert "rule 4" in capsys.readouterr().err


def test_a_fixture_release_never_targets_dist(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build.main(["--fixture", "--release"])
    assert exit_info.value.code == 2
    assert "needs --out" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["--version", "2026.13.0", "--date", "2026-12-01"],
        ["--version", "2026.11.0-draft", "--date", "2026-11-02"],
        ["--version", "2026.11.0", "--date", "2026-11-31"],
    ],
)
def test_a_malformed_version_or_date_is_a_usage_error(tmp_path: Path, arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build.main([*FIXTURE_DRAFT, *arguments, "--out", str(tmp_path / "out")])
    assert exit_info.value.code == 2
    with pytest.raises(SystemExit) as exit_info:
        validate.main(["--fixture", *arguments])
    assert exit_info.value.code == 2
    assert not (tmp_path / "out").exists()


def test_fixture_has_its_own_release_json(tmp_path: Path) -> None:
    """Bumping the root release.json (release procedure, step 1) moves no fixture build."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "release.json").write_bytes(
        b'{"version": "2026.11.0", "date": "2026-11-02", "previous": "2026.10.0"}\n'
    )
    shutil.copyfile(ROOT / "ATTRIBUTION.md", root / "ATTRIBUTION.md")
    ctx = build.load_context(make_args(), release=True, root=root)
    assert (ctx.version, ctx.date, ctx.named_previous) == ("2026.10.0", "2026-10-12", "")


def test_version_and_date_are_in_the_same_month() -> None:
    with pytest.raises(build.BuildError, match="same month"):
        context(version="2026.11.0", date="2026-10-30")
    with pytest.raises(build.BuildError, match="--draft"):
        context(version="2026.11.0-draft", date="2026-11-02")


# --- previous version -----------------------------------------------------------------------


def build_version(data_dir: Path, out: Path, version: str, date: str, *extra: str) -> None:
    args = ["--data-dir", str(data_dir), *FIXTURE_DRAFT, "--version", version, "--date", date]
    assert build.main([*args, *extra, "--out", str(out)]) == 0


def test_dates_follow_the_content_between_versions(mini_copy: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build_version(mini_copy, first, "2026.10.0", "2026-10-12")

    edit_csv(
        mini_copy / "sections.csv",
        lambda rows: row_of(rows, section_key="champion").update(valid_from="2023-02-26"),
    )
    edit_csv(
        mini_copy / "postcodes.csv", lambda rows: [row for row in rows if row["postcode"] != "1301"]
    )
    edit_csv(
        mini_copy / "vectors.csv", lambda rows: [row for row in rows if row["name"] != "wavre-1301"]
    )
    edit_csv(
        mini_copy / "operators.csv",
        lambda rows: row_of(rows, id="enexis").update(website="https://www.enexis.nl/"),
    )
    build_version(mini_copy, second, "2026.11.0", "2026-11-02", "--previous", str(first))

    before = {(r["postcode"], r["ins"], r["section_key"]): r for r in read(first, "dso_lookup.csv")}
    after = {(r["postcode"], r["ins"], r["section_key"]): r for r in read(second, "dso_lookup.csv")}
    assert set(before) - set(after) == {("1301", "25112", "")}
    for key, row in after.items():
        expected = (
            ("2026-10-12", "2026-11-02")
            if key == ("5020", "92094", "champion")
            else ("2026-10-12", "2026-10-12")
        )
        assert (row["first_seen"], row["changed_at"]) == expected, key
        assert row["data_version"] == "2026.11.0-draft"
    operators = {row["id"]: row for row in read(second, "operators.csv")}
    assert operators["enexis"]["changed_at"] == "2026-11-02"
    assert operators["ores"]["changed_at"] == "2026-10-12"

    assert (second / "CHANGES.md").read_text(encoding="utf-8") == (
        "# Changes\n"
        "\n"
        "## 2026.11.0 — 2026-11-02\n"
        "- removed dso_lookup 1301|25112| — Wavre\n"
        "- changed dso_lookup 5020|92094|champion — Champion (Namur); valid_from: ∅→2023-02-26\n"
        "- changed operators enexis — Enexis; website\n"
        "\n"
        "## 2026.10.0 — 2026-10-12\n"
        "- initial release\n"
    )
    release = json.loads((second / "release.json").read_text(encoding="utf-8"))
    assert (release["version"], release["previous"]) == ("2026.11.0-draft", "2026.10.0-draft")


def test_unchanged_data_gives_no_changes(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build_version(MINI, first, "2026.10.0", "2026-10-12")
    build_version(MINI, second, "2026.10.1", "2026-10-20", "--previous", str(first))
    assert "## 2026.10.1 — 2026-10-20\n- no changes\n" in (second / "CHANGES.md").read_text(
        encoding="utf-8"
    )
    for name in build.DIST_HEADERS:
        assert {row["changed_at"] for row in read(second, name)} == {"2026-10-12"}


def test_previous_must_be_older(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = tmp_path / "a"
    build_version(MINI, first, "2026.10.0", "2026-10-12")
    args = [*FIXTURE_DRAFT, "--previous", str(first), "--out", str(tmp_path / "b")]
    assert build.main(args) == 1
    assert "not newer" in capsys.readouterr().err


def test_previous_ref_reads_dist_from_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "a"
    build_version(MINI, first, "2026.10.0", "2026-10-12")
    asked: list[str] = []

    def fake_git_show(root: Path, spec: str) -> bytes:
        asked.append(spec)
        return (first / spec.split(":dist/", 1)[1]).read_bytes()

    monkeypatch.setattr(build, "_git_show", fake_git_show)
    previous = build.load_previous_ref("2026.10.0", ROOT)
    assert previous.release.version == "2026.10.0-draft"
    assert asked == [f"2026.10.0:dist/{name}" for name in build.PREVIOUS_FILES]


def test_default_previous_is_the_committed_dist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    assert (
        build.resolve_previous(
            root, previous_dir=None, previous_ref=None, fixture=False, version="2026.10.0"
        )
        is None
    )
    first = tmp_path / "a"
    build_version(MINI, first, "2026.10.0", "2026-10-12")
    shutil.copytree(first, root / "dist")
    found = build.resolve_previous(
        root, previous_dir=None, previous_ref=None, fixture=False, version="2026.11.0"
    )
    assert found is not None and found.release.version == "2026.10.0-draft"
    assert (
        build.resolve_previous(
            root, previous_dir=None, previous_ref=None, fixture=True, version="2026.11.0"
        )
        is None
    )
    with pytest.raises(build.BuildError, match="newer"):
        build.resolve_previous(
            root, previous_dir=None, previous_ref=None, fixture=False, version="2026.09.0"
        )


def test_rebuilding_the_published_version_reads_its_previous_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = tmp_path / "older"
    build_version(MINI, older, "2026.10.0", "2026-10-12")
    root = tmp_path / "repo"
    (root / "dist").mkdir(parents=True)
    (root / "dist" / "release.json").write_bytes(b"{}\n")
    published = build.Previous(
        "dist", build.Release("2026.11.0", "2026-11-02", "2026.10.0"), {}, ""
    )
    monkeypatch.setattr(build, "load_previous_dir", lambda path: published)
    asked: list[str] = []

    def fake_git_show(_: Path, spec: str) -> bytes:
        asked.append(spec)
        return (older / spec.split(":dist/", 1)[1]).read_bytes()

    monkeypatch.setattr(build, "_git_show", fake_git_show)
    found = build.resolve_previous(
        root, previous_dir=None, previous_ref=None, fixture=False, version="2026.11.0"
    )
    assert found is not None and found.release.version == "2026.10.0-draft"
    assert asked[0] == "refs/tags/2026.10.0:dist/release.json"


def test_previous_rows_carry_its_version(tmp_path: Path) -> None:
    first = tmp_path / "a"
    build_version(MINI, first, "2026.10.0", "2026-10-12")
    assert build.load_previous_dir(first).release.version == "2026.10.0-draft"
    edit_csv(
        first / "notes.csv",
        lambda rows: row_of(rows, key="baarle-hertog-enclaves").update(data_version="2026.09.0"),
    )
    with pytest.raises(build.BuildError, match="data_version differs"):
        build.load_previous_dir(first)


def test_published_release_json_is_checked(tmp_path: Path) -> None:
    with pytest.raises(build.BuildError, match="keys"):
        build.parse_release(b'{"version": "2026.10.0"}\n', "release.json", published=False)
    with pytest.raises(build.BuildError, match="YYYY-MM-DD"):
        build.parse_release(
            b'{"version": "2026.10.0", "date": "2026-10-32", "previous": ""}\n',
            "release.json",
            published=False,
        )
    with pytest.raises(build.BuildError, match="draft"):
        build.parse_release(
            b'{"version": "2026.10.0-draft", "date": "2026-10-12", "previous": ""}\n',
            "release.json",
            published=False,
        )
    root = build.parse_release(
        (ROOT / "release.json").read_bytes(), "release.json", published=False
    )
    assert schema.VERSION_RE.fullmatch(root.version)
