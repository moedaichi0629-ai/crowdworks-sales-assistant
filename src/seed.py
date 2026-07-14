"""サンプルデータ(data/sample_jobs.csv)をデータベースへ投入するスクリプト。

使い方: python -m src.seed
"""
from __future__ import annotations

from src.config import DATA_DIR
from src.csv_import import auto_map_columns, import_dataframe, read_csv_bytes
from src.database import init_db, session
from src.logger import get_logger

logger = get_logger()


def seed_sample_data() -> dict:
    init_db()
    sample_path = DATA_DIR / "sample_jobs.csv"
    file_bytes = sample_path.read_bytes()
    df = read_csv_bytes(file_bytes, sample_path.name)
    mapping, _unmapped = auto_map_columns(list(df.columns))

    with session() as conn:
        result = import_dataframe(conn, df, mapping, source_name="sample_jobs.csv")
    return result


if __name__ == "__main__":
    summary = seed_sample_data()
    print(
        f"サンプルデータ投入完了: 新規{summary['inserted']}件 / 更新{summary['updated']}件 / "
        f"重複{summary['duplicate']}件 / エラー{summary['errors']}件"
    )
