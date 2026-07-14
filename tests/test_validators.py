"""入力検証(validators)のテスト。"""
from __future__ import annotations

import pytest

from src.validators import (
    ValidationError,
    is_blocked_domain,
    validate_csv_extension,
    validate_fetch_url,
    validate_required_title,
    validate_url_format,
)


def test_validate_required_title_raises_on_empty():
    with pytest.raises(ValidationError):
        validate_required_title("")
    with pytest.raises(ValidationError):
        validate_required_title(None)
    with pytest.raises(ValidationError):
        validate_required_title("   ")


def test_validate_required_title_ok():
    assert validate_required_title(" 案件タイトル ") == "案件タイトル"


def test_validate_url_format_rejects_invalid_url():
    with pytest.raises(ValidationError):
        validate_url_format("これはURLではありません")


def test_validate_url_format_accepts_valid_url():
    assert validate_url_format("https://example.com/jobs/1") == "https://example.com/jobs/1"


def test_validate_url_format_allows_empty():
    assert validate_url_format(None) is None
    assert validate_url_format("") is None


def test_is_blocked_domain_crowdworks():
    assert is_blocked_domain("https://crowdworks.jp/public/jobs/12345") is True
    assert is_blocked_domain("https://www.crowdworks.jp/public/jobs/12345") is True
    assert is_blocked_domain("https://example.com/jobs/1") is False


def test_validate_fetch_url_blocks_crowdworks():
    with pytest.raises(ValidationError):
        validate_fetch_url("https://crowdworks.jp/public/jobs/12345")


def test_validate_fetch_url_allows_other_domain():
    assert validate_fetch_url("https://example.com/jobs/1") == "https://example.com/jobs/1"


def test_validate_csv_extension_rejects_non_csv():
    with pytest.raises(ValidationError):
        validate_csv_extension("jobs.xlsx")


def test_validate_csv_extension_accepts_csv():
    validate_csv_extension("jobs.csv")
