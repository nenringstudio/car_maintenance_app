"""保存先の「共通ルール（インターフェース）」を決めるファイル。

CSV 版でもスプレッドシート版でも、必ず同じメソッドを持つ、と決めます。
こうしておくと app.py 側は「どこに保存しているか」を気にせず使えます。

保存先は2種類あります。
  ・CarStorage …………………… 車の基本情報の保存先
  ・MaintenanceRecordStorage … 整備記録（履歴）の保存先
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Car, MaintenanceRecord


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


class MaintenanceRecordStorage(ABC):
    """整備記録（履歴）の保存先を表す共通の型。"""

    @abstractmethod
    def list_records(self, car_id: str | None = None) -> list[MaintenanceRecord]:
        """整備記録を返す。car_id を指定すれば、その車の分だけ返す。"""

    @abstractmethod
    def add_record(self, record: MaintenanceRecord) -> None:
        """整備記録を1件追加する。"""

    @abstractmethod
    def delete_record(self, record_id: str) -> None:
        """id を指定して整備記録を1件削除する。"""

    @abstractmethod
    def delete_records_for_car(self, car_id: str) -> None:
        """指定した車の整備記録をすべて削除する（車を削除するときに使う）。"""
