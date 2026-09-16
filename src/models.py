"""データの「形」を決めるファイル。

このアプリが扱うデータは2種類です。
  ・Car …………………… 車1台分の基本情報（名前・ナンバー・車検期限など）
  ・MaintenanceRecord … 整備記録1件分（いつ・何を・いくらで・メモ）

車1台に対して整備記録は何件でも持てます（1対多の関係）。
整備記録は car_id で「どの車の記録か」を紐づけています。
CSV でもスプレッドシートでも、1行 = データ1件 になるようにしてあります。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# =====================================================================
# Car: 車1台分の情報
# =====================================================================

# CSV / スプレッドシートの列の並び順（この順で1行に並びます）
# ※ owner 以降は後から追加した列。既存データとの互換のため末尾に足しています。
# ※ 以前あった last_oil_change_date / last_tire_change_date は、
#   整備記録（MaintenanceRecord）に移行したのでここには含みません。
# ※ 自動車税は「毎年5月」から自動計算するだけなので、列（保存する値）はありません。
FIELDNAMES = [
    "id",                                  # アプリ内部で使う識別番号（自動採番）
    "name",                                # 車の名前（例: パパの車）
    "plate_number",                        # ナンバー
    "inspection_due_date",                 # 車検の期限日
    "owner",                               # 担当者（例: 父 / 母 / 長男 / 長女）
    "compulsory_insurance_due_date",       # 自賠責保険の満期日
    "voluntary_insurance_due_date",        # 任意保険の満期日
]


@dataclass
class Car:
    """車1台分の情報。"""

    name: str
    plate_number: str = ""
    inspection_due_date: date | None = None
    owner: str = ""
    compulsory_insurance_due_date: date | None = None  # 自賠責保険の満期日
    voluntary_insurance_due_date: date | None = None    # 任意保険の満期日
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
            "owner": self.owner,
            "compulsory_insurance_due_date": _date_to_str(
                self.compulsory_insurance_due_date
            ),
            "voluntary_insurance_due_date": _date_to_str(
                self.voluntary_insurance_due_date
            ),
        }

    @classmethod
    def from_row(cls, row: dict) -> "Car":
        """保存されている1行（文字列の辞書）から Car を作り直す。

        古い形式（last_oil_change_date などの列）が残っていても、
        知らない列は単に無視されるので問題ありません。
        """
        return cls(
            id=(row.get("id") or "").strip() or str(uuid.uuid4()),
            name=(row.get("name") or "").strip(),
            plate_number=(row.get("plate_number") or "").strip(),
            inspection_due_date=_str_to_date(row.get("inspection_due_date")),
            owner=(row.get("owner") or "").strip(),
            compulsory_insurance_due_date=_str_to_date(
                row.get("compulsory_insurance_due_date")
            ),
            voluntary_insurance_due_date=_str_to_date(
                row.get("voluntary_insurance_due_date")
            ),
        )


# =====================================================================
# MaintenanceRecord: 整備記録1件分（車の履歴）
# =====================================================================


class RecordType(str, Enum):
    """整備記録の「作業内容」の種類。"""

    OIL = "oil"
    TIRE = "tire"
    INSPECTION = "inspection"
    OTHER = "other"


# 画面表示用の日本語ラベル
RECORD_TYPE_LABELS: dict[RecordType, str] = {
    RecordType.OIL: "オイル交換",
    RecordType.TIRE: "タイヤ交換",
    RecordType.INSPECTION: "車検",
    RecordType.OTHER: "その他",
}

RECORD_FIELDNAMES = ["id", "car_id", "date", "record_type", "cost", "memo"]


@dataclass
class MaintenanceRecord:
    """整備記録1件分（いつ・何を・いくらで・メモ）。"""

    car_id: str            # どの車の記録か（Car.id）
    date: date              # 作業した日
    record_type: RecordType  # オイル交換 / タイヤ交換 / 車検 / その他
    cost: int | None = None  # 費用（円）。未入力なら None
    memo: str = ""           # メモ（任意）
    # id は指定しなければ自動でユニークな文字列が入ります
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_row(self) -> dict[str, str]:
        """保存用に「すべて文字列の1行」に変換する。"""
        return {
            "id": self.id,
            "car_id": self.car_id,
            "date": _date_to_str(self.date),
            "record_type": self.record_type.value,
            "cost": "" if self.cost is None else str(self.cost),
            "memo": self.memo,
        }

    @classmethod
    def from_row(cls, row: dict) -> "MaintenanceRecord":
        """保存されている1行（文字列の辞書）から MaintenanceRecord を作り直す。"""
        return cls(
            id=(row.get("id") or "").strip() or str(uuid.uuid4()),
            car_id=(row.get("car_id") or "").strip(),
            date=_str_to_date(row.get("date")) or date.today(),
            record_type=_str_to_record_type(row.get("record_type")),
            cost=_str_to_cost(row.get("cost")),
            memo=(row.get("memo") or "").strip(),
        )


def _str_to_record_type(s: str | None) -> RecordType:
    """文字列 -> RecordType。知らない値なら「その他」扱いにする。"""
    try:
        return RecordType((s or "").strip())
    except ValueError:
        return RecordType.OTHER


def _str_to_cost(s: str | None) -> int | None:
    """文字列 -> 費用（円）。空や変な値なら None。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


# =====================================================================
# 日付の変換（Car / MaintenanceRecord 共通）
# =====================================================================


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
