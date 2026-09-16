"""期限が近いかどうかを判定する部分。

画面(app.py)からは切り離してあります。
・app.py …… 色をつけて「見せる」役
・このファイル …… 「あと何日か」「危ないか」を計算する役
将来のメール通知(ステップ4)でも、この計算部分をそのまま使い回せます。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from enum import Enum

from src import config
from src.models import Car, MaintenanceRecord, RecordType


class Status(str, Enum):
    """1項目の状態。"""

    OVERDUE = "overdue"    # 期限切れ
    SOON = "soon"          # 期限が近い
    OK = "ok"              # まだ余裕
    UNKNOWN = "unknown"    # 日付が未入力


# 表示用の対応表（app.py から使う）
STATUS_LABEL = {
    Status.OVERDUE: "期限切れ",
    Status.SOON: "期限が近い",
    Status.OK: "まだ余裕",
    Status.UNKNOWN: "未設定",
}
STATUS_EMOJI = {
    Status.OVERDUE: "🔴",
    Status.SOON: "🟡",
    Status.OK: "🟢",
    Status.UNKNOWN: "⚪",
}
# Streamlit の色つき文字 :red[...] などに使う色名
STATUS_COLOR = {
    Status.OVERDUE: "red",
    Status.SOON: "orange",
    Status.OK: "green",
    Status.UNKNOWN: "gray",
}
# 並べ替え用の緊急度（数字が小さいほど緊急）
_STATUS_ORDER = {
    Status.OVERDUE: 0,
    Status.SOON: 1,
    Status.OK: 2,
    Status.UNKNOWN: 3,
}


@dataclass
class ItemCheck:
    """1項目（車検 / オイル交換 / タイヤ交換 など）の判定結果。"""

    name: str                 # "車検" など
    due_date: date | None     # 期限（次回の目安日）。日数で判定する項目のみ
    days_left: int | None     # 残り日数。マイナスなら超過日数
    status: Status
    is_estimate: bool = False  # True なら「前回＋間隔」で計算した目安
    distance_left_km: int | None = None
    # ↑ 距離でも判定する項目（オイル交換）だけ使う。
    #   プラスなら次の節目まであと何km、マイナスなら超過km。


@dataclass
class CarCheck:
    """車1台分の判定結果。"""

    car: Car
    items: list[ItemCheck]

    @property
    def status(self) -> Status:
        """車全体の状態＝一番緊急な項目の状態。"""
        known = [i.status for i in self.items if i.status != Status.UNKNOWN]
        if not known:
            return Status.UNKNOWN
        return min(known, key=lambda s: _STATUS_ORDER[s])

    @property
    def sort_key(self) -> tuple:
        """緊急な車を上に並べるための並べ替えキー。"""
        soonest = min(
            (i.days_left for i in self.items if i.days_left is not None),
            default=10**9,
        )
        return (_STATUS_ORDER[self.status], soonest)

    def item(self, name: str) -> ItemCheck:
        """名前（"車検" など）で該当する項目を取り出す。"""
        for i in self.items:
            if i.name == name:
                return i
        raise KeyError(name)


def add_months(d: date, months: int) -> date:
    """日付に「月」を足す。月末は自動調整（例: 8/31 + 6か月 = 2/28）。"""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _judge(name, due_date, warn_days, today, *, is_estimate=False) -> ItemCheck:
    if due_date is None:
        return ItemCheck(name, None, None, Status.UNKNOWN, is_estimate)
    days_left = (due_date - today).days
    if days_left < 0:
        status = Status.OVERDUE
    elif days_left <= warn_days:
        status = Status.SOON
    else:
        status = Status.OK
    return ItemCheck(name, due_date, days_left, status, is_estimate)


def _worse_status(a: Status, b: Status) -> Status:
    """2つの状態のうち、より緊急な方（悪い方）を返す。"""
    return min(a, b, key=lambda s: _STATUS_ORDER[s])


def _latest_record(
    records: list[MaintenanceRecord], record_type: RecordType
) -> MaintenanceRecord | None:
    """指定した作業内容の記録の中で、一番新しい日付のものを返す（無ければ None）。"""
    matching = [r for r in records if r.record_type == record_type]
    return max(matching, key=lambda r: r.date) if matching else None


def _judge_km(
    current_km: int | None, last_km: int | None, warn_km: int, overdue_km: int
) -> tuple[Status, int | None]:
    """距離基準の判定（例: オイル交換）。

    前回からの走行距離が warn_km を超えたら黄色、overdue_km を超えたら赤。
    現在の走行距離・前回の走行距離のどちらかが未入力なら判定できない（未設定扱い）。
    戻り値の2つめは「次の節目まであと何km」（マイナスなら超過km）。
    """
    if current_km is None or last_km is None:
        return Status.UNKNOWN, None
    traveled = current_km - last_km
    if traveled > overdue_km:
        return Status.OVERDUE, overdue_km - traveled
    elif traveled > warn_km:
        return Status.SOON, overdue_km - traveled
    else:
        return Status.OK, warn_km - traveled


def next_annual_due(today: date, month: int, day: int) -> date:
    """「毎年○月○日」の、次に来る日付を返す。

    今年のその日がもう過ぎていたら、来年の同じ日を返す
    （例: 今日が6月なら、次の自動車税は来年の5月31日）。
    """
    candidate = date(today.year, month, day)
    if candidate < today:
        candidate = date(today.year + 1, month, day)
    return candidate


def check_car(
    car: Car, records: list[MaintenanceRecord], today: date | None = None
) -> CarCheck:
    """車1台をチェックして CarCheck を返す。

    records には全車ぶんの整備記録を渡してよい（内部で car.id の分だけ絞り込む）。
    """
    today = today or date.today()
    car_records = [r for r in records if r.car_id == car.id]

    # 車検: 記録された期限日をそのまま使う（履歴とは別に、車ごとに直接持つ値）
    inspection = _judge(
        "車検", car.inspection_due_date, config.INSPECTION_WARN_DAYS, today
    )

    # 自動車税: 車ごとの日付は持たず、「次に来る○月○日」を自動計算する
    tax_due = next_annual_due(
        today, config.VEHICLE_TAX_DUE_MONTH, config.VEHICLE_TAX_DUE_DAY
    )
    vehicle_tax = _judge(
        "自動車税", tax_due, config.VEHICLE_TAX_WARN_DAYS, today, is_estimate=True
    )

    # 自賠責保険 / 任意保険: 車検と同じく、満期日をそのまま使う
    compulsory_insurance = _judge(
        "自賠責保険",
        car.compulsory_insurance_due_date,
        config.COMPULSORY_INSURANCE_WARN_DAYS,
        today,
    )
    voluntary_insurance = _judge(
        "任意保険",
        car.voluntary_insurance_due_date,
        config.VOLUNTARY_INSURANCE_WARN_DAYS,
        today,
    )

    # オイル交換: 月数 と 距離 の両方で判定し、早く来た方（悪い方）を採用する
    last_oil_record = _latest_record(car_records, RecordType.OIL)
    last_oil_date = last_oil_record.date if last_oil_record else None
    oil_due = (
        add_months(last_oil_date, config.OIL_CHANGE_INTERVAL_MONTHS)
        if last_oil_date
        else None
    )
    oil_by_date = _judge(
        "オイル交換", oil_due, config.OIL_CHANGE_WARN_DAYS, today, is_estimate=True
    )

    last_oil_km = last_oil_record.odometer_km if last_oil_record else None
    oil_km_status, oil_distance_left_km = _judge_km(
        car.current_odometer_km,
        last_oil_km,
        config.OIL_CHANGE_WARN_KM,
        config.OIL_CHANGE_OVERDUE_KM,
    )

    oil = ItemCheck(
        name="オイル交換",
        due_date=oil_by_date.due_date,
        days_left=oil_by_date.days_left,
        status=_worse_status(oil_by_date.status, oil_km_status),
        is_estimate=True,
        distance_left_km=oil_distance_left_km,
    )

    # タイヤ交換: オイルと同じく、記録の中で一番新しい日付 ＋ 推奨間隔（距離での判定はなし）
    last_tire_record = _latest_record(car_records, RecordType.TIRE)
    last_tire = last_tire_record.date if last_tire_record else None
    tire_due = (
        add_months(last_tire, config.TIRE_CHANGE_INTERVAL_MONTHS) if last_tire else None
    )
    tire = _judge(
        "タイヤ交換", tire_due, config.TIRE_CHANGE_WARN_DAYS, today, is_estimate=True
    )

    return CarCheck(
        car=car,
        items=[
            inspection,
            vehicle_tax,
            compulsory_insurance,
            voluntary_insurance,
            oil,
            tire,
        ],
    )


def check_all(
    cars: list[Car], records: list[MaintenanceRecord], today: date | None = None
) -> list[CarCheck]:
    """複数台をまとめてチェックし、緊急な順に並べて返す。"""
    today = today or date.today()
    checks = [check_car(c, records, today) for c in cars]
    checks.sort(key=lambda cc: cc.sort_key)
    return checks
