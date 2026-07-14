"""アプリ共通のロガー設定。認証情報や個人情報はログへ出力しないこと。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.config import LOG_FILE_PATH

_LOGGER_NAME = "crowdworks_sales_assistant"
_configured = False


def get_logger() -> logging.Logger:
    """アプリ共通のロガーを取得する（初回呼び出し時にハンドラを設定）。"""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)

    if not _configured:
        logger.setLevel(logging.INFO)

        file_handler = RotatingFileHandler(
            LOG_FILE_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.propagate = False
        _configured = True

    return logger
