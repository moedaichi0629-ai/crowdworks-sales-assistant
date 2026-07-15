"""第1〜第4段階の主要フローを通した統合テスト。

案件登録 → AI/ルール分析 → 営業文生成 → ポートフォリオ選択 → 本日の候補選定 →
応募記録 → 返信登録 → 面談登録 → 採用結果登録 → KPI集計、までの一連の流れを検証する。
"""
from __future__ import annotations

from src.analytics.kpi_service import compute_kpis
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.application.application_service import generate_for_job
from src.crm.application_history_service import get_application_detail
from src.crm.interview_service import create_interview
from src.crm.response_service import record_response
from src.crm.result_service import record_hired
from src.daily.candidate_selector import select_daily_candidates
from src.daily.goal_service import save_daily_goal
from src.database import session
from src.repositories import get_current_application_draft, get_job, insert_job, save_job_analysis

TARGET_DATE = "2026-07-15"


def test_full_pipeline_from_job_registration_to_kpi(db_path):
    # 1. 案件登録
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": "AI業務自動化ツール開発", "body": "PythonとOpenAI APIで業務自動化ツールを開発してください。" * 3,
            "category": "AI開発", "job_type": "固定報酬制", "source_type": "manual",
            "client_name": "テスト株式会社", "client_rating": 4.7, "identity_verified": 1,
            "applicant_count": 4, "deadline": "2026-08-01", "published_at": "2026-07-15 08:00:00",
        })

    # 2. ルールベース分析(AI未使用でも動作すること)
    with session(db_path) as conn:
        save_job_analysis(conn, job_id, {
            "rule_based_score": 80, "total_score": 82, "safety_score": 95, "risk_level": "low", "used_ai": 0,
        })

    # 3. 営業文生成(テンプレート)
    with session(db_path) as conn:
        generation_result = generate_for_job(conn, job_id, force_template=True)
    assert generation_result["draft_id"] is not None

    # 4. ポートフォリオ選択(営業文生成に含まれる自動選択が下書きに保存されていること)
    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert isinstance(draft.get("selected_portfolio_ids"), list)
    assert len(draft["selected_portfolio_ids"]) > 0

    # 5. 本日の候補選定
    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {
            "target_count": 1, "ai_development_target": 1, "design_target": 0, "other_target": 0,
        })
        selection = select_daily_candidates(conn, TARGET_DATE)
    assert selection["selected_count"] == 1

    # 6. 応募記録(応募済みとして正式記録)
    with session(db_path) as conn:
        from src.applications.application_record_service import record_application

        record_id = record_application(
            conn, TARGET_DATE, job_id, draft["id"], proposed_price=40000, proposed_delivery_days=7,
        )

    # 7. 返信登録
    with session(db_path) as conn:
        record_response(conn, record_id, "質問", "稼働時間を教えてください")

    # 8. 面談登録
    with session(db_path) as conn:
        create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")

    # 9. 採用結果登録
    with session(db_path) as conn:
        record_hired(conn, record_id, contract_amount=45000)

    # 10. KPI集計
    with session(db_path) as conn:
        date_from, date_to = resolve_period(PERIOD_ALL)
        kpis = compute_kpis(conn, date_from, date_to)

    assert kpis["application_count"] == 1
    assert kpis["response_count"] == 1
    assert kpis["response_rate"] == 100.0
    assert kpis["interview_count"] == 1
    assert kpis["hired_count"] == 1
    assert kpis["contract_amount_total"] == 45000

    with session(db_path) as conn:
        job_after = get_job(conn, job_id)
        detail = get_application_detail(conn, record_id)

    assert job_after["status"] == "採用"
    assert detail["record"]["application_status"] == "採用"
    assert detail["record"]["sent_message"]  # スナップショットが保存されていること
    assert len(detail["timeline"]) >= 5
    assert len(detail["status_history"]) >= 2
