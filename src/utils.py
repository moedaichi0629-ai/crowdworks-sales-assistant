"""日時処理・URL正規化などの汎用ユーティリティ。"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import pytz

from src.config import DEFAULT_TIMEZONE

JST = pytz.timezone(DEFAULT_TIMEZONE)


def now_jst_str() -> str:
    """現在時刻を日本時間の文字列（YYYY-MM-DD HH:MM:SS）で返す。"""
    return now_jst().strftime("%Y-%m-%d %H:%M:%S")


def now_jst():
    """現在時刻を日本時間のdatetimeで返す。"""
    import datetime

    return datetime.datetime.now(JST)


def normalize_url(url: str | None) -> str | None:
    """URLを重複判定・比較しやすい形に正規化する。

    クエリパラメータ・フラグメント・末尾スラッシュ・スキームの大文字小文字差異を吸収する。
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or ""
    normalized = urlunsplit((scheme, netloc, path, "", ""))
    return normalized


def truncate(text: str | None, length: int = 200) -> str:
    """文字列を指定長で省略表示用に切り詰める。"""
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= length else text[:length] + "…"
