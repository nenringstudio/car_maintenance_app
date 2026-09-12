"""保存先の「CSVファイル版」。

data/cars.csv というテキストファイルに、1行 = 車1台 で読み書きします。
中身の考え方（1行=1台、日付は文字列）はスプレッドシートとほぼ同じなので、
将来の差し替えがしやすくなっています。
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.models import FIELDNAMES, Car
from src.storage.base import CarStorage


class CsvCarStorage(CarStorage):
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        # 保存先フォルダが無ければ作る
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        # ファイルがまだ無ければ、見出し行だけの空ファイルを作る
        if not self.csv_path.exists():
            self._write_all([])

    # ---- ここから下は「まとめて読み書き」する内部処理 ----

    def _read_all(self) -> list[Car]:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [Car.from_row(row) for row in reader]

    def _write_all(self, cars: list[Car]) -> None:
        with self.csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for car in cars:
                writer.writerow(car.to_row())

    # ---- ここから下が共通ルール（CarStorage）で決めたメソッド ----

    def list_cars(self) -> list[Car]:
        return self._read_all()

    def get_car(self, car_id: str) -> Car | None:
        for car in self._read_all():
            if car.id == car_id:
                return car
        return None

    def add_car(self, car: Car) -> None:
        cars = self._read_all()
        cars.append(car)
        self._write_all(cars)

    def update_car(self, car: Car) -> None:
        cars = self._read_all()
        for i, existing in enumerate(cars):
            if existing.id == car.id:
                cars[i] = car
                self._write_all(cars)
                return
        raise ValueError(f"更新対象の車が見つかりません: {car.id}")

    def delete_car(self, car_id: str) -> None:
        cars = [c for c in self._read_all() if c.id != car_id]
        self._write_all(cars)
