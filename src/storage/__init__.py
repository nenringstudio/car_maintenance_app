"""保存先を1か所で選ぶための入り口。

app.py からは get_storage() を呼ぶだけ。
保存先を変えるときは config の DATA_BACKEND を "csv" / "gsheets" で切り替えます。
"""
from __future__ import annotations

from src.config import CSV_PATH, DATA_BACKEND
from src.storage.base import CarStorage
from src.storage.csv_storage import CsvCarStorage


def get_storage() -> CarStorage:
    if DATA_BACKEND == "csv":
        return CsvCarStorage(CSV_PATH)

    if DATA_BACKEND == "gsheets":
        # import はこの分岐に入ったときだけ（gspread 未インストールでも csv は動く）
        from src.storage.gsheets_storage import GoogleSheetsCarStorage

        return GoogleSheetsCarStorage()

    raise ValueError(
        f"未対応の保存先です: {DATA_BACKEND!r}（'csv' か 'gsheets' を指定してください）"
    )


__all__ = ["CarStorage", "get_storage"]
