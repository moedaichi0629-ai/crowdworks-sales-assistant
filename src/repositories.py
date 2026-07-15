"""jobs / settings / import_logs / job_analyses / user_profiles / skills / portfolios /
analysis_settings テーブルに対するデータアクセス層。"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional

from src.config import DEFAULT_ANALYSIS_SETTINGS, DEFAULT_SETTINGS, STATUS_UNCONFIRMED
from src.duplicate_checker import find_duplicate
from src.logger import get_logger
from src.utils import normalize_url, now_jst_str

logger = get_logger()

# 更新時にユーザー入力を上書きしてはいけない項目
USER_PRESERVED_FIELDS = ["status", "is_favorite", "memo"]

JOB_COLUMNS = [
    "external_job_id", "title", "url", "normalized_url", "description", "body",
    "job_type", "category", "budget_min", "budget_max", "budget_text", "hourly_rate",
    "published_at", "deadline", "applicant_count", "recruitment_count", "client_name",
    "client_rating", "client_review_count", "identity_verified", "rule_check_verified",
    "matched_keyword", "excluded_keyword", "source_type", "status", "is_favorite",
    "memo", "collected_at",
]


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


def insert_job(conn: sqlite3.Connection, data: dict) -> int:
    """新規案件を1件登録し、内部IDを返す。"""
    data = dict(data)
    data.setdefault("status", STATUS_UNCONFIRMED)
    data.setdefault("is_favorite", 0)
    if data.get("url") and not data.get("normalized_url"):
        data["normalized_url"] = normalize_url(data["url"])

    now = now_jst_str()
    columns = [c for c in JOB_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]

    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO jobs ({', '.join(columns)}) VALUES ({placeholders})"
    cursor = conn.execute(sql, values)
    logger.info("案件を新規登録しました: title=%s", data.get("title"))
    return cursor.lastrowid


def update_job(conn: sqlite3.Connection, job_id: int, data: dict, preserve_user_fields: bool = True) -> None:
    """既存案件を更新する。preserve_user_fields=Trueの場合ユーザー入力項目は上書きしない。"""
    data = dict(data)
    if preserve_user_fields:
        for field in USER_PRESERVED_FIELDS:
            data.pop(field, None)

    if data.get("url") and not data.get("normalized_url"):
        data["normalized_url"] = normalize_url(data["url"])

    data["updated_at"] = now_jst_str()
    columns = [c for c in data if c in JOB_COLUMNS + ["normalized_url", "updated_at"]]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns)
    values = [data[c] for c in columns] + [job_id]
    conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
    logger.info("案件を更新しました: id=%s", job_id)


def _values_differ(existing_row: sqlite3.Row, data: dict) -> bool:
    for key, value in data.items():
        if key in USER_PRESERVED_FIELDS or key not in JOB_COLUMNS:
            continue
        existing_value = existing_row[key] if key in existing_row.keys() else None
        if (existing_value or None) != (value if value not in ("",) else None):
            return True
    return False


def upsert_job(conn: sqlite3.Connection, data: dict) -> tuple[str, int]:
    """案件を新規登録または更新する。

    戻り値は ("inserted" | "updated" | "duplicate", job_id)。
    duplicate は既存案件と内容が完全一致していたため書き込みをスキップしたケース。
    """
    data = dict(data)
    if data.get("url"):
        data["normalized_url"] = normalize_url(data["url"])

    existing = find_duplicate(conn, data)
    if existing is None:
        job_id = insert_job(conn, data)
        return "inserted", job_id

    if _values_differ(existing, data):
        update_job(conn, existing["id"], data, preserve_user_fields=True)
        return "updated", existing["id"]

    return "duplicate", existing["id"]


def update_status_bulk(conn: sqlite3.Connection, job_ids: Iterable[int], status: str) -> int:
    """複数案件のステータスを一括変更する。"""
    now = now_jst_str()
    ids = list(job_ids)
    if not ids:
        return 0
    placeholders = ", ".join(["?"] * len(ids))
    conn.execute(
        f"UPDATE jobs SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
        [status, now, *ids],
    )
    logger.info("ステータスを一括変更しました: ids=%s status=%s", ids, status)
    return len(ids)


def update_memo(conn: sqlite3.Connection, job_id: int, memo: str) -> None:
    conn.execute(
        "UPDATE jobs SET memo = ?, updated_at = ? WHERE id = ?",
        (memo, now_jst_str(), job_id),
    )


def update_favorite(conn: sqlite3.Connection, job_id: int, is_favorite: bool) -> None:
    conn.execute(
        "UPDATE jobs SET is_favorite = ?, updated_at = ? WHERE id = ?",
        (int(is_favorite), now_jst_str(), job_id),
    )


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row)


def list_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM jobs ORDER BY collected_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def get_dashboard_counts(conn: sqlite3.Connection) -> dict:
    """ダッシュボードに表示する集計値を取得する。"""
    from src.config import STATUS_CANDIDATE, STATUS_CONFIRMED, STATUS_SKIPPED, STATUS_APPLIED, STATUS_UNCONFIRMED

    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    today = now_jst_str()[:10]
    today_count = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE substr(collected_at, 1, 10) = ?", (today,)
    ).fetchone()[0]

    def count_status(status: str) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)
        ).fetchone()[0]

    return {
        "total_jobs": total,
        "today_collected": today_count,
        "unconfirmed": count_status(STATUS_UNCONFIRMED),
        "confirmed": count_status(STATUS_CONFIRMED),
        "candidate": count_status(STATUS_CANDIDATE),
        "skipped": count_status(STATUS_SKIPPED),
        "applied": count_status(STATUS_APPLIED),
    }


def get_recent_7days_counts(conn: sqlite3.Connection) -> list[dict]:
    """直近7日間の日別案件取得数を返す。"""
    rows = conn.execute(
        """
        SELECT substr(collected_at, 1, 10) AS day, COUNT(*) AS count
        FROM jobs
        WHERE collected_at >= date('now', '-6 days')
        GROUP BY day
        ORDER BY day
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_counts_by_column(conn: sqlite3.Connection, column: str) -> list[dict]:
    """指定カラムごとの件数を集計する（募集形式・検索キーワード・ステータス等）。"""
    if column not in JOB_COLUMNS + ["status"]:
        raise ValueError(f"不正な集計対象カラムです: {column}")
    rows = conn.execute(
        f"SELECT {column} AS label, COUNT(*) AS count FROM jobs "
        f"WHERE {column} IS NOT NULL AND {column} != '' GROUP BY {column} ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# --- settings ---------------------------------------------------------------

def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute(
        "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    try:
        return json.loads(row["setting_value"])
    except (TypeError, json.JSONDecodeError):
        return row["setting_value"]


def get_all_settings(conn: sqlite3.Connection) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    rows = conn.execute("SELECT setting_key, setting_value FROM settings").fetchall()
    for row in rows:
        try:
            settings[row["setting_key"]] = json.loads(row["setting_value"])
        except (TypeError, json.JSONDecodeError):
            settings[row["setting_key"]] = row["setting_value"]
    return settings


def save_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = now_jst_str()
    serialized = json.dumps(value, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id FROM settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (serialized, now, key),
        )
    else:
        conn.execute(
            "INSERT INTO settings (setting_key, setting_value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, serialized, now, now),
        )
    logger.info("設定を保存しました: key=%s", key)


# --- import_logs --------------------------------------------------------------

def log_import(
    conn: sqlite3.Connection,
    source_type: str,
    source_name: str,
    total_count: int,
    inserted_count: int,
    updated_count: int,
    duplicate_count: int,
    error_count: int,
    error_detail: str = "",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO import_logs
            (source_type, source_name, total_count, inserted_count, updated_count,
             duplicate_count, error_count, error_detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_type, source_name, total_count, inserted_count, updated_count,
            duplicate_count, error_count, error_detail, now_jst_str(),
        ),
    )
    logger.info(
        "インポート結果を記録しました: source=%s total=%s inserted=%s updated=%s duplicate=%s error=%s",
        source_name, total_count, inserted_count, updated_count, duplicate_count, error_count,
    )
    return cursor.lastrowid


# =============================================================================
# 第2段階: job_analyses (AI案件分析結果)
# =============================================================================

JOB_ANALYSIS_JSON_FIELDS = [
    "client_needs", "required_skills", "matched_skills", "missing_skills",
    "matched_portfolio", "strengths", "concerns", "questions",
    "detected_risks", "risk_reasons",
]

JOB_ANALYSIS_COLUMNS = [
    "job_id", "content_hash", "rule_based_score", "rule_based_breakdown_json",
    "ai_suitability_score", "total_score", "recommendation", "application_priority",
    "difficulty", "confidence_score", "summary", "client_needs_json", "required_skills_json",
    "matched_skills_json", "missing_skills_json", "matched_portfolio_json",
    "estimated_hours_min", "estimated_hours_max", "estimated_days", "budget_evaluation",
    "strengths_json", "concerns_json", "questions_json", "application_strategy",
    "analysis_reason", "safety_score", "risk_level", "detected_risks_json",
    "risk_reasons_json", "recommended_action", "safety_summary", "provider", "model",
    "prompt_version", "used_ai", "token_usage_json", "analysis_error",
]


def _analysis_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in JOB_ANALYSIS_JSON_FIELDS:
        key = f"{field}_json"
        if key in data:
            try:
                data[field] = json.loads(data[key]) if data[key] else []
            except (TypeError, json.JSONDecodeError):
                data[field] = []
    for key in ("rule_based_breakdown_json", "token_usage_json"):
        if key in data and data[key]:
            try:
                data[key.removesuffix("_json")] = json.loads(data[key])
            except (TypeError, json.JSONDecodeError):
                data[key.removesuffix("_json")] = None
    return data


def save_job_analysis(conn: sqlite3.Connection, job_id: int, result: dict) -> int:
    """AI案件分析結果を新規保存する（履歴として蓄積し、最新のものが「現在の結果」として扱われる）。"""
    now = now_jst_str()
    data = dict(result)
    data["job_id"] = job_id

    for field in JOB_ANALYSIS_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    if "rule_based_breakdown" in data:
        data["rule_based_breakdown_json"] = json.dumps(data.pop("rule_based_breakdown"), ensure_ascii=False)
    if "token_usage" in data:
        data["token_usage_json"] = json.dumps(data.pop("token_usage"), ensure_ascii=False)

    columns = [c for c in JOB_ANALYSIS_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]

    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO job_analyses ({', '.join(columns)}) VALUES ({placeholders})"
    cursor = conn.execute(sql, values)
    logger.info("AI案件分析結果を保存しました: job_id=%s total_score=%s", job_id, data.get("total_score"))
    return cursor.lastrowid


def get_latest_analysis(conn: sqlite3.Connection, job_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM job_analyses WHERE job_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    return _analysis_row_to_dict(row)


def list_analyses_for_job(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM job_analyses WHERE job_id = ? ORDER BY created_at DESC, id DESC", (job_id,)
    ).fetchall()
    return [_analysis_row_to_dict(r) for r in rows]


def get_jobs_with_latest_analysis(conn: sqlite3.Connection) -> list[dict]:
    """全案件に、存在すれば最新の分析結果を結合して返す（分析結果一覧・案件一覧の表示用）。"""
    rows = conn.execute(
        """
        SELECT j.*,
               a.id AS analysis_id, a.rule_based_score, a.ai_suitability_score, a.total_score,
               a.recommendation, a.application_priority, a.difficulty, a.confidence_score,
               a.summary, a.client_needs_json, a.required_skills_json, a.matched_skills_json,
               a.missing_skills_json, a.matched_portfolio_json, a.estimated_hours_min,
               a.estimated_hours_max, a.estimated_days, a.budget_evaluation, a.strengths_json,
               a.concerns_json, a.questions_json, a.application_strategy, a.analysis_reason,
               a.safety_score, a.risk_level, a.detected_risks_json, a.risk_reasons_json,
               a.recommended_action, a.safety_summary, a.provider, a.model, a.prompt_version,
               a.used_ai, a.token_usage_json, a.analysis_error, a.created_at AS analyzed_at
        FROM jobs j
        LEFT JOIN (
            SELECT ja1.* FROM job_analyses ja1
            WHERE ja1.id = (
                SELECT ja2.id FROM job_analyses ja2
                WHERE ja2.job_id = ja1.job_id
                ORDER BY ja2.created_at DESC, ja2.id DESC LIMIT 1
            )
        ) a ON a.job_id = j.id
        ORDER BY j.collected_at DESC, j.id DESC
        """
    ).fetchall()
    return [_analysis_row_to_dict(r) for r in rows]


def get_analysis_dashboard_counts(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    analyzed = conn.execute(
        "SELECT COUNT(DISTINCT job_id) FROM job_analyses"
    ).fetchone()[0]
    return {"total_jobs": total, "analyzed": analyzed, "unanalyzed": max(0, total - analyzed)}


# =============================================================================
# 第2段階: user_profiles / skills / portfolios
# =============================================================================

def _profile_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for key in ("basic_info_json", "preferred_conditions_json", "difficult_conditions_json"):
        field = key.removesuffix("_json")
        try:
            data[field] = json.loads(data[key]) if data[key] else {}
        except (TypeError, json.JSONDecodeError):
            data[field] = {}
    return data


def get_profile(conn: sqlite3.Connection, profile_name: str = "default") -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE profile_name = ?", (profile_name,)
    ).fetchone()
    return _profile_row_to_dict(row)


def update_profile(conn: sqlite3.Connection, profile_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in ("basic_info", "preferred_conditions", "difficult_conditions"):
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    allowed = {
        "display_name", "job_title", "experience_level", "daily_available_hours",
        "basic_info_json", "preferred_conditions_json", "difficult_conditions_json",
    }
    columns = [c for c in data if c in allowed]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", version = version + 1, updated_at = ?"
    values = [data[c] for c in columns] + [now, profile_id]
    conn.execute(f"UPDATE user_profiles SET {set_clause} WHERE id = ?", values)
    logger.info("スキルプロフィールを更新しました: profile_id=%s", profile_id)


def _skill_row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_skills(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM skills WHERE profile_id = ? ORDER BY category, skill_name", (profile_id,)
    ).fetchall()
    return [_skill_row_to_dict(r) for r in rows]


def add_skill(conn: sqlite3.Connection, profile_id: int, data: dict) -> int:
    now = now_jst_str()
    cursor = conn.execute(
        """
        INSERT INTO skills
            (profile_id, category, skill_name, proficiency_level, experience_type,
             years_experience, memo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id, data.get("category"), data["skill_name"], data.get("proficiency_level"),
            data.get("experience_type"), data.get("years_experience"), data.get("memo"), now, now,
        ),
    )
    logger.info("スキルを追加しました: skill_name=%s", data.get("skill_name"))
    return cursor.lastrowid


def update_skill(conn: sqlite3.Connection, skill_id: int, data: dict) -> None:
    now = now_jst_str()
    allowed = {"category", "skill_name", "proficiency_level", "experience_type", "years_experience", "memo"}
    columns = [c for c in data if c in allowed]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, skill_id]
    conn.execute(f"UPDATE skills SET {set_clause} WHERE id = ?", values)


def delete_skill(conn: sqlite3.Connection, skill_id: int) -> None:
    conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    logger.info("スキルを削除しました: skill_id=%s", skill_id)


PORTFOLIO_JSON_LIST_FIELDS = [
    "technologies", "skills", "subcategories", "target_job_categories",
    "design_tools", "technology_keywords",
]
PORTFOLIO_BOOL_FIELDS = ["is_active", "for_development", "for_design", "for_ai_design"]


def _portfolio_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for field in PORTFOLIO_JSON_LIST_FIELDS:
        key = f"{field}_json"
        if key not in data:
            continue
        try:
            data[field] = json.loads(data[key]) if data[key] else []
        except (TypeError, json.JSONDecodeError):
            data[field] = []
    for field in PORTFOLIO_BOOL_FIELDS:
        if field in data:
            data[field] = bool(data[field])
    return data


def list_portfolios(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM portfolios WHERE profile_id = ? ORDER BY display_order, id", (profile_id,)
    ).fetchall()
    return [_portfolio_row_to_dict(r) for r in rows]


def get_portfolio(conn: sqlite3.Connection, portfolio_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
    return _portfolio_row_to_dict(row) if row else None


def get_portfolios_by_ids(conn: sqlite3.Connection, portfolio_ids: Iterable[int]) -> list[dict]:
    ids = list(portfolio_ids)
    if not ids:
        return []
    placeholders = ", ".join(["?"] * len(ids))
    rows = conn.execute(
        f"SELECT * FROM portfolios WHERE id IN ({placeholders})", ids
    ).fetchall()
    return [_portfolio_row_to_dict(r) for r in rows]


def add_portfolio(conn: sqlite3.Connection, profile_id: int, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    for field in PORTFOLIO_JSON_LIST_FIELDS:
        data.setdefault(field, [])
    cursor = conn.execute(
        """
        INSERT INTO portfolios
            (profile_id, title, description, technologies_json, skills_json,
             portfolio_url, github_url, is_active,
             portfolio_type, main_category, subcategories_json, target_job_categories_json,
             design_tools_json, technology_keywords_json, sales_description, priority,
             for_development, for_design, for_ai_design, display_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id, data["title"], data.get("description"),
            json.dumps(data.get("technologies", []), ensure_ascii=False),
            json.dumps(data.get("skills", []), ensure_ascii=False),
            data.get("portfolio_url"), data.get("github_url"),
            int(data.get("is_active", True)),
            data.get("portfolio_type"), data.get("main_category"),
            json.dumps(data.get("subcategories", []), ensure_ascii=False),
            json.dumps(data.get("target_job_categories", []), ensure_ascii=False),
            json.dumps(data.get("design_tools", []), ensure_ascii=False),
            json.dumps(data.get("technology_keywords", []), ensure_ascii=False),
            data.get("sales_description"), int(data.get("priority", 50)),
            int(data.get("for_development", True)), int(data.get("for_design", False)),
            int(data.get("for_ai_design", False)), int(data.get("display_order", 50)),
            now, now,
        ),
    )
    logger.info("制作実績を追加しました: title=%s", data.get("title"))
    return cursor.lastrowid


def update_portfolio(conn: sqlite3.Connection, portfolio_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in PORTFOLIO_JSON_LIST_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in PORTFOLIO_BOOL_FIELDS + ["priority", "display_order"]:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    allowed = {
        "title", "description", "technologies_json", "skills_json", "portfolio_url", "github_url",
        "is_active", "portfolio_type", "main_category", "subcategories_json",
        "target_job_categories_json", "design_tools_json", "technology_keywords_json",
        "sales_description", "priority", "for_development", "for_design", "for_ai_design",
        "display_order",
    }
    columns = [c for c in data if c in allowed]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, portfolio_id]
    conn.execute(f"UPDATE portfolios SET {set_clause} WHERE id = ?", values)


def delete_portfolio(conn: sqlite3.Connection, portfolio_id: int) -> None:
    conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    logger.info("制作実績を削除しました: portfolio_id=%s", portfolio_id)


def get_profile_bundle(conn: sqlite3.Connection, profile_name: str = "default") -> Optional[dict]:
    """プロフィール分析に必要な情報（プロフィール・スキル・制作実績）をまとめて取得する。"""
    profile = get_profile(conn, profile_name)
    if profile is None:
        return None
    return {
        "profile": profile,
        "skills": list_skills(conn, profile["id"]),
        "portfolios": list_portfolios(conn, profile["id"]),
    }


# =============================================================================
# 第2段階: analysis_settings
# =============================================================================

def get_analysis_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute(
        "SELECT setting_value FROM analysis_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row is None:
        return DEFAULT_ANALYSIS_SETTINGS.get(key, default)
    try:
        return json.loads(row["setting_value"])
    except (TypeError, json.JSONDecodeError):
        return row["setting_value"]


def get_all_analysis_settings(conn: sqlite3.Connection) -> dict:
    settings = dict(DEFAULT_ANALYSIS_SETTINGS)
    rows = conn.execute("SELECT setting_key, setting_value FROM analysis_settings").fetchall()
    for row in rows:
        try:
            settings[row["setting_key"]] = json.loads(row["setting_value"])
        except (TypeError, json.JSONDecodeError):
            settings[row["setting_key"]] = row["setting_value"]
    return settings


def save_analysis_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = now_jst_str()
    serialized = json.dumps(value, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id FROM analysis_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE analysis_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (serialized, now, key),
        )
    else:
        conn.execute(
            "INSERT INTO analysis_settings (setting_key, setting_value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, serialized, now, now),
        )
    logger.info("AI分析設定を保存しました: key=%s", key)


# =============================================================================
# 第3段階: portfolio_matches（案件ごとのポートフォリオ関連度・選択状態）
# =============================================================================

def _portfolio_match_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    try:
        data["matched_skills"] = json.loads(data["matched_skills_json"]) if data.get("matched_skills_json") else []
    except (TypeError, json.JSONDecodeError):
        data["matched_skills"] = []
    data["is_selected"] = bool(data.get("is_selected"))
    return data


def save_portfolio_matches(conn: sqlite3.Connection, job_id: int, matches: list[dict]) -> None:
    """案件のポートフォリオ関連度計算結果を保存する（既存の計算結果は置き換える）。"""
    now = now_jst_str()
    conn.execute("DELETE FROM portfolio_matches WHERE job_id = ?", (job_id,))
    for m in matches:
        conn.execute(
            """
            INSERT INTO portfolio_matches
                (job_id, portfolio_id, relevance_score, matched_skills_json, matched_category,
                 match_reason, is_selected, selection_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id, m["portfolio_id"], m.get("relevance_score", 0),
                json.dumps(m.get("matched_skills", []), ensure_ascii=False),
                m.get("matched_category"), m.get("match_reason"),
                int(m.get("is_selected", False)), m.get("selection_order"), now, now,
            ),
        )
    logger.info("ポートフォリオ関連度を計算・保存しました: job_id=%s 件数=%s", job_id, len(matches))


def get_portfolio_matches_for_job(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM portfolio_matches WHERE job_id = ? ORDER BY relevance_score DESC", (job_id,)
    ).fetchall()
    return [_portfolio_match_row_to_dict(r) for r in rows]


def get_selected_portfolio_matches(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM portfolio_matches WHERE job_id = ? AND is_selected = 1 ORDER BY selection_order",
        (job_id,),
    ).fetchall()
    return [_portfolio_match_row_to_dict(r) for r in rows]


def update_portfolio_match_selection(conn: sqlite3.Connection, job_id: int, selected_ids: list[int]) -> None:
    """手動でのポートフォリオ選択（追加・削除・並べ替え）を反映する。"""
    now = now_jst_str()
    conn.execute(
        "UPDATE portfolio_matches SET is_selected = 0, selection_order = NULL, updated_at = ? WHERE job_id = ?",
        (now, job_id),
    )
    for order, portfolio_id in enumerate(selected_ids):
        conn.execute(
            """
            UPDATE portfolio_matches SET is_selected = 1, selection_order = ?, updated_at = ?
            WHERE job_id = ? AND portfolio_id = ?
            """,
            (order, now, job_id, portfolio_id),
        )
    logger.info("ポートフォリオの選択状態を更新しました: job_id=%s selected=%s", job_id, selected_ids)


# =============================================================================
# 第3段階: application_drafts（案件ごとの営業文下書き）
# =============================================================================

APPLICATION_DRAFT_JSON_FIELDS = [
    "questions_for_client", "client_questions", "client_answers",
    "selected_portfolio_ids", "portfolio_reasons", "skills_to_highlight",
    "proposed_approach", "warnings", "missing_information",
]

APPLICATION_DRAFT_COLUMNS = [
    "job_id", "analysis_id", "profile_id", "title", "generation_type", "tone", "length_type",
    "application_message", "short_message", "proposed_price", "minimum_price", "ideal_price",
    "price_reason", "proposed_delivery_days", "minimum_delivery_days", "safe_delivery_days",
    "delivery_reason", "questions_for_client_json", "client_questions_json", "client_answers_json",
    "selected_portfolio_ids_json", "portfolio_reasons_json", "skills_to_highlight_json",
    "proposed_approach_json", "warnings_json", "missing_information_json", "confidence_score",
    "preparation_status", "user_memo", "provider", "model", "prompt_version", "source_hash",
    "copied_at",
]


def _application_draft_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in APPLICATION_DRAFT_JSON_FIELDS:
        key = f"{field}_json"
        if key in data:
            try:
                data[field] = json.loads(data[key]) if data[key] else []
            except (TypeError, json.JSONDecodeError):
                data[field] = []
    return data


def create_application_draft(conn: sqlite3.Connection, job_id: int, data: dict) -> int:
    """営業文の下書きを新規作成する。"""
    now = now_jst_str()
    data = dict(data)
    data["job_id"] = job_id
    data.setdefault("preparation_status", "未作成")

    for field in APPLICATION_DRAFT_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in APPLICATION_DRAFT_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]

    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO application_drafts ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("営業文の下書きを作成しました: job_id=%s draft_id=%s", job_id, cursor.lastrowid)
    return cursor.lastrowid


def update_application_draft(conn: sqlite3.Connection, draft_id: int, data: dict) -> None:
    """既存の営業文下書きを更新する（同一案件の「現在の下書き」を上書きする場合に使用）。"""
    data = dict(data)
    now = now_jst_str()
    for field in APPLICATION_DRAFT_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in APPLICATION_DRAFT_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, draft_id]
    conn.execute(f"UPDATE application_drafts SET {set_clause} WHERE id = ?", values)
    logger.info("営業文の下書きを更新しました: draft_id=%s", draft_id)


def get_application_draft(conn: sqlite3.Connection, draft_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM application_drafts WHERE id = ?", (draft_id,)).fetchone()
    return _application_draft_row_to_dict(row)


def get_current_application_draft(conn: sqlite3.Connection, job_id: int) -> Optional[dict]:
    """指定案件の「現在の」営業文下書き（最新のもの）を取得する。"""
    row = conn.execute(
        "SELECT * FROM application_drafts WHERE job_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    return _application_draft_row_to_dict(row)


def list_application_drafts(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_drafts WHERE job_id = ? ORDER BY created_at DESC, id DESC", (job_id,)
    ).fetchall()
    return [_application_draft_row_to_dict(r) for r in rows]


def mark_application_draft_copied(conn: sqlite3.Connection, draft_id: int) -> None:
    now = now_jst_str()
    conn.execute(
        "UPDATE application_drafts SET copied_at = ?, updated_at = ? WHERE id = ?",
        (now, now, draft_id),
    )
    logger.info("営業文をコピーしました: draft_id=%s", draft_id)


def get_jobs_with_latest_application(conn: sqlite3.Connection) -> list[dict]:
    """全案件に、存在すれば最新の営業文下書きを結合して返す（案件一覧・営業文一覧の表示用）。"""
    rows = conn.execute(
        """
        SELECT j.*,
               d.id AS draft_id, d.title AS application_title, d.generation_type, d.tone,
               d.length_type, d.application_message, d.short_message, d.proposed_price,
               d.proposed_delivery_days, d.preparation_status, d.copied_at,
               d.selected_portfolio_ids_json, d.created_at AS draft_created_at,
               d.updated_at AS draft_updated_at
        FROM jobs j
        LEFT JOIN (
            SELECT d1.* FROM application_drafts d1
            WHERE d1.id = (
                SELECT d2.id FROM application_drafts d2
                WHERE d2.job_id = d1.job_id
                ORDER BY d2.created_at DESC, d2.id DESC LIMIT 1
            )
        ) d ON d.job_id = j.id
        ORDER BY j.collected_at DESC, j.id DESC
        """
    ).fetchall()
    results = []
    for row in rows:
        data = dict(row)
        try:
            data["selected_portfolio_ids"] = (
                json.loads(data["selected_portfolio_ids_json"]) if data.get("selected_portfolio_ids_json") else []
            )
        except (TypeError, json.JSONDecodeError):
            data["selected_portfolio_ids"] = []
        results.append(data)
    return results


# =============================================================================
# 第3段階: application_versions（営業文の編集履歴）
# =============================================================================

def add_application_version(
    conn: sqlite3.Connection,
    draft_id: int,
    application_message: str,
    short_message: str | None = None,
    version_type: str = "generated",
    change_instruction: str | None = None,
    created_by: str = "system",
) -> int:
    """営業文の状態を1バージョンとして記録する（編集・再生成のたびに直前の状態を保存する）。"""
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM application_versions WHERE application_draft_id = ?", (draft_id,)
    ).fetchone()[0]
    cursor = conn.execute(
        """
        INSERT INTO application_versions
            (application_draft_id, version_number, version_type, application_message,
             short_message, change_instruction, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft_id, existing_count + 1, version_type, application_message,
            short_message, change_instruction, created_by, now_jst_str(),
        ),
    )
    logger.info("営業文のバージョンを記録しました: draft_id=%s version=%s", draft_id, existing_count + 1)
    return cursor.lastrowid


def list_application_versions(conn: sqlite3.Connection, draft_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_versions WHERE application_draft_id = ? ORDER BY version_number DESC",
        (draft_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_application_version(conn: sqlite3.Connection, version_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM application_versions WHERE id = ?", (version_id,)).fetchone()
    return dict(row) if row else None


# =============================================================================
# 第3段階: application_templates（AI APIなしでの営業文テンプレート）
# =============================================================================

def list_application_templates(conn: sqlite3.Connection, category: str | None = None) -> list[dict]:
    if category:
        rows = conn.execute(
            "SELECT * FROM application_templates WHERE category = ? AND is_active = 1 ORDER BY id",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM application_templates WHERE is_active = 1 ORDER BY category, id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_application_template(conn: sqlite3.Connection, template_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM application_templates WHERE id = ?", (template_id,)).fetchone()
    return dict(row) if row else None


def add_application_template(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    cursor = conn.execute(
        """
        INSERT INTO application_templates
            (template_name, category, tone, length_type, template_body, is_default, is_active,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["template_name"], data.get("category"), data.get("tone"), data.get("length_type"),
            data.get("template_body"), int(data.get("is_default", False)), int(data.get("is_active", True)),
            now, now,
        ),
    )
    logger.info("営業文テンプレートを追加しました: template_name=%s", data.get("template_name"))
    return cursor.lastrowid


def update_application_template(conn: sqlite3.Connection, template_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in ("is_default", "is_active"):
        if field in data:
            data[field] = int(data[field])
    allowed = {"template_name", "category", "tone", "length_type", "template_body", "is_default", "is_active"}
    columns = [c for c in data if c in allowed]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, template_id]
    conn.execute(f"UPDATE application_templates SET {set_clause} WHERE id = ?", values)


# =============================================================================
# 第3段階: pricing_settings（応募金額・納期提案の設定）
# =============================================================================

def get_pricing_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute(
        "SELECT setting_value FROM pricing_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["setting_value"])
    except (TypeError, json.JSONDecodeError):
        return row["setting_value"]


def get_all_pricing_settings(conn: sqlite3.Connection) -> dict:
    settings: dict = {}
    rows = conn.execute("SELECT setting_key, setting_value FROM pricing_settings").fetchall()
    for row in rows:
        try:
            settings[row["setting_key"]] = json.loads(row["setting_value"])
        except (TypeError, json.JSONDecodeError):
            settings[row["setting_key"]] = row["setting_value"]
    return settings


def save_pricing_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = now_jst_str()
    serialized = json.dumps(value, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id FROM pricing_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE pricing_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (serialized, now, key),
        )
    else:
        conn.execute(
            "INSERT INTO pricing_settings (setting_key, setting_value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, serialized, now, now),
        )
    logger.info("料金・納期設定を保存しました: key=%s", key)


# =============================================================================
# 第3段階: application_checklists（応募前確認チェックリスト）
# =============================================================================

_CHECKLIST_FIELDS = [
    "job_reviewed", "conditions_confirmed", "price_confirmed", "deadline_confirmed",
    "message_confirmed", "portfolio_confirmed", "client_questions_answered", "safety_confirmed",
]


def get_application_checklist(conn: sqlite3.Connection, draft_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM application_checklists WHERE application_draft_id = ?", (draft_id,)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    for field in _CHECKLIST_FIELDS:
        data[field] = bool(data.get(field))
    return data


def save_application_checklist(conn: sqlite3.Connection, draft_id: int, data: dict) -> None:
    """応募前確認チェックリストを保存する（存在しなければ作成する）。"""
    now = now_jst_str()
    values = {field: int(bool(data.get(field, False))) for field in _CHECKLIST_FIELDS}
    all_checked = all(values.values())
    completed_at = now if all_checked else None

    existing = conn.execute(
        "SELECT id FROM application_checklists WHERE application_draft_id = ?", (draft_id,)
    ).fetchone()
    if existing:
        set_clause = ", ".join(f"{f} = ?" for f in _CHECKLIST_FIELDS)
        conn.execute(
            f"UPDATE application_checklists SET {set_clause}, completed_at = ?, updated_at = ? "
            f"WHERE application_draft_id = ?",
            [*values.values(), completed_at, now, draft_id],
        )
    else:
        columns = ", ".join(_CHECKLIST_FIELDS)
        placeholders = ", ".join(["?"] * len(_CHECKLIST_FIELDS))
        conn.execute(
            f"INSERT INTO application_checklists "
            f"(application_draft_id, {columns}, completed_at, updated_at) "
            f"VALUES (?, {placeholders}, ?, ?)",
            [draft_id, *values.values(), completed_at, now],
        )
    logger.info("応募前確認チェックリストを保存しました: draft_id=%s 完了=%s", draft_id, all_checked)


# =============================================================================
# 第4段階Part1: daily_application_goals（1日あたりの応募目標）
# =============================================================================

_DAILY_GOAL_JSON_FIELDS = ["allowed_risk_levels", "score_weights"]
_DAILY_GOAL_BOOL_FIELDS = ["prioritize_verified_client", "prioritize_ready_drafts", "prioritize_application_written"]
_DAILY_GOAL_COLUMNS = [
    "target_date", "target_count", "maximum_count", "ai_development_target", "design_target",
    "other_target", "minimum_total_score", "minimum_ai_score", "minimum_safety_score",
    "allowed_risk_levels_json", "new_arrival_hours", "maximum_applicant_count", "minimum_client_rating",
    "prioritize_verified_client", "prioritize_ready_drafts", "prioritize_application_written",
    "score_weights_json",
]


def _daily_goal_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in _DAILY_GOAL_JSON_FIELDS:
        key = f"{field}_json"
        if key in data:
            try:
                data[field] = json.loads(data[key]) if data[key] else ({} if field == "score_weights" else [])
            except (TypeError, json.JSONDecodeError):
                data[field] = {} if field == "score_weights" else []
    for field in _DAILY_GOAL_BOOL_FIELDS:
        if field in data:
            data[field] = bool(data[field])
    return data


def get_daily_goal(conn: sqlite3.Connection, target_date: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM daily_application_goals WHERE target_date = ?", (target_date,)
    ).fetchone()
    return _daily_goal_row_to_dict(row)


def list_daily_goals(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM daily_application_goals ORDER BY target_date DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_daily_goal_row_to_dict(r) for r in rows]


def create_daily_goal(conn: sqlite3.Connection, target_date: str, data: dict) -> int:
    """指定日の応募目標を新規作成する（target_dateは重複不可）。"""
    now = now_jst_str()
    data = dict(data)
    data["target_date"] = target_date
    for field in _DAILY_GOAL_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _DAILY_GOAL_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    columns = [c for c in _DAILY_GOAL_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]

    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO daily_application_goals ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("日次応募目標を作成しました: target_date=%s", target_date)
    return cursor.lastrowid


def update_daily_goal(conn: sqlite3.Connection, target_date: str, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _DAILY_GOAL_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _DAILY_GOAL_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    columns = [c for c in _DAILY_GOAL_COLUMNS if c in data and c != "target_date"]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, target_date]
    conn.execute(f"UPDATE daily_application_goals SET {set_clause} WHERE target_date = ?", values)
    logger.info("日次応募目標を更新しました: target_date=%s", target_date)


# =============================================================================
# 第4段階Part1: daily_selection_settings（応募目標の既定値・デイリー優先スコアの重み）
# =============================================================================

def get_daily_selection_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute(
        "SELECT setting_value FROM daily_selection_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["setting_value"])
    except (TypeError, json.JSONDecodeError):
        return row["setting_value"]


def get_all_daily_selection_settings(conn: sqlite3.Connection) -> dict:
    settings: dict = {}
    rows = conn.execute("SELECT setting_key, setting_value FROM daily_selection_settings").fetchall()
    for row in rows:
        try:
            settings[row["setting_key"]] = json.loads(row["setting_value"])
        except (TypeError, json.JSONDecodeError):
            settings[row["setting_key"]] = row["setting_value"]
    return settings


def save_daily_selection_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = now_jst_str()
    serialized = json.dumps(value, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id FROM daily_selection_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE daily_selection_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (serialized, now, key),
        )
    else:
        conn.execute(
            "INSERT INTO daily_selection_settings (setting_key, setting_value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, serialized, now, now),
        )
    logger.info("応募目標の既定値・スコア設定を保存しました: key=%s", key)


# =============================================================================
# 第4段階Part1: daily_candidates（本日の応募候補）
# =============================================================================

_DAILY_CANDIDATE_JSON_FIELDS = ["selection_reasons", "exclusion_reasons"]
_DAILY_CANDIDATE_BOOL_FIELDS = ["is_manually_added", "is_manually_removed"]
_DAILY_CANDIDATE_COLUMNS = [
    "target_date", "job_id", "application_draft_id", "category_group", "daily_priority_score",
    "rank_number", "selection_reasons_json", "exclusion_reasons_json", "candidate_status",
    "is_manually_added", "is_manually_removed", "postponed_until", "user_memo",
]


def _daily_candidate_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in _DAILY_CANDIDATE_JSON_FIELDS:
        key = f"{field}_json"
        if key in data:
            try:
                data[field] = json.loads(data[key]) if data[key] else []
            except (TypeError, json.JSONDecodeError):
                data[field] = []
    for field in _DAILY_CANDIDATE_BOOL_FIELDS:
        if field in data:
            data[field] = bool(data[field])
    return data


def get_daily_candidates(conn: sqlite3.Connection, target_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT dc.*, j.title AS job_title, j.url AS job_url, j.category AS job_category,
               j.budget_min, j.budget_max, j.budget_text, j.applicant_count, j.deadline,
               j.published_at, j.collected_at, j.client_rating, j.identity_verified,
               j.status AS job_status,
               d.preparation_status, d.generation_type, d.application_message, d.short_message,
               d.proposed_price AS draft_proposed_price,
               d.proposed_delivery_days AS draft_proposed_delivery_days,
               d.selected_portfolio_ids_json
        FROM daily_candidates dc
        JOIN jobs j ON j.id = dc.job_id
        LEFT JOIN application_drafts d ON d.id = dc.application_draft_id
        WHERE dc.target_date = ?
        ORDER BY (dc.rank_number IS NULL), dc.rank_number, dc.daily_priority_score DESC
        """,
        (target_date,),
    ).fetchall()
    results = []
    for row in rows:
        data = _daily_candidate_row_to_dict(row)
        try:
            data["selected_portfolio_ids"] = (
                json.loads(data["selected_portfolio_ids_json"]) if data.get("selected_portfolio_ids_json") else []
            )
        except (TypeError, json.JSONDecodeError):
            data["selected_portfolio_ids"] = []
        results.append(data)
    return results


def get_daily_candidate(conn: sqlite3.Connection, candidate_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM daily_candidates WHERE id = ?", (candidate_id,)).fetchone()
    return _daily_candidate_row_to_dict(row)


def get_daily_candidate_by_job(conn: sqlite3.Connection, target_date: str, job_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM daily_candidates WHERE target_date = ? AND job_id = ?", (target_date, job_id),
    ).fetchone()
    return _daily_candidate_row_to_dict(row)


def upsert_daily_candidate(conn: sqlite3.Connection, target_date: str, job_id: int, data: dict) -> int:
    """本日の候補を1件登録・更新する（target_date, job_idの組で一意）。"""
    now = now_jst_str()
    data = dict(data)
    for field in _DAILY_CANDIDATE_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _DAILY_CANDIDATE_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    existing = conn.execute(
        "SELECT id FROM daily_candidates WHERE target_date = ? AND job_id = ?", (target_date, job_id),
    ).fetchone()

    if existing:
        columns = [c for c in _DAILY_CANDIDATE_COLUMNS if c in data and c not in ("target_date", "job_id")]
        if columns:
            set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
            values = [data[c] for c in columns] + [now, existing["id"]]
            conn.execute(f"UPDATE daily_candidates SET {set_clause} WHERE id = ?", values)
        return existing["id"]

    data["target_date"] = target_date
    data["job_id"] = job_id
    columns = [c for c in _DAILY_CANDIDATE_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["selected_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO daily_candidates ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    return cursor.lastrowid


def update_daily_candidate(conn: sqlite3.Connection, candidate_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _DAILY_CANDIDATE_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _DAILY_CANDIDATE_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    columns = [c for c in _DAILY_CANDIDATE_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, candidate_id]
    conn.execute(f"UPDATE daily_candidates SET {set_clause} WHERE id = ?", values)


def delete_stale_daily_candidates(conn: sqlite3.Connection, target_date: str) -> int:
    """再選定時に、アルゴリズムによる行（候補・対象外）のみを入れ替える。

    手動追加・保留・見送り・除外・応募済みなど、ユーザーが明示的に操作した行は保持する。
    """
    cursor = conn.execute(
        """
        DELETE FROM daily_candidates
        WHERE target_date = ? AND is_manually_added = 0
          AND candidate_status IN ('候補', '対象外')
        """,
        (target_date,),
    )
    return cursor.rowcount


def get_active_postponement(conn: sqlite3.Connection, job_id: int, target_date: str) -> Optional[str]:
    """指定案件について、target_date時点でまだ有効な保留期限があれば返す（無ければNone）。"""
    row = conn.execute(
        """
        SELECT postponed_until FROM daily_candidates
        WHERE job_id = ? AND candidate_status = '保留' AND postponed_until IS NOT NULL
        ORDER BY postponed_until DESC LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if row and row["postponed_until"] and row["postponed_until"] > target_date:
        return row["postponed_until"]
    return None


# =============================================================================
# 第4段階Part1: application_records（簡易応募記録）
# 第4段階Part2: 正式な応募履歴（スナップショット・応募後ステータス・応募経路 等へ拡張）
# =============================================================================

_APPLICATION_RECORD_COLUMNS = [
    "job_id", "application_draft_id", "application_version_id", "source_platform", "applied_at",
    "contract_type", "proposed_price", "tax_type", "proposed_delivery_days", "proposed_delivery_date",
    "sent_message", "sent_short_message", "generation_type", "tone",
    "portfolio_snapshot_json", "portfolio_urls_json", "total_score_snapshot", "ai_score_snapshot",
    "safety_score_snapshot", "daily_priority_score_snapshot", "applicant_count_snapshot",
    "client_snapshot_json", "job_snapshot_json", "application_status", "current_response_status",
    "next_action", "next_action_due_at", "is_over_limit", "over_limit_reason", "user_memo",
    "is_active", "is_reapplication", "reapplication_reason",
]

_APPLICATION_RECORD_JSON_FIELDS = [
    "portfolio_snapshot", "portfolio_urls", "client_snapshot", "job_snapshot",
]
_APPLICATION_RECORD_BOOL_FIELDS = ["is_over_limit", "is_active", "is_reapplication"]


def _application_record_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in _APPLICATION_RECORD_JSON_FIELDS:
        key = f"{field}_json"
        if key in data:
            try:
                data[field] = json.loads(data[key]) if data[key] else ([] if field in ("portfolio_snapshot", "portfolio_urls") else {})
            except (TypeError, json.JSONDecodeError):
                data[field] = [] if field in ("portfolio_snapshot", "portfolio_urls") else {}
    for field in _APPLICATION_RECORD_BOOL_FIELDS:
        if field in data:
            data[field] = bool(data[field])
    return data


def create_application_record(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    data.setdefault("applied_at", now)
    data.setdefault("application_status", "応募済み")
    data.setdefault("source_platform", "クラウドワークス")

    for field in _APPLICATION_RECORD_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _APPLICATION_RECORD_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    columns = [c for c in _APPLICATION_RECORD_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO application_records ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("応募を記録しました: job_id=%s", data.get("job_id"))
    return cursor.lastrowid


def update_application_record(conn: sqlite3.Connection, record_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _APPLICATION_RECORD_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    for field in _APPLICATION_RECORD_BOOL_FIELDS:
        if field in data and data[field] is not None:
            data[field] = int(data[field])

    columns = [c for c in _APPLICATION_RECORD_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, record_id]
    conn.execute(f"UPDATE application_records SET {set_clause} WHERE id = ?", values)
    logger.info("応募履歴を更新しました: record_id=%s", record_id)


def get_application_record(conn: sqlite3.Connection, record_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM application_records WHERE id = ?", (record_id,)).fetchone()
    return _application_record_row_to_dict(row)


def get_application_records_for_date(conn: sqlite3.Connection, target_date: str) -> list[dict]:
    """日本時間の応募日時をもとに、指定日の応募記録を取得する。"""
    rows = conn.execute(
        "SELECT * FROM application_records WHERE substr(applied_at, 1, 10) = ? ORDER BY applied_at",
        (target_date,),
    ).fetchall()
    return [_application_record_row_to_dict(r) for r in rows]


def count_applications_for_date(conn: sqlite3.Connection, target_date: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM application_records WHERE substr(applied_at, 1, 10) = ?", (target_date,),
    ).fetchone()[0]


def list_application_records_for_job(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_records WHERE job_id = ? ORDER BY applied_at DESC", (job_id,),
    ).fetchall()
    return [_application_record_row_to_dict(r) for r in rows]


def count_active_application_records_for_job(conn: sqlite3.Connection, job_id: int) -> int:
    """重複応募検知に使用する: 有効な（無効化されていない）応募履歴の件数。"""
    return conn.execute(
        "SELECT COUNT(*) FROM application_records WHERE job_id = ? AND is_active = 1", (job_id,),
    ).fetchone()[0]


def deactivate_application_record(conn: sqlite3.Connection, record_id: int) -> None:
    """応募記録を無効化する（要件16: 削除は原則行わず無効化方式にする）。"""
    conn.execute(
        "UPDATE application_records SET is_active = 0, updated_at = ? WHERE id = ?",
        (now_jst_str(), record_id),
    )
    logger.info("応募履歴を無効化しました: record_id=%s", record_id)


def list_application_history(conn: sqlite3.Connection) -> list[dict]:
    """応募履歴一覧画面用に、案件情報と結合した全応募履歴（有効なもの）を返す。"""
    rows = conn.execute(
        """
        SELECT r.*, j.title AS job_title, j.url AS job_url, j.category AS job_category,
               j.client_name AS job_client_name
        FROM application_records r
        JOIN jobs j ON j.id = r.job_id
        WHERE r.is_active = 1
        ORDER BY r.applied_at DESC
        """
    ).fetchall()
    return [_application_record_row_to_dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: application_status_history（応募後ステータス変更履歴）
# =============================================================================

def add_status_history(
    conn: sqlite3.Connection, application_record_id: int, previous_status: str | None,
    new_status: str, change_reason: str | None = None, memo: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO application_status_history
            (application_record_id, previous_status, new_status, changed_at, change_reason, memo)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (application_record_id, previous_status, new_status, now_jst_str(), change_reason, memo),
    )
    return cursor.lastrowid


def list_status_history(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_status_history WHERE application_record_id = ? ORDER BY changed_at, id",
        (application_record_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: client_responses（クライアント返信管理）
# =============================================================================

_CLIENT_RESPONSE_JSON_FIELDS = ["questions"]
_CLIENT_RESPONSE_COLUMNS = [
    "application_record_id", "received_at", "response_type", "response_body", "response_summary",
    "questions_json", "response_due_at", "urgency", "next_action", "answer_body", "answered_at",
    "response_status", "memo",
]


def _client_response_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    try:
        data["questions"] = json.loads(data["questions_json"]) if data.get("questions_json") else []
    except (TypeError, json.JSONDecodeError):
        data["questions"] = []
    return data


def create_client_response(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    data.setdefault("received_at", now)
    data.setdefault("response_status", "未対応")
    for field in _CLIENT_RESPONSE_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in _CLIENT_RESPONSE_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO client_responses ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("クライアント返信を登録しました: application_record_id=%s", data.get("application_record_id"))
    return cursor.lastrowid


def update_client_response(conn: sqlite3.Connection, response_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _CLIENT_RESPONSE_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    columns = [c for c in _CLIENT_RESPONSE_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, response_id]
    conn.execute(f"UPDATE client_responses SET {set_clause} WHERE id = ?", values)
    logger.info("クライアント返信を更新しました: response_id=%s", response_id)


def get_client_response(conn: sqlite3.Connection, response_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM client_responses WHERE id = ?", (response_id,)).fetchone()
    return _client_response_row_to_dict(row)


def list_client_responses(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM client_responses WHERE application_record_id = ? ORDER BY received_at DESC",
        (application_record_id,),
    ).fetchall()
    return [_client_response_row_to_dict(r) for r in rows]


def list_all_client_responses(conn: sqlite3.Connection) -> list[dict]:
    """出力・分析用: 全返信履歴を案件情報と結合して返す。"""
    rows = conn.execute(
        """
        SELECT cr.*, r.job_id, r.applied_at, j.title AS job_title
        FROM client_responses cr
        JOIN application_records r ON r.id = cr.application_record_id
        JOIN jobs j ON j.id = r.job_id
        ORDER BY cr.received_at
        """
    ).fetchall()
    return [_client_response_row_to_dict(r) for r in rows]


def list_client_responses_by_status(conn: sqlite3.Connection, statuses: list[str]) -> list[dict]:
    """返信管理画面用: 指定した対応状況の返信を、案件情報と結合して返す。"""
    placeholders = ", ".join(["?"] * len(statuses))
    rows = conn.execute(
        f"""
        SELECT cr.*, r.job_id, j.title AS job_title
        FROM client_responses cr
        JOIN application_records r ON r.id = cr.application_record_id
        JOIN jobs j ON j.id = r.job_id
        WHERE cr.response_status IN ({placeholders})
        ORDER BY cr.response_due_at IS NULL, cr.response_due_at
        """,
        statuses,
    ).fetchall()
    return [_client_response_row_to_dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: interviews（面談管理）
# =============================================================================

_INTERVIEW_JSON_FIELDS = ["questions"]
_INTERVIEW_COLUMNS = [
    "application_record_id", "title", "scheduled_start", "scheduled_end", "timezone", "meeting_type",
    "meeting_url", "contact_name", "preparation_notes", "questions_json", "self_intro_notes",
    "proposal_notes", "result", "next_step", "next_contact_due_at", "interview_notes", "status",
]


def _interview_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    try:
        data["questions"] = json.loads(data["questions_json"]) if data.get("questions_json") else []
    except (TypeError, json.JSONDecodeError):
        data["questions"] = []
    return data


def create_interview(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    data.setdefault("status", "調整中")
    data.setdefault("timezone", "Asia/Tokyo")
    for field in _INTERVIEW_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in _INTERVIEW_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO interviews ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("面談を作成しました: application_record_id=%s", data.get("application_record_id"))
    return cursor.lastrowid


def update_interview(conn: sqlite3.Connection, interview_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _INTERVIEW_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    columns = [c for c in _INTERVIEW_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, interview_id]
    conn.execute(f"UPDATE interviews SET {set_clause} WHERE id = ?", values)
    logger.info("面談を更新しました: interview_id=%s", interview_id)


def get_interview(conn: sqlite3.Connection, interview_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
    return _interview_row_to_dict(row)


def list_interviews(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM interviews WHERE application_record_id = ? ORDER BY scheduled_start DESC",
        (application_record_id,),
    ).fetchall()
    return [_interview_row_to_dict(r) for r in rows]


def list_interviews_with_job(conn: sqlite3.Connection) -> list[dict]:
    """面談管理画面用: 全面談を案件情報と結合して返す。"""
    rows = conn.execute(
        """
        SELECT i.*, r.job_id, j.title AS job_title
        FROM interviews i
        JOIN application_records r ON r.id = i.application_record_id
        JOIN jobs j ON j.id = r.job_id
        ORDER BY i.scheduled_start
        """
    ).fetchall()
    return [_interview_row_to_dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: negotiation_records（条件相談管理）
# =============================================================================

_NEGOTIATION_JSON_FIELDS = ["deliverables", "additional_work"]
_NEGOTIATION_COLUMNS = [
    "application_record_id", "original_price", "client_offered_price", "agreed_price",
    "original_delivery_date", "requested_delivery_date", "agreed_delivery_date", "revision_count",
    "deliverables_json", "payment_terms", "external_cost_terms", "maintenance_terms",
    "additional_work_json", "agreement_status", "memo",
]


def _negotiation_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for field in _NEGOTIATION_JSON_FIELDS:
        key = f"{field}_json"
        try:
            data[field] = json.loads(data[key]) if data.get(key) else []
        except (TypeError, json.JSONDecodeError):
            data[field] = []
    return data


def create_negotiation_record(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    data.setdefault("agreement_status", "未確認")
    for field in _NEGOTIATION_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in _NEGOTIATION_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO negotiation_records ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("条件相談を作成しました: application_record_id=%s", data.get("application_record_id"))
    return cursor.lastrowid


def update_negotiation_record(conn: sqlite3.Connection, negotiation_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    for field in _NEGOTIATION_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)
    columns = [c for c in _NEGOTIATION_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, negotiation_id]
    conn.execute(f"UPDATE negotiation_records SET {set_clause} WHERE id = ?", values)
    logger.info("条件相談を更新しました: negotiation_id=%s", negotiation_id)


def get_negotiation_record(conn: sqlite3.Connection, application_record_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM negotiation_records WHERE application_record_id = ? ORDER BY id DESC LIMIT 1",
        (application_record_id,),
    ).fetchone()
    return _negotiation_row_to_dict(row)


# =============================================================================
# 第4段階Part2: application_results（採用・不採用・辞退の結果管理）
# =============================================================================

_RESULT_JSON_FIELDS = ["improvement_points"]
_RESULT_COLUMNS = [
    "application_record_id", "result_type", "result_date", "hired_at", "contracted_at",
    "contract_amount", "contract_type", "contract_start_date", "contract_end_date",
    "planned_delivery_date", "actual_delivery_date", "client_reason", "inferred_reason",
    "improvement_points_json", "client_comment", "continuation_possible", "is_recurring",
    "withdrawal_reason", "memo",
]


def _result_row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    try:
        data["improvement_points"] = json.loads(data["improvement_points_json"]) if data.get("improvement_points_json") else []
    except (TypeError, json.JSONDecodeError):
        data["improvement_points"] = []
    data["is_recurring"] = bool(data.get("is_recurring"))
    return data


def create_application_result(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    if "is_recurring" in data and data["is_recurring"] is not None:
        data["is_recurring"] = int(data["is_recurring"])
    for field in _RESULT_JSON_FIELDS:
        if field in data:
            data[f"{field}_json"] = json.dumps(data.pop(field), ensure_ascii=False)

    columns = [c for c in _RESULT_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO application_results ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("応募結果を記録しました: application_record_id=%s result_type=%s", data.get("application_record_id"), data.get("result_type"))
    return cursor.lastrowid


def get_latest_application_result(conn: sqlite3.Connection, application_record_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM application_results WHERE application_record_id = ? ORDER BY id DESC LIMIT 1",
        (application_record_id,),
    ).fetchone()
    return _result_row_to_dict(row)


def list_application_results(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_results WHERE application_record_id = ? ORDER BY id DESC",
        (application_record_id,),
    ).fetchall()
    return [_result_row_to_dict(r) for r in rows]


def list_all_application_results(conn: sqlite3.Connection) -> list[dict]:
    """出力・分析用: 全採用・不採用・辞退結果を案件情報と結合して返す。"""
    rows = conn.execute(
        """
        SELECT res.*, r.job_id, r.applied_at, j.title AS job_title
        FROM application_results res
        JOIN application_records r ON r.id = res.application_record_id
        JOIN jobs j ON j.id = r.job_id
        ORDER BY res.id
        """
    ).fetchall()
    return [_result_row_to_dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: follow_up_tasks（フォローアップ管理）
# =============================================================================

_FOLLOW_UP_COLUMNS = [
    "application_record_id", "due_at", "task_type", "task_content", "status", "completed_at", "memo",
]


def create_follow_up_task(conn: sqlite3.Connection, data: dict) -> int:
    now = now_jst_str()
    data = dict(data)
    data.setdefault("status", "未対応")
    columns = [c for c in _FOLLOW_UP_COLUMNS if c in data]
    values = [data[c] for c in columns]
    columns += ["created_at", "updated_at"]
    values += [now, now]
    placeholders = ", ".join(["?"] * len(columns))
    cursor = conn.execute(
        f"INSERT INTO follow_up_tasks ({', '.join(columns)}) VALUES ({placeholders})", values,
    )
    logger.info("フォローアップを作成しました: application_record_id=%s", data.get("application_record_id"))
    return cursor.lastrowid


def update_follow_up_task(conn: sqlite3.Connection, task_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    columns = [c for c in _FOLLOW_UP_COLUMNS if c in data]
    if not columns:
        return
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [data[c] for c in columns] + [now, task_id]
    conn.execute(f"UPDATE follow_up_tasks SET {set_clause} WHERE id = ?", values)


def get_follow_up_task(conn: sqlite3.Connection, task_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM follow_up_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def list_follow_up_tasks(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM follow_up_tasks WHERE application_record_id = ? ORDER BY due_at",
        (application_record_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_all_follow_up_tasks(conn: sqlite3.Connection) -> list[dict]:
    """フォローアップ画面用: 全タスクを案件情報と結合して返す。"""
    rows = conn.execute(
        """
        SELECT f.*, r.job_id, j.title AS job_title
        FROM follow_up_tasks f
        JOIN application_records r ON r.id = f.application_record_id
        JOIN jobs j ON j.id = r.job_id
        ORDER BY f.due_at
        """
    ).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# 第4段階Part2: application_timeline（応募案件タイムライン）
# =============================================================================

def add_timeline_event(
    conn: sqlite3.Connection, application_record_id: int, event_type: str, event_title: str | None = None,
    event_detail: str | None = None, related_table: str | None = None, related_id: int | None = None,
    event_at: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO application_timeline
            (application_record_id, event_type, event_at, event_title, event_detail,
             related_table, related_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_record_id, event_type, event_at or now_jst_str(), event_title, event_detail,
            related_table, related_id, now_jst_str(),
        ),
    )
    return cursor.lastrowid


def list_timeline(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM application_timeline WHERE application_record_id = ? ORDER BY event_at, id",
        (application_record_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# 第4段階Part3: 営業成績分析用の集計データ取得
# =============================================================================

_ANALYTICS_JSON_LIST_FIELDS = ["portfolio_snapshot", "portfolio_urls"]
_ANALYTICS_JSON_DICT_FIELDS = ["client_snapshot", "job_snapshot"]


def list_application_analytics_base(conn: sqlite3.Connection) -> list[dict]:
    """営業成績分析の基礎となる、応募履歴1件ごとの集約データを返す（有効な応募のみ）。

    返信・面談は応募単位のユニーク件数（response_count/interview_count）で数えられるよう、
    件数と最初の発生日時をあらかじめ集約して1行にまとめる。
    """
    rows = conn.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM client_responses cr WHERE cr.application_record_id = r.id) AS response_count,
               (SELECT MIN(cr2.received_at) FROM client_responses cr2 WHERE cr2.application_record_id = r.id) AS first_response_at,
               (SELECT COUNT(*) FROM interviews iv WHERE iv.application_record_id = r.id) AS interview_count,
               (SELECT MIN(iv2.scheduled_start) FROM interviews iv2 WHERE iv2.application_record_id = r.id) AS first_interview_at,
               res.result_type, res.result_date, res.hired_at, res.contract_amount,
               res.contract_type AS result_contract_type, res.client_reason, res.inferred_reason,
               res.improvement_points_json AS result_improvement_points_json, res.withdrawal_reason,
               res.is_recurring AS result_is_recurring
        FROM application_records r
        LEFT JOIN (
            SELECT ar1.* FROM application_results ar1
            WHERE ar1.id = (
                SELECT ar2.id FROM application_results ar2
                WHERE ar2.application_record_id = ar1.application_record_id
                ORDER BY ar2.id DESC LIMIT 1
            )
        ) res ON res.application_record_id = r.id
        WHERE r.is_active = 1
        ORDER BY r.applied_at
        """
    ).fetchall()

    results = []
    for row in rows:
        data = dict(row)
        for field in _ANALYTICS_JSON_LIST_FIELDS:
            key = f"{field}_json"
            try:
                data[field] = json.loads(data[key]) if data.get(key) else []
            except (TypeError, json.JSONDecodeError):
                data[field] = []
        for field in _ANALYTICS_JSON_DICT_FIELDS:
            key = f"{field}_json"
            try:
                data[field] = json.loads(data[key]) if data.get(key) else {}
            except (TypeError, json.JSONDecodeError):
                data[field] = {}
        try:
            data["improvement_points"] = (
                json.loads(data["result_improvement_points_json"]) if data.get("result_improvement_points_json") else []
            )
        except (TypeError, json.JSONDecodeError):
            data["improvement_points"] = []
        data["is_active"] = bool(data.get("is_active"))
        data["is_reapplication"] = bool(data.get("is_reapplication"))
        results.append(data)
    return results


def get_daily_application_counts(conn: sqlite3.Connection) -> dict:
    """日付(YYYY-MM-DD)ごとの応募数を返す。"""
    rows = conn.execute(
        "SELECT substr(applied_at, 1, 10) AS d, COUNT(*) AS c FROM application_records WHERE is_active = 1 GROUP BY d"
    ).fetchall()
    return {r["d"]: r["c"] for r in rows}


def get_portfolio_average_relevance(conn: sqlite3.Connection) -> dict:
    """ポートフォリオIDごとの平均関連度スコア（選択されたもののみ）を返す。"""
    rows = conn.execute(
        "SELECT portfolio_id, AVG(relevance_score) AS avg_score FROM portfolio_matches "
        "WHERE is_selected = 1 GROUP BY portfolio_id"
    ).fetchall()
    return {r["portfolio_id"]: round(r["avg_score"], 1) for r in rows if r["avg_score"] is not None}


def count_jobs_collected_in_range(conn: sqlite3.Connection, date_from: str, date_to: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE substr(collected_at, 1, 10) BETWEEN ? AND ?", (date_from, date_to),
    ).fetchone()[0]


def count_jobs_analyzed_in_range(conn: sqlite3.Connection, date_from: str, date_to: str) -> int:
    return conn.execute(
        "SELECT COUNT(DISTINCT job_id) FROM job_analyses WHERE substr(created_at, 1, 10) BETWEEN ? AND ?",
        (date_from, date_to),
    ).fetchone()[0]


def count_candidates_in_range(conn: sqlite3.Connection, date_from: str, date_to: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM daily_candidates WHERE target_date BETWEEN ? AND ? AND candidate_status = '候補'",
        (date_from, date_to),
    ).fetchone()[0]


def count_drafts_created_in_range(conn: sqlite3.Connection, date_from: str, date_to: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM application_drafts WHERE substr(created_at, 1, 10) BETWEEN ? AND ?",
        (date_from, date_to),
    ).fetchone()[0]


def count_drafts_ready_in_range(conn: sqlite3.Connection, date_from: str, date_to: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM application_drafts WHERE preparation_status = '応募準備完了' "
        "AND substr(updated_at, 1, 10) BETWEEN ? AND ?",
        (date_from, date_to),
    ).fetchone()[0]


def list_jobs_with_analysis_for_scoring(conn: sqlite3.Connection) -> list[dict]:
    """スコア帯別分析用: 分析済みの全案件（最新の分析結果付き）を返す。"""
    rows = conn.execute(
        """
        SELECT j.id AS job_id, a.total_score, a.ai_suitability_score, a.safety_score
        FROM jobs j
        JOIN (
            SELECT ja1.* FROM job_analyses ja1
            WHERE ja1.id = (
                SELECT ja2.id FROM job_analyses ja2
                WHERE ja2.job_id = ja1.job_id ORDER BY ja2.created_at DESC, ja2.id DESC LIMIT 1
            )
        ) a ON a.job_id = j.id
        """
    ).fetchall()
    return [dict(r) for r in rows]
