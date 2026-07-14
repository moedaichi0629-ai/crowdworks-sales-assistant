"""初期スキルプロフィール（ユーザー: もえ）のシードデータ。

AIに実績を過大評価させないよう、公開実績・制作実績に直接紐づくスキルのみ
experience_type="公開実績" とし、それ以外は「個人開発」レベルで登録している。
「実案件」区分は初期状態では使用しない（実案件経験が未確認のため）。
"""
from __future__ import annotations

from src.config import DEFAULT_DIFFICULT_CONDITIONS, DEFAULT_EXCLUDED_CONDITIONS, DEFAULT_PREFERRED_CONDITIONS, DEFAULT_ATTAINABLE_TASKS

DEFAULT_PROFILE = {
    "profile_name": "default",
    "display_name": "もえ",
    "job_title": "AIエンジニア / Webデザイナー",
    "experience_level": "学習・個人開発実績あり、実案件経験を増やしている段階",
    "daily_available_hours": "2〜3時間",
    "basic_info": {
        "languages": ["日本語"],
        "desired_jobs": "オンライン完結、リモート対応可能な案件",
        "contact_availability": "案件ごとに相談",
        "response_policy": "誠実な対応、丁寧な連絡、AIを活用した効率的な制作",
    },
    "preferred_conditions": {
        "preferred_conditions": list(DEFAULT_PREFERRED_CONDITIONS),
        "attainable_tasks": list(DEFAULT_ATTAINABLE_TASKS),
    },
    "difficult_conditions": {
        "difficult_conditions": list(DEFAULT_DIFFICULT_CONDITIONS),
        "excluded_conditions": list(DEFAULT_EXCLUDED_CONDITIONS),
    },
}

# 公開実績（制作実績）に直接紐づくスキルは "公開実績" 区分とする
_PUBLIC_PORTFOLIO_SKILLS = {
    "Python", "React", "Streamlit", "OpenAI API", "Dify", "Google Maps API",
    "Google Sheets API", "Google Calendar API", "Google Docs API", "Google Drive API",
    "OpenWeather API", "OAuth認証", "LINE Messaging API", "AIチャットボット開発",
    "AI文章生成", "AI文章添削", "プロンプト設計", "AIを活用した業務効率化",
    "AIを活用したWebアプリ開発", "API連携", "Webアプリ制作", "ホームページ制作",
    "データ可視化", "業務自動化",
}


def _skill(category: str, name: str) -> dict:
    if name in _PUBLIC_PORTFOLIO_SKILLS:
        return {
            "category": category, "skill_name": name,
            "proficiency_level": "公開実績あり", "experience_type": "公開実績",
            "years_experience": None, "memo": None,
        }
    return {
        "category": category, "skill_name": name,
        "proficiency_level": "個人開発で使用", "experience_type": "個人開発",
        "years_experience": None, "memo": None,
    }


_PROGRAMMING_SKILLS = [
    "Python", "JavaScript", "TypeScript", "React", "Vite", "Flask",
    "Streamlit", "Node.js", "HTML", "CSS", "Git", "GitHub",
]

_AI_SKILLS = [
    "OpenAI API", "ChatGPT", "Claude", "Claude Code", "Gemini", "Dify",
    "プロンプト設計", "AIチャットボット開発", "AI文章生成", "AI文章添削",
    "AIを活用した業務効率化", "AIを活用したWebアプリ開発",
]

_API_SKILLS = [
    "Google Drive API", "Google Docs API", "Google Sheets API", "Google Calendar API",
    "Google Maps API", "Gmail API", "YouTube Data API", "LINE Messaging API",
    "Slack API", "Discord Webhook", "Zoom API", "OpenWeather API", "OAuth認証",
]

_WEB_AUTOMATION_SKILLS = [
    "Webアプリ制作", "ホームページ制作", "LP制作", "API連携", "データ収集", "CSV処理",
    "Googleスプレッドシート自動化", "Googleドキュメント自動生成", "LINE通知",
    "業務自動化", "データ可視化", "定期処理の設計",
]

_DESIGN_SKILLS = [
    "Webデザイン", "バナー制作", "SNS投稿画像制作", "YouTubeサムネイル制作",
    "名刺・ショップカード制作", "チラシ制作", "ロゴ制作", "Illustrator", "Photoshop",
]

_DEPLOY_SKILLS = ["GitHub Pages", "Vercel", "Netlify", "Streamlit Cloud", "Render"]

DEFAULT_SKILLS = (
    [_skill("プログラミング・開発", s) for s in _PROGRAMMING_SKILLS]
    + [_skill("AI関連", s) for s in _AI_SKILLS]
    + [_skill("API・外部サービス連携", s) for s in _API_SKILLS]
    + [_skill("Web・自動化", s) for s in _WEB_AUTOMATION_SKILLS]
    + [_skill("デザイン", s) for s in _DESIGN_SKILLS]
    + [_skill("公開・デプロイ", s) for s in _DEPLOY_SKILLS]
)

DEFAULT_PORTFOLIOS = [
    {
        "title": "Googleマップ×ホームページ生成システム",
        "description": "Googleマップの店舗情報をもとにホームページのたたき台を自動作成するシステム。店舗情報整理からホームページ自動生成までを行う。",
        "technologies": ["Google Maps API", "Webアプリ制作"],
        "skills": ["Google Maps API", "Web制作", "店舗情報整理", "ホームページ自動生成"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "歌舞伎予習AIチャットボット",
        "description": "演目情報・あらすじ・登場人物・用語などを説明するAIチャットボット。",
        "technologies": ["Dify API", "React"],
        "skills": ["Dify API", "React", "AIチャットボット", "外部API連携"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "AI ToDoリスト",
        "description": "タスク管理・AIによるタスク分解・締切管理・ダッシュボード表示・Googleスプレッドシート連携を備えたタスク管理アプリ。",
        "technologies": ["React", "Google Sheets API"],
        "skills": ["タスク管理", "AIによるタスク分解", "締切管理", "ダッシュボード", "React", "Google Sheets連携"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "AI文章添削ツール",
        "description": "入力文章を用途やトーンに合わせて添削するツール。",
        "technologies": ["Python", "Streamlit", "OpenAI API"],
        "skills": ["Python", "Streamlit", "OpenAI API", "文章生成"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "AI日程調整ツール",
        "description": "候補日時の抽出、提案文生成、Googleカレンダー登録までを行う日程調整ツール。",
        "technologies": ["Streamlit", "Google Calendar API", "OAuth認証"],
        "skills": ["候補日時の抽出", "提案文生成", "Googleカレンダー登録", "OAuth認証", "Streamlit"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "天気予報Webアプリ",
        "description": "都市検索・現在地天気・履歴・お気に入り・時間帯グラフを備えた天気予報アプリ。",
        "technologies": ["React", "OpenWeather API"],
        "skills": ["都市検索", "現在地天気", "履歴", "お気に入り", "時間帯グラフ", "OpenWeather API", "React"],
        "portfolio_url": None,
        "github_url": None,
    },
    {
        "title": "LINE連携ライブ思い出アルバム",
        "description": "LINEから写真やライブ情報を登録し、Google Docsでアルバムを生成、Google Driveへ保存、Google Sheetsで履歴管理するシステム。",
        "technologies": ["LINE Messaging API", "Google Docs API", "Google Drive API", "Google Sheets API"],
        "skills": ["LINE連携", "Google Docsアルバム生成", "Google Drive保存", "Google Sheets履歴管理"],
        "portfolio_url": None,
        "github_url": None,
    },
]
