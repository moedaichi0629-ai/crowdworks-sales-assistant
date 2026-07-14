"""入力値検証ユーティリティ。"""
from __future__ import annotations

import validators as validators_lib

from src.config import BLOCKED_FETCH_DOMAINS, MAX_CSV_UPLOAD_SIZE_MB


class ValidationError(Exception):
    """入力検証エラー。ユーザー向けメッセージをそのまま保持する。"""


def validate_required_title(title: str | None) -> str:
    """案件タイトルが未入力でないことを検証する。"""
    if not title or not title.strip():
        raise ValidationError("案件タイトルは必須項目です。入力してください。")
    return title.strip()


def is_valid_url(url: str | None) -> bool:
    """URLとして妥当な形式か判定する（空はTrue扱い＝任意項目のため）。"""
    if not url:
        return True
    return bool(validators_lib.url(url))


def validate_url_format(url: str | None) -> str | None:
    """URL形式を検証する。不正な場合はValidationErrorを送出する。"""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not validators_lib.url(url):
        raise ValidationError(f"URLの形式が正しくありません: {url}")
    return url


def is_blocked_domain(url: str) -> bool:
    """自動取得が禁止されているドメインかどうかを判定する。"""
    from urllib.parse import urlsplit

    netloc = urlsplit(url).netloc.lower()
    return any(netloc == d or netloc.endswith("." + d) for d in BLOCKED_FETCH_DOMAINS)


def validate_fetch_url(url: str | None) -> str:
    """URL取得機能で使うURLを検証する（形式・禁止ドメインの両方をチェック）。"""
    validated = validate_url_format(url)
    if not validated:
        raise ValidationError("取得先URLを入力してください。")
    if is_blocked_domain(validated):
        raise ValidationError(
            "クラウドワークス（crowdworks.jp）はrobots.txtでAIクローラーによる"
            "自動アクセスを明示的に禁止しているため、このツールから自動取得することはできません。"
            "手動入力またはCSVアップロードをご利用ください。"
        )
    return validated


def validate_csv_file_size(size_bytes: int) -> None:
    """アップロードされたCSVのサイズを検証する。"""
    max_bytes = MAX_CSV_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(
            f"CSVファイルのサイズが上限（{MAX_CSV_UPLOAD_SIZE_MB}MB）を超えています。"
        )


def validate_csv_extension(filename: str) -> None:
    """アップロードされたファイルの拡張子を検証する。"""
    if not filename.lower().endswith(".csv"):
        raise ValidationError("CSVファイル（拡張子.csv）のみアップロードできます。")
