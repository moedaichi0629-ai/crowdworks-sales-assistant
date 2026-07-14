"""アプリ全体で共有する設定値・定数の定義。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

DB_PATH = Path(os.getenv("JOBS_DB_PATH", str(DATA_DIR / "jobs.db")))
LOG_FILE_PATH = LOGS_DIR / "app.log"

DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tokyo")

# --- 案件ステータス -----------------------------------------------------
STATUS_UNCONFIRMED = "未確認"
STATUS_CONFIRMED = "確認済み"
STATUS_CANDIDATE = "応募候補"
STATUS_SKIPPED = "見送り"
STATUS_PREPARING = "応募準備中"
STATUS_APPLIED = "応募済み"
STATUS_HIRED = "採用"
STATUS_REJECTED = "不採用"

JOB_STATUSES = [
    STATUS_UNCONFIRMED,
    STATUS_CONFIRMED,
    STATUS_CANDIDATE,
    STATUS_SKIPPED,
    STATUS_PREPARING,
    STATUS_APPLIED,
    STATUS_HIRED,
    STATUS_REJECTED,
]

# --- 募集形式 -------------------------------------------------------------
JOB_TYPES = ["固定報酬制", "時間単価制", "プロジェクト", "タスク", "コンペ", "その他"]

# --- データ取得方法 ---------------------------------------------------------
SOURCE_TYPE_URL = "url"
SOURCE_TYPE_MANUAL = "manual"
SOURCE_TYPE_CSV = "csv"
SOURCE_TYPES = [SOURCE_TYPE_URL, SOURCE_TYPE_MANUAL, SOURCE_TYPE_CSV]

# --- 初期検索キーワード -----------------------------------------------------
DEFAULT_SEARCH_KEYWORDS = [
    "AI", "ChatGPT", "OpenAI API", "Claude", "Gemini", "Dify",
    "Python", "JavaScript", "TypeScript", "React", "Next.js",
    "Webアプリ", "ホームページ制作", "LP制作", "WordPress", "API連携",
    "Googleスプレッドシート", "Google Apps Script", "業務自動化",
    "LINE連携", "チャットボット", "データ入力", "リサーチ", "SNS運用",
    "バナー制作", "資料作成",
]

# --- 初期除外キーワード -----------------------------------------------------
DEFAULT_EXCLUDE_KEYWORDS = [
    "高度な実務経験必須", "週5常駐", "出社必須", "電話営業", "成人向け",
    "ギャンブル", "仮想通貨投資", "初期費用", "教材購入", "LINE登録必須",
    "外部連絡先交換必須", "無報酬テスト",
]

# --- 既定設定値 -------------------------------------------------------------
DEFAULT_SETTINGS = {
    "search_keywords": DEFAULT_SEARCH_KEYWORDS,
    "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    "min_budget": 0,
    "max_fetch_count": 20,
    "default_job_type": "固定報酬制",
    "fetch_wait_seconds": 3.0,
    "daily_application_limit": 5,
    "timezone": DEFAULT_TIMEZONE,
}

# 自動取得（スクレイピング）に関する安全設定 -----------------------------------
# robots.txt (https://crowdworks.jp/robots.txt) で ClaudeBot / GPTBot 等の
# AIクローラーが明示的にブロックされていることを確認したため、
# crowdworks.jp ドメインへの自動アクセスはアプリ側で禁止する。
BLOCKED_FETCH_DOMAINS = ["crowdworks.jp", "www.crowdworks.jp"]

USER_AGENT = "crowdworks-sales-assistant/0.1 (personal job search assistant; contact: user)"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRY_COUNT = 2
MIN_FETCH_INTERVAL_SECONDS = 2.0

MAX_CSV_UPLOAD_SIZE_MB = 5

# =============================================================================
# 第2段階: AI案件分析関連の設定
# =============================================================================

# --- AIプロバイダー ----------------------------------------------------------
AI_PROVIDER_OPENAI = "openai"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_GEMINI = "gemini"
AI_PROVIDER_NONE = "none"
AI_PROVIDERS = [AI_PROVIDER_NONE, AI_PROVIDER_OPENAI, AI_PROVIDER_ANTHROPIC, AI_PROVIDER_GEMINI]

DEFAULT_AI_PROVIDER = os.getenv("AI_PROVIDER", AI_PROVIDER_NONE)

DEFAULT_MODELS = {
    AI_PROVIDER_OPENAI: os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    AI_PROVIDER_ANTHROPIC: os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
    AI_PROVIDER_GEMINI: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
}

PROMPT_VERSION = "v1"
AI_MAX_BODY_CHARS = 4000  # 案件本文をAIへ渡す際の最大文字数（費用対策・トークン対策）

# --- 分析ステータス -----------------------------------------------------------
ANALYSIS_STATUS_UNANALYZED = "未分析"
ANALYSIS_STATUS_ANALYZED = "分析済み"
ANALYSIS_STATUS_FAILED = "分析失敗"
ANALYSIS_STATUSES = [ANALYSIS_STATUS_UNANALYZED, ANALYSIS_STATUS_ANALYZED, ANALYSIS_STATUS_FAILED]

# --- 応募推奨度・難易度・予算評価・危険度 ---------------------------------------
RECOMMENDATIONS = ["strong_apply", "apply", "consider", "skip"]
RECOMMENDATION_LABELS_JA = {
    "strong_apply": "強く応募推奨", "apply": "応募推奨", "consider": "要検討", "skip": "見送り推奨",
}

DIFFICULTIES = ["beginner", "intermediate", "advanced", "expert"]
DIFFICULTY_LABELS_JA = {
    "beginner": "初級", "intermediate": "中級", "advanced": "上級", "expert": "エキスパート",
}

BUDGET_EVALUATIONS = ["low", "fair", "good", "unknown"]
BUDGET_EVALUATION_LABELS_JA = {
    "low": "低い", "fair": "妥当", "good": "良い", "unknown": "不明",
}

RISK_LEVELS = ["low", "medium", "high", "critical"]
RISK_LEVEL_LABELS_JA = {
    "low": "低", "medium": "中", "high": "高", "critical": "非常に高い",
}

RECOMMENDED_ACTIONS = ["proceed", "review", "avoid"]
RECOMMENDED_ACTION_LABELS_JA = {
    "proceed": "進めてよい", "review": "要確認", "avoid": "避けるべき",
}

# --- 応募優先度 ---------------------------------------------------------------
PRIORITY_TOP = "最優先"
PRIORITY_HIGH = "優先"
PRIORITY_CANDIDATE = "応募候補"
PRIORITY_REVIEW = "要確認"
PRIORITY_SKIP = "見送り候補"
APPLICATION_PRIORITIES = [PRIORITY_TOP, PRIORITY_HIGH, PRIORITY_CANDIDATE, PRIORITY_REVIEW, PRIORITY_SKIP]

DEFAULT_PRIORITY_THRESHOLDS = {
    "top": 90,
    "high": 80,
    "candidate": 70,
    "review": 60,
}

# --- 経験区分・習熟度 ----------------------------------------------------------
EXPERIENCE_TYPES = ["学習", "個人開発", "公開実績", "実案件", "その他"]
PROFICIENCY_LEVELS = ["学習中", "基礎", "個人開発で使用", "公開実績あり", "実案件で使用", "上級"]

SKILL_CATEGORIES = [
    "基本情報", "プログラミング・開発", "AI関連", "API・外部サービス連携",
    "Web・自動化", "デザイン", "公開・デプロイ",
]

# --- 総合スコアの重み（合計100%になるようにすること） ----------------------------
DEFAULT_SCORE_WEIGHTS = {
    "ai_suitability": 0.35,
    "rule_based": 0.20,
    "safety": 0.15,
    "budget": 0.10,
    "deadline": 0.05,
    "applicant_count": 0.05,
    "client_trust": 0.05,
    "portfolio_match": 0.05,
}

# --- ルールベース判定の加点・減点重み -------------------------------------------
DEFAULT_RULE_WEIGHTS = {
    "skill_match_per_hit": 5,
    "skill_match_max": 40,
    "portfolio_match_bonus": 10,
    "preferred_condition_bonus": 5,
    "difficult_condition_penalty": 8,
    "exclude_keyword_penalty": 15,
    "budget_low_penalty": 8,
    "budget_good_bonus": 5,
    "deadline_tight_penalty": 6,
    "deadline_ample_bonus": 2,
    "applicant_many_penalty": 5,
    "applicant_few_bonus": 3,
    "client_rating_high_bonus": 5,
    "client_rating_low_penalty": 5,
    "identity_verified_bonus": 5,
    "body_vague_penalty": 5,
    "body_concrete_bonus": 6,
}

RULE_BUDGET_LOW_THRESHOLD_YEN = 10000
RULE_DEADLINE_TIGHT_DAYS = 3
RULE_APPLICANT_MANY_COUNT = 10
RULE_APPLICANT_FEW_COUNT = 3
RULE_CLIENT_RATING_HIGH = 4.5
RULE_CLIENT_RATING_LOW = 3.5
RULE_BODY_VAGUE_LENGTH = 50

# --- 加点・減点キーワード（設定画面から編集可能） -------------------------------
DEFAULT_BONUS_KEYWORDS = ["長期継続", "継続案件", "リモート", "在宅", "オンライン完結", "経験者優遇"]
DEFAULT_PENALTY_KEYWORDS = ["未経験者歓迎", "誰でもできる", "急募", "至急"]
RULE_KEYWORD_BONUS_WEIGHT = 3
RULE_KEYWORD_PENALTY_WEIGHT = 3
RULE_KEYWORD_BONUS_MAX = 9
RULE_KEYWORD_PENALTY_MAX = 9

# --- 危険キーワードカテゴリ（単純一致用。AIの文脈判定と併用する） -----------------
DEFAULT_DANGER_KEYWORD_CATEGORIES = {
    "外部LINE・SNSへの登録誘導": ["LINE登録", "個人LINE", "LINEで直接", "InstagramのDMで", "外部SNSで連絡"],
    "クラウドワークス外での直接契約誘導": ["クラウドワークス外", "直接契約", "直取引", "直接契約に切り替え"],
    "教材・商品・サービスの購入要求": ["教材購入", "商品を購入", "サービスの購入", "教材費"],
    "初期費用・登録費用の要求": ["初期費用", "登録費用", "保証金が必要", "入会金"],
    "無報酬テスト": ["無報酬でテスト", "無償トライアル", "無料お試し作業"],
    "極端に低い報酬・高収入の過度な強調": ["高収入", "誰でも稼げる", "簡単に稼げる", "月収100万"],
    "業務・成果物・報酬条件が不明確": ["詳細は応募後に連絡", "報酬は応相談のみ"],
    "個人情報の過剰な提出要求": ["本人確認書類を送付", "運転免許証の写真", "マイナンバーを提出"],
    "仮払い前の作業要求": ["仮払い前に作業", "入金確認前に納品"],
    "投資・副業コミュニティへの勧誘": ["投資の勧誘", "副業コミュニティ", "権利収入", "unfold仮想通貨"],
    "成人向け・ギャンブル関連": ["成人向け", "アダルト", "ギャンブル", "カジノ"],
    "不自然に短い納期": ["即日納品", "24時間以内に納品"],
    "規約違反・不正行為の要求": ["やらせレビュー", "サクラ投稿", "アカウントの貸し借り", "虚偽のレビュー"],
}

# --- 対応が難しい案件の初期条件（第2段階） --------------------------------------
DEFAULT_DIFFICULT_CONDITIONS = [
    "週5日常駐", "出社必須", "平日日中の長時間拘束", "電話営業", "飛び込み営業",
    "高度な業務システムの実務経験必須", "大規模インフラ構築", "AWSやGCPの高度な本番運用が必須",
    "セキュリティ監査の実務経験必須", "大規模チームのPM経験必須", "ネイティブアプリの高度な開発",
    "24時間監視", "緊急対応必須", "即日納品", "成人向け", "ギャンブル", "投資勧誘",
    "教材購入が必要", "初期費用が必要", "無報酬テスト", "外部LINE登録が応募条件",
    "クラウドワークス外での契約が前提",
]

DEFAULT_PREFERRED_CONDITIONS = ["オンライン完結", "リモート対応可能"]

DEFAULT_ATTAINABLE_TASKS = [
    "Webアプリ開発", "ホームページ・LP制作", "AIチャットボット開発",
    "業務自動化（GAS・API連携）", "データ収集・CSV処理", "データ可視化・ダッシュボード制作",
    "AI文章生成・添削", "バナー・SNS画像・チラシ・ロゴ制作",
]

DEFAULT_EXCLUDED_CONDITIONS: list[str] = []

# --- AI分析設定のデフォルト値 --------------------------------------------------
DEFAULT_ANALYSIS_SETTINGS = {
    "ai_provider": DEFAULT_AI_PROVIDER,
    "ai_models": DEFAULT_MODELS,
    "api_timeout_seconds": 30,
    "max_retry_count": 1,
    "bulk_analysis_max_count": 10,
    "analysis_wait_seconds": 2.0,
    "max_tokens": 1500,
    "daily_analysis_limit": 50,
    "min_body_chars_for_analysis": 20,
    "score_weights": DEFAULT_SCORE_WEIGHTS,
    "priority_thresholds": DEFAULT_PRIORITY_THRESHOLDS,
    "rule_weights": DEFAULT_RULE_WEIGHTS,
    "danger_keyword_categories": DEFAULT_DANGER_KEYWORD_CATEGORIES,
    "bonus_keywords": DEFAULT_BONUS_KEYWORDS,
    "penalty_keywords": DEFAULT_PENALTY_KEYWORDS,
    "min_budget_for_analysis": 0,
    "max_applicant_count": 0,
    "min_client_rating": 0.0,
    "require_identity_verified": False,
    "rule_based_only": DEFAULT_AI_PROVIDER == AI_PROVIDER_NONE,
    # 営業文生成用（案件分析用とはモデルのみ別設定可能。プロバイダー・タイムアウト等は共通）
    "application_ai_models": None,  # None の場合は起動時に DEFAULT_APPLICATION_MODELS を使用
    "application_max_tokens": 2000,
    "application_bulk_max_count": 5,
    "application_daily_limit": 30,
}

# =============================================================================
# 第3段階: 営業文自動生成・ポートフォリオ自動選択・料金/納期提案関連の設定
# =============================================================================

# --- 営業文生成用モデル（案件分析用モデルとは別に設定可能） ------------------------
DEFAULT_APPLICATION_MODELS = {
    AI_PROVIDER_OPENAI: os.getenv("APPLICATION_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
    AI_PROVIDER_ANTHROPIC: os.getenv("APPLICATION_ANTHROPIC_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")),
    AI_PROVIDER_GEMINI: os.getenv("APPLICATION_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-flash")),
}

APPLICATION_PROMPT_VERSION = "v1"

# --- 営業文タイプ（トーン） ------------------------------------------------------
TONE_STANDARD = "標準"
TONE_SHORT = "短め"
TONE_POLITE = "丁寧"
TONE_ENTHUSIASTIC = "熱意重視"
TONE_TECHNICAL = "技術説明重視"
TONE_ACHIEVEMENT = "実績重視"
TONE_PROPOSAL = "提案重視"
TONE_SINCERE_BEGINNER = "初心者らしい誠実さ重視"
TONE_DESIGN = "デザイン案件向け"
TONE_AI_DEV = "AI・開発案件向け"
TONE_AUTOMATION = "業務自動化案件向け"
TONE_WEBSITE = "ホームページ制作案件向け"
TONE_DATA_ENTRY = "データ入力・リサーチ案件向け"
TONE_SNS_DESIGN = "SNS・デザイン案件向け"
TONE_BANNER = "バナー・サムネイル制作向け"
TONE_LOGO_PRINT = "ロゴ・印刷物制作向け"
TONE_AI_DESIGN = "AI×デザイン複合案件向け"

GENERATION_TONES = [
    TONE_STANDARD, TONE_SHORT, TONE_POLITE, TONE_ENTHUSIASTIC, TONE_TECHNICAL,
    TONE_ACHIEVEMENT, TONE_PROPOSAL, TONE_SINCERE_BEGINNER, TONE_DESIGN, TONE_AI_DEV,
    TONE_AUTOMATION, TONE_WEBSITE, TONE_DATA_ENTRY, TONE_SNS_DESIGN, TONE_BANNER,
    TONE_LOGO_PRINT, TONE_AI_DESIGN,
]

# --- 営業文の長さ ----------------------------------------------------------------
LENGTH_SHORT = "短文"
LENGTH_STANDARD = "標準"
LENGTH_DETAILED = "詳細"
LENGTH_MATCH_JOB = "案件指定に合わせる"
LENGTH_TYPES = [LENGTH_SHORT, LENGTH_STANDARD, LENGTH_DETAILED, LENGTH_MATCH_JOB]

LENGTH_CHAR_RANGES = {
    LENGTH_SHORT: (300, 500),
    LENGTH_STANDARD: (500, 800),
    LENGTH_DETAILED: (800, 1200),
    LENGTH_MATCH_JOB: (300, 1200),
}
DEFAULT_MAX_APPLICATION_CHARS = 1400  # これを超えた場合は自動で要約版を作成する

# --- 応募準備ステータス ------------------------------------------------------------
PREP_STATUS_NONE = "未作成"
PREP_STATUS_GENERATING = "生成中"
PREP_STATUS_DRAFT = "下書き"
PREP_STATUS_NEEDS_REVIEW = "要確認"
PREP_STATUS_EDITING = "修正中"
PREP_STATUS_READY = "応募準備完了"
PREP_STATUS_COPIED = "コピー済み"
PREP_STATUS_APPLIED = "応募済み"
PREP_STATUS_ON_HOLD = "保留"
PREP_STATUS_SKIPPED = "見送り"

PREPARATION_STATUSES = [
    PREP_STATUS_NONE, PREP_STATUS_GENERATING, PREP_STATUS_DRAFT, PREP_STATUS_NEEDS_REVIEW,
    PREP_STATUS_EDITING, PREP_STATUS_READY, PREP_STATUS_COPIED, PREP_STATUS_APPLIED,
    PREP_STATUS_ON_HOLD, PREP_STATUS_SKIPPED,
]

# --- ポートフォリオ区分 ------------------------------------------------------------
PORTFOLIO_TYPE_DEVELOPMENT = "development"
PORTFOLIO_TYPE_DESIGN = "design"
PORTFOLIO_TYPE_GENERAL = "general"
PORTFOLIO_TYPES = [PORTFOLIO_TYPE_DEVELOPMENT, PORTFOLIO_TYPE_DESIGN, PORTFOLIO_TYPE_GENERAL]
PORTFOLIO_TYPE_LABELS_JA = {
    PORTFOLIO_TYPE_DEVELOPMENT: "AI・開発", PORTFOLIO_TYPE_DESIGN: "デザイン", PORTFOLIO_TYPE_GENERAL: "総合",
}

# 案件カテゴリ判定用キーワード（デザイン系 / 開発系 / AI×デザイン複合系）
DEFAULT_DESIGN_JOB_KEYWORDS = [
    "バナー制作", "バナー", "SNS投稿画像", "Instagram投稿画像", "YouTubeサムネイル", "サムネイル",
    "広告クリエイティブ", "チラシ", "名刺", "ショップカード", "ロゴ", "資料デザイン", "スライドデザイン",
    "Webデザイン", "LPデザイン", "Illustrator", "Photoshop", "画像制作", "グラフィックデザイン",
]
DEFAULT_DEVELOPMENT_JOB_KEYWORDS = [
    "AIツール開発", "Webアプリ開発", "API連携", "Python", "React", "Streamlit", "Dify", "ChatGPT",
    "OpenAI API", "Google API", "LINE連携", "業務自動化", "ホームページ実装", "システム開発",
]
DEFAULT_AI_DESIGN_JOB_KEYWORDS = [
    "AIを使用した画像制作", "AIデザイン", "AIを使ったSNS制作", "Webサイトのデザインと実装",
    "LPのデザインとコーディング", "SNS運用と投稿画像制作", "AIを活用した資料作成", "デザイン業務の自動化",
]

# --- クライアント名・応募機密情報保護対象キーワード（営業文へ含めない） -----------------
FORBIDDEN_CONTENT_KEYWORDS = [
    "パスワード", "APIキー", "秘密鍵", "クレジットカード", "口座番号", "マイナンバー",
]

# --- 営業文生成を停止する危険カテゴリ（危険案件判定に加えて営業文固有の停止条件） ----------
APPLICATION_STOP_KEYWORD_CATEGORIES = {
    "成人向け・ギャンブル・投資勧誘": ["成人向け", "アダルト", "ギャンブル", "カジノ", "投資の勧誘", "仮想通貨投資"],
    "教材購入・初期費用が必要": ["教材購入", "教材費", "初期費用", "登録費用", "保証金が必要", "入会金"],
    "無報酬作業のみ": ["無報酬でテスト", "無償トライアル", "無料お試し作業", "報酬は発生しません"],
    "アカウント貸与・虚偽レビュー・規約違反": [
        "アカウントの貸し借り", "アカウント貸与", "やらせレビュー", "サクラ投稿", "虚偽のレビュー", "水増し",
    ],
    "著作権・素材ライセンス違反": ["無断転載", "トレース", "他者の作品をそのまま", "著作権を気にせず", "素材の無断使用"],
}
APPLICATION_MIN_SAFETY_SCORE = 40  # これ未満の安全度では営業文生成を停止する
APPLICATION_MIN_BODY_CHARS = 20

# --- 応募金額提案の初期設定 ---------------------------------------------------------
DEFAULT_PRICING_SETTINGS = {
    "base_hourly_rate_yen": 1200,
    "ai_api_hourly_rate_min": 1200,
    "ai_api_hourly_rate_max": 2000,
    "website_minimum_price_yen": 10000,
    "minimum_order_price_yen": 3000,
    "standard_revision_count": 2,
    "rush_fee_addable": True,
    "external_api_cost_policy": "クライアント負担または別途相談",
    "paid_material_cost_policy": "クライアント負担または事前相談",
    "avoid_extreme_discount": True,
    "category_price_notes": {
        "バナー制作": "内容と枚数に応じて設定",
        "SNS投稿画像": "枚数とテンプレート数に応じて設定",
        "YouTubeサムネイル": "内容に応じて設定",
        "ロゴ制作": "修正回数・提案数に応じて設定",
        "名刺・チラシ": "片面・両面や入稿データの有無で調整",
        "データ入力": "案件相場に応じる",
    },
}

# --- 納期提案の初期設定 -------------------------------------------------------------
DEFAULT_DELIVERY_SETTINGS = {
    "daily_available_hours_default": 2.5,
    "buffer_days_min": 1,
    "buffer_days_standard": 2,
    "revision_buffer_days": 1,
    "design_draft_buffer_days": 1,
    "material_wait_buffer_days": 1,
    "api_review_buffer_days": 2,
}

# --- 営業文構成（見出し表示の有無は画面から設定可能） ---------------------------------
APPLICATION_MESSAGE_SECTIONS = [
    "opening", "understanding", "matching_reason", "skills_to_highlight", "portfolio",
    "proposed_approach", "delivery", "price", "client_questions", "questions_for_client",
    "contact_policy", "closing",
]

# --- クライアント質問抽出用パターン(本文中の代表的な質問見出し) ------------------------
DEFAULT_CLIENT_QUESTION_MARKERS = [
    "自己紹介", "実績", "使用経験", "稼働時間", "対応可能時間", "希望金額", "希望単価", "納期",
    "応募理由", "過去の制作物", "使用できるツール", "Illustrator", "Photoshop", "デザインポートフォリオ",
    "GitHub", "継続対応", "週あたりの作業時間", "ポートフォリオ",
]

# --- 営業文AI出力の既定値(不足項目の安全な補完に使用) ---------------------------------
DEFAULT_APPLICATION_AI_RESPONSE = {
    "application_title": "",
    "opening": "",
    "understanding": "",
    "matching_reason": "",
    "skills_to_highlight": [],
    "portfolio_ids": [],
    "portfolio_reasons": [],
    "proposed_approach": [],
    "proposed_price": 0,
    "price_reason": "",
    "proposed_delivery_days": 0,
    "delivery_reason": "",
    "answers_to_client_questions": [],
    "questions_for_client": [],
    "closing": "",
    "full_message": "",
    "short_message": "",
    "warnings": [],
    "missing_information": [],
    "confidence": 0,
}
