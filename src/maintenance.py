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
from src.models import Car


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
    """1項目（車検 / オイル交換 / タイヤ交換）の判定結果。"""

    name: str                 # "車検" など
    due_date: date | None     # 期限（次回の目安日）
    days_left: int | None     # 残り日数。マイナスなら超過日数
    status: Status
    is_estimate: bool = False  # True なら「前回＋間隔」で計算した目安


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


def check_car(car: Car, today: date | None = None) -> CarCheck:
    """車1台をチェックして CarCheck を返す。"""
    today = today or date.today()

    # 車検: 記録された期限日をそのまま使う
    inspection = _judge(
        "車検", car.inspection_due_date, config.INSPECTION_WARN_DAYS, today
    )

    # オイル交換: 前回 ＋ 推奨間隔 を次回の目安日にする
    oil_due = (
        add_months(car.last_oil_change_date, config.OIL_CHANGE_INTERVAL_MONTHS)
        if car.last_oil_change_date
        else None
    )
    oil = _judge(
        "オイル交換", oil_due, config.OIL_CHANGE_WARN_DAYS, today, is_estimate=True
    )

    # タイヤ交換: 同上
    tire_due = (
        add_months(car.last_tire_change_date, config.TIRE_CHANGE_INTERVAL_MONTHS)
        if car.last_tire_change_date
        else None
    )
    tire = _judge(
        "タイヤ交換", tire_due, config.TIRE_CHANGE_WARN_DAYS, today, is_estimate=True
    )

    return CarCheck(car=car, items=[inspection, oil, tire])


def check_all(cars: list[Car], today: date | None = None) -> list[CarCheck]:
    """複数台をまとめてチェックし、緊急な順に並べて返す。"""
    today = today or date.today()
    checks = [check_car(c, today) for c in cars]
    checks.sort(key=lambda cc: cc.sort_key)
    return checks
