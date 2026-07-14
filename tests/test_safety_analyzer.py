"""危険・低品質案件の単純キーワード一致検出(safety_analyzer)のテスト。"""
from __future__ import annotations

from src.analysis.safety_analyzer import analyze_safety_rule_based


def test_external_line_inducement_detection():
    job = {"title": "案件", "body": "作業前に個人LINEを教えてください。", "description": ""}
    result = analyze_safety_rule_based(job)
    categories = [r["category"] for r in result["detected_risks"]]
    assert "外部LINE・SNSへの登録誘導" in categories
    assert result["safety_score"] < 100


def test_educational_material_purchase_detection():
    job = {"title": "案件", "body": "まず教材購入をお願いします。", "description": ""}
    result = analyze_safety_rule_based(job)
    categories = [r["category"] for r in result["detected_risks"]]
    assert "教材・商品・サービスの購入要求" in categories
    assert result["risk_level"] == "critical"


def test_unpaid_test_detection():
    job = {"title": "案件", "body": "まずは無報酬でテストしていただきます。", "description": ""}
    result = analyze_safety_rule_based(job)
    categories = [r["category"] for r in result["detected_risks"]]
    assert "無報酬テスト" in categories


def test_upfront_fee_detection():
    job = {"title": "案件", "body": "初期費用が必要です。", "description": ""}
    result = analyze_safety_rule_based(job)
    categories = [r["category"] for r in result["detected_risks"]]
    assert "初期費用・登録費用の要求" in categories


def test_external_contract_inducement_detection():
    job = {"title": "案件", "body": "クラウドワークス外で直接契約しませんか。", "description": ""}
    result = analyze_safety_rule_based(job)
    categories = [r["category"] for r in result["detected_risks"]]
    assert "クラウドワークス外での直接契約誘導" in categories


def test_no_danger_keywords_gives_full_safety_score():
    job = {"title": "通常のWeb制作案件", "body": "コーポレートサイトの制作をお願いします。", "description": ""}
    result = analyze_safety_rule_based(job)
    assert result["detected_risks"] == []
    assert result["safety_score"] == 100
    assert result["risk_level"] == "low"


def test_detected_risks_are_marked_as_rule_source():
    """AIの文脈判定前のルール検出結果であることが分かるようsourceを分けて保存する。"""
    job = {"title": "案件", "body": "初期費用が必要です。", "description": ""}
    result = analyze_safety_rule_based(job)
    assert all(r["source"] == "rule" for r in result["detected_risks"])
