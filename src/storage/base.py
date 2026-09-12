"""保存先の「共通ルール（インターフェース）」を決めるファイル。

CSV 版でもスプレッドシート版でも、必ずこの5つのメソッドを持つ、と決めます。
こうしておくと app.py 側は「どこに保存しているか」を気にせず使えます。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Car


class CarStorage(ABC):
    """車データの保存先を表す共通の型。"""

    @abstractmethod
    def list_cars(self) -> list[Car]:
        """登録されている車をすべて返す。"""

    @abstractmethod
    def get_car(self, car_id: str) -> Car | None:
        """id を指定して車を1台返す。無ければ None。"""

    @abstractmethod
    def add_car(self, car: Car) -> None:
        """車を1台追加する。"""

    @abstractmethod
    def update_car(self, car: Car) -> None:
        """既存の車の情報を書き換える（今回の画面では未使用。次のステップ用）。"""

    @abstractmethod
    def delete_car(self, car_id: str) -> None:
        """id を指定して車を削除する。"""
