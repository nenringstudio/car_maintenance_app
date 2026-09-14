"""保存先を1か所で選ぶための入り口。

app.py からは get_storages() を呼ぶだけ。
保存先を変えるときは config の DATA_BACKEND を "csv" / "gsheets" で切り替えます。
"""
from __future__ import annotations

from src.config import CSV_PATH, DATA_BACKEND, RECORDS_CSV_PATH
from src.storage.base import CarStorage, MaintenanceRecordStorage
from src.storage.csv_storage import CsvCarStorage, CsvMaintenanceRecordStorage


def get_record_storage() -> MaintenanceRecordStorage:
    """整備記録（履歴）の保存先を返す。"""
    if DATA_BACKEND == "csv":
        return CsvMaintenanceRecordStorage(RECORDS_CSV_PATH)

    if DATA_BACKEND == "gsheets":
        # import はこの分岐に入ったときだけ（gspread 未インストールでも csv は動く）
        from src.storage.gsheets_storage import GoogleSheetsMaintenanceRecordStorage

        return GoogleSheetsMaintenanceRecordStorage()

    raise ValueError(
        f"未対応の保存先です: {DATA_BACKEND!r}（'csv' か 'gsheets' を指定してください）"
    )


def get_storage(record_storage: MaintenanceRecordStorage | None = None) -> CarStorage:
    """車の情報の保存先を返す。

    record_storage を渡すと、古い形式のデータ（前回の日付を車に直接持たせていた形）
    が見つかったときに、そちらへ履歴として移してくれる。
    """
    if record_storage is None:
        record_storage = get_record_storage()

    if DATA_BACKEND == "csv":
        return CsvCarStorage(CSV_PATH, record_storage=record_storage)

    if DATA_BACKEND == "gsheets":
        from src.storage.gsheets_storage import GoogleSheetsCarStorage

        return GoogleSheetsCarStorage(record_storage=record_storage)

    raise ValueError(
        f"未対応の保存先です: {DATA_BACKEND!r}（'csv' か 'gsheets' を指定してください）"
    )


def get_storages() -> tuple[CarStorage, MaintenanceRecordStorage]:
    """車の保存先と、整備記録の保存先をまとめて用意する（app.py はこれを使う）。"""
    record_storage = get_record_storage()
    car_storage = get_storage(record_storage=record_storage)
    return car_storage, record_storage


__all__ = [
    "CarStorage",
    "MaintenanceRecordStorage",
    "get_storage",
    "get_record_storage",
    "get_storages",
]
