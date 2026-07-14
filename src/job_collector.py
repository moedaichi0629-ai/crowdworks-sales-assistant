"""公開ページURLからの案件情報取得モジュール（HTML取得部分を独立させた構成）。

重要な注意事項:
    クラウドワークス(crowdworks.jp)は robots.txt で ClaudeBot / GPTBot などの
    AIクローラーを明示的に拒否しており、/api/ 配下も公開APIの一部を除き
    クロールを禁止している。そのため本モジュールは crowdworks.jp への
    自動アクセスを `validate_fetch_url` の時点でブロックする。

    本モジュールはユーザーが自身の判断で指定した「取得が許可されている
    公開ページ」（利用規約・robots.txtで自動取得が禁止されていないページ）
    にのみ利用すること。HTMLセレクタは `SELECTORS` に集約してあるため、
    対象サイトのHTML構造に合わせて調整・差し替えができる。
    将来的に別の取得方法（公式API・RSS等）へ差し替える場合も、
    このファイルのインターフェースだけを守ればよい。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.config import (
    MAX_RETRY_COUNT,
    MIN_FETCH_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    SOURCE_TYPE_URL,
    USER_AGENT,
)
from src.logger import get_logger
from src.parsers import extract_fields_from_body
from src.repositories import log_import, upsert_job
from src.utils import now_jst_str
from src.validators import ValidationError, validate_fetch_url

logger = get_logger()

# --- HTMLセレクタ定義（サイト構造変更時はここだけ直せばよい） -----------------------
SELECTORS = {
    "list_link": "a",
    "title": "h1",
    "body": "main, article, .job-detail, .detail, body",
}

LOGIN_PAGE_KEYWORDS = ["ログイン", "log in", "sign in", "password", "パスワードを入力"]
CAPTCHA_KEYWORDS = ["captcha", "recaptcha", "私はロボットではありません"]

_last_access_by_domain: dict[str, float] = {}


class FetchError(Exception):
    """取得処理全般のエラー。"""


class LoginRequiredError(FetchError):
    """ログインページへ遷移したため処理を中断した。"""


class CaptchaDetectedError(FetchError):
    """CAPTCHAが検出されたため処理を中断した。"""


class StructureChangedError(FetchError):
    """想定していたHTML構造が見つからなかった。"""


@dataclass
class FetchResult:
    url: str
    title: str | None = None
    body: str | None = None
    extra: dict = field(default_factory=dict)


def _respect_rate_limit(url: str, wait_seconds: float) -> None:
    """同一ドメインへの連続アクセスを避けるため、必要に応じて待機する。"""
    from urllib.parse import urlsplit

    domain = urlsplit(url).netloc
    last = _last_access_by_domain.get(domain)
    now = time.monotonic()
    min_interval = max(wait_seconds, MIN_FETCH_INTERVAL_SECONDS)
    if last is not None:
        elapsed = now - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    # ランダムな短い待機を追加し、負荷集中や機械的アクセスの印象を避ける
    time.sleep(random.uniform(0.2, 0.8))
    _last_access_by_domain[domain] = time.monotonic()


@retry(
    reraise=True,
    stop=stop_after_attempt(MAX_RETRY_COUNT + 1),
    wait=wait_fixed(2),
    retry=retry_if_exception_type(requests.RequestException),
)
def _http_get(url: str) -> requests.Response:
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    return response


def fetch_page(url: str, wait_seconds: float = MIN_FETCH_INTERVAL_SECONDS) -> str:
    """指定URLのHTMLを安全策付きで取得する。

    - URLの妥当性・禁止ドメインを検証する
    - User-Agent / タイムアウトを設定する
    - 同一ドメインへの連続アクセスを避けるため待機する
    - HTTPステータスを確認する
    - ログインページ・CAPTCHAを検知した場合は例外を送出して停止する
    """
    validated_url = validate_fetch_url(url)
    _respect_rate_limit(validated_url, wait_seconds)

    logger.info("URL取得を開始します: url=%s", validated_url)
    try:
        response = _http_get(validated_url)
    except requests.RequestException as exc:
        logger.error("URL取得に失敗しました(通信エラー): url=%s error=%s", validated_url, exc)
        raise FetchError(f"通信に失敗しました: {exc}") from exc

    if response.status_code != 200:
        logger.error("URL取得に失敗しました(HTTPエラー): url=%s status=%s", validated_url, response.status_code)
        raise FetchError(f"ページを取得できませんでした（HTTPステータス: {response.status_code}）")

    html = response.text
    lowered = html.lower()

    if any(k.lower() in lowered for k in CAPTCHA_KEYWORDS):
        logger.warning("CAPTCHAを検知したため取得を中断しました: url=%s", validated_url)
        raise CaptchaDetectedError("CAPTCHAが表示されたため取得を中断しました。")

    if any(k.lower() in lowered for k in LOGIN_PAGE_KEYWORDS[:2]) and "<form" in lowered and "password" in lowered:
        logger.warning("ログインページへの遷移を検知したため取得を中断しました: url=%s", validated_url)
        raise LoginRequiredError("ログインが必要なページのため取得を中断しました。")

    logger.info("URL取得が完了しました: url=%s", validated_url)
    return html


def parse_job_detail(html: str, url: str) -> FetchResult:
    """案件詳細ページのHTMLからタイトル・本文を抽出する。

    セレクタが一致しない場合はStructureChangedErrorを送出し、
    呼び出し側でログに記録した上で処理を継続できるようにする。
    """
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(SELECTORS["title"])
    body_el = soup.select_one(SELECTORS["body"])

    if title_el is None and body_el is None:
        raise StructureChangedError(
            "想定していたHTML構造が見つかりませんでした。サイト構造が変更された可能性があります。"
        )

    title = title_el.get_text(strip=True) if title_el else None
    body = body_el.get_text("\n", strip=True) if body_el else None

    return FetchResult(url=url, title=title, body=body)


def collect_jobs_from_urls(
    conn,
    urls: list[str],
    keyword: str = "",
    max_count: int = 20,
    wait_seconds: float = MIN_FETCH_INTERVAL_SECONDS,
) -> dict:
    """複数の案件詳細URLから情報を取得し、DBへ登録する。

    1件の取得・解析に失敗しても処理全体は継続する。
    """
    urls = urls[:max_count]
    inserted = updated = duplicate = errors = 0
    error_rows: list[dict] = []

    for url in urls:
        try:
            html = fetch_page(url, wait_seconds=wait_seconds)
            result = parse_job_detail(html, url)
            if not result.title:
                raise ValidationError("案件タイトルを取得できませんでした。")

            extracted = extract_fields_from_body(result.body)
            data = {
                "title": result.title,
                "url": url,
                "body": result.body,
                "source_type": SOURCE_TYPE_URL,
                "matched_keyword": keyword or None,
                "collected_at": now_jst_str(),
                **{k: v for k, v in extracted.items() if v is not None},
            }
            action, _job_id = upsert_job(conn, data)
            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                duplicate += 1
        except Exception as exc:  # noqa: BLE001 - URL単位でエラーを収集し処理継続する
            errors += 1
            error_rows.append({"url": url, "reason": str(exc)})
            logger.warning("案件取得エラー: url=%s reason=%s", url, exc)

    log_import(
        conn,
        source_type=SOURCE_TYPE_URL,
        source_name=keyword or "URL取得",
        total_count=len(urls),
        inserted_count=inserted,
        updated_count=updated,
        duplicate_count=duplicate,
        error_count=errors,
        error_detail="; ".join(f"{r['url']}: {r['reason']}" for r in error_rows),
    )

    return {
        "total": len(urls),
        "inserted": inserted,
        "updated": updated,
        "duplicate": duplicate,
        "errors": errors,
        "error_rows": error_rows,
    }
