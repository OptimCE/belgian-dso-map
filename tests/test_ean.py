"""The informative EAN check: format, Belgian prefix, GS1 check digit, Sibelga prefix."""

from __future__ import annotations

import pytest

import lookup

FULLWIDTH_DIGITS = "".join(chr(0xFF10 + int(digit)) for digit in "541448200000000008")


@pytest.mark.parametrize(
    ("ean", "digit"),
    [
        ("541448200000000001", 8),
        ("541448200000000008", 8),
        ("541448900000000007", 7),
        ("871685900000000004", 4),
        ("541448920000100002", 2),
    ],
)
def test_gs1_check_digit(ean: str, digit: int) -> None:
    assert lookup.gs1_check_digit(ean[:17]) == digit


def test_dev_ean_has_a_wrong_check_digit_but_a_valid_format() -> None:
    assert lookup.check_ean("541448200000000001") == {
        "ean": "541448200000000001",
        "format": True,
        "belgian_prefix": True,
        "gs1_check": False,
        "known_operator": None,
    }


def test_sibelga_prefix_is_reported_never_enforced() -> None:
    check = lookup.check_ean(" 541448900000000007 ")
    assert check["ean"] == "541448900000000007"
    assert check["known_operator"] == "sibelga"
    assert check["gs1_check"] is True


def test_liege_demo_ean_collides_with_the_sibelga_prefix() -> None:
    """Q7: the RESA demo EANs start with 5414489 too, so they read as Sibelga."""
    assert lookup.check_ean("541448920000100002")["known_operator"] == "sibelga"


def test_foreign_ean() -> None:
    check = lookup.check_ean("871685900000000004")
    assert (check["format"], check["belgian_prefix"], check["gs1_check"]) == (True, False, True)


@pytest.mark.parametrize(
    "raw",
    [
        "54144820000000000",
        "5414482000000",
        "54144820000000000A",
        "5414 4820 0000 0000 08",
        FULLWIDTH_DIGITS,
        "",
        None,
    ],
)
def test_invalid_format_makes_every_check_false(raw: str | None) -> None:
    check = lookup.check_ean(raw)
    assert check["format"] is False
    assert check["belgian_prefix"] is False
    assert check["gs1_check"] is None
    assert check["known_operator"] is None
