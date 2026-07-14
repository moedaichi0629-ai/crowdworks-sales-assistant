"""クライアント質問抽出(client_question_extractor)のテスト。"""
from __future__ import annotations

from src.application.client_question_extractor import extract_client_questions


def test_extracts_explicit_question():
    job = {"body": "稼働時間はどれくらい確保できますか？"}
    questions = extract_client_questions(job)
    assert any("稼働時間" in q["question"] for q in questions)


def test_extracts_applicant_info_request():
    job = {"body": "自己紹介と実績を教えてください。"}
    questions = extract_client_questions(job)
    assert questions
    assert any("自己紹介" in q["question"] or "実績" in q["question"] for q in questions)


def test_design_marker_classified_as_design():
    job = {"body": "Illustratorでの制作経験があるか教えてください。"}
    questions = extract_client_questions(job)
    assert questions[0]["answer_category"] == "design"


def test_github_marker_classified_as_github():
    job = {"body": "GitHubで過去の開発履歴を確認させてください。"}
    questions = extract_client_questions(job)
    assert any(q["answer_category"] == "github" for q in questions)


def test_no_questions_in_empty_body():
    assert extract_client_questions({"body": ""}) == []
    assert extract_client_questions({}) == []


def test_pure_client_statement_not_treated_as_question():
    job = {"body": "納期は2週間程度でお願いします。"}
    questions = extract_client_questions(job)
    assert questions == []


def test_duplicate_lines_are_not_repeated():
    job = {"body": "実績を教えてください。実績を教えてください。"}
    questions = extract_client_questions(job)
    texts = [q["question"] for q in questions]
    assert len(texts) == len(set(texts))


def test_max_question_cap():
    lines = "。".join(f"質問{i}の実績を教えてください" for i in range(20))
    job = {"body": lines}
    questions = extract_client_questions(job)
    assert len(questions) <= 10
