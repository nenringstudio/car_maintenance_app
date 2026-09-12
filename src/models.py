"""車1台分の情報の「形」を決めるファイル。

Car というひとかたまりのデータとして扱います。
CSV でもスプレッドシートでも、1行 = 車1台 になるようにしてあります。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

# CSV / スプレッドシートの列の並び順（この順で1行に並びます）
FIELDNAMES = [
    "id",                      # アプリ内部で使う識別番号（自動採番）
    "name",                    # 車の名前（例: パパの車）
    "plate_number",            # ナンバー
    "inspection_due_date",     # 車検の期限日
    "last_oil_change_date",    # 直近のオイル交換日
    "last_tire_change_date",   # 直近のタイヤ交換日
]


@dataclass
class Car:
    """車1台分の情報。"""

    name: str
    plate_number: str = ""
    inspection_due_date: date | None = None
    last_oil_change_date: date | None = None
    last_tire_change_date: date | None = None
    # id は指定しなければ自動でユニークな文字列が入ります
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_row(self) -> dict[str, str]:
        """保存用に「すべて文字列の1行」に変換する。

        日付は "2026-09-08" の形（ISO形式）の文字列にします。
        この形なら CSV でもスプレッドシートでもそのまま使えます。
        """
        return {
            "id": self.id,
            "name": self.name,
            "plate_number": self.plate_number,
            "inspection_due_date": _date_to_str(self.inspection_due_date),
            "last_oil_change_date": _date_to_str(self.last_oil_change_date),
            "last_tire_change_date": _date_to_str(self.last_tire_change_date),
        }

    @classmethod
    def from_row(cls, row: dict) -> "Car":
        """保存されている1行（文字列の辞書）から Car を作り直す。"""
        return cls(
            id=(row.get("id") or "").strip() or str(uuid.uuid4()),
            name=(row.get("name") or "").strip(),
            plate_number=(row.get("plate_number") or "").strip(),
            inspection_due_date=_str_to_date(row.get("inspection_due_date")),
            last_oil_change_date=_str_to_date(row.get("last_oil_change_date")),
            last_tire_change_date=_str_to_date(row.get("last_tire_change_date")),
        )


def _date_to_str(d: date | None) -> str:
    """日付 -> "2026-09-08" のような文字列。空なら ""。"""
    return d.isoformat() if d else ""


def _str_to_date(s: str | None) -> date | None:
    """"2026-09-08" のような文字列 -> 日付。空や変な値なら None。"""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s).strip())
    except ValueError:
        return None
