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
    set_clause = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
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


def _portfolio_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("technologies_json", "skills_json"):
        field = key.removesuffix("_json")
        try:
            data[field] = json.loads(data[key]) if data[key] else []
        except (TypeError, json.JSONDecodeError):
            data[field] = []
    return data


def list_portfolios(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM portfolios WHERE profile_id = ? ORDER BY id", (profile_id,)
    ).fetchall()
    return [_portfolio_row_to_dict(r) for r in rows]


def add_portfolio(conn: sqlite3.Connection, profile_id: int, data: dict) -> int:
    now = now_jst_str()
    cursor = conn.execute(
        """
        INSERT INTO portfolios
            (profile_id, title, description, technologies_json, skills_json,
             portfolio_url, github_url, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id, data["title"], data.get("description"),
            json.dumps(data.get("technologies", []), ensure_ascii=False),
            json.dumps(data.get("skills", []), ensure_ascii=False),
            data.get("portfolio_url"), data.get("github_url"),
            int(data.get("is_active", True)), now, now,
        ),
    )
    logger.info("制作実績を追加しました: title=%s", data.get("title"))
    return cursor.lastrowid


def update_portfolio(conn: sqlite3.Connection, portfolio_id: int, data: dict) -> None:
    data = dict(data)
    now = now_jst_str()
    if "technologies" in data:
        data["technologies_json"] = json.dumps(data.pop("technologies"), ensure_ascii=False)
    if "skills" in data:
        data["skills_json"] = json.dumps(data.pop("skills"), ensure_ascii=False)
    if "is_active" in data:
        data["is_active"] = int(data["is_active"])

    allowed = {"title", "description", "technologies_json", "skills_json", "portfolio_url", "github_url", "is_active"}
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
