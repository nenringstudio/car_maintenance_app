"""昔のデータ形式との互換用の処理。

以前は車の情報に「直近のオイル交換日」「直近のタイヤ交換日」を
1個ずつ直接持たせていましたが、今は整備記録（履歴）として
何件でも持てるようにしました。

この古い2つの列がまだ残っている場合、ここで整備記録の1件目として
移行してから、列自体は削除します（CSV / スプレッドシート共通の処理）。
"""
from __future__ import annotations

from datetime import date

from src.models import MaintenanceRecord, RecordType
from src.storage.base import MaintenanceRecordStorage

# 古い列名 -> 移行先の作業内容
LEGACY_DATE_COLUMNS: dict[str, RecordType] = {
    "last_oil_change_date": RecordType.OIL,
    "last_tire_change_date": RecordType.TIRE,
}


def migrate_legacy_rows_to_records(
    raw_rows: list[dict], record_storage: MaintenanceRecordStorage
) -> None:
    """車データの生の行（古い列を含む可能性あり）から、整備記録を作る。"""
    for row in raw_rows:
        car_id = (row.get("id") or "").strip()
        if not car_id:
            continue
        for column, record_type in LEGACY_DATE_COLUMNS.items():
            value = (row.get(column) or "").strip()
            if not value:
                continue
            parsed = _parse_iso_date(value)
            if parsed is None:
                continue
            record_storage.add_record(
                MaintenanceRecord(car_id=car_id, date=parsed, record_type=record_type)
            )


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
