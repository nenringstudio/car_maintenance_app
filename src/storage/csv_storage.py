"""保存先の「CSVファイル版」。

車の情報は data/cars.csv、整備記録は data/maintenance_records.csv という
2つのテキストファイルに分けて読み書きします（1行 = データ1件）。
中身の考え方（日付は文字列など）はスプレッドシートとほぼ同じなので、
将来の差し替えがしやすくなっています。
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.models import FIELDNAMES, RECORD_FIELDNAMES, Car, MaintenanceRecord
from src.storage.base import CarStorage, MaintenanceRecordStorage
from src.storage.legacy import migrate_legacy_rows_to_records


class CsvCarStorage(CarStorage):
    def __init__(
        self,
        csv_path: str | Path,
        record_storage: MaintenanceRecordStorage | None = None,
    ) -> None:
        self.csv_path = Path(csv_path)
        # 保存先フォルダが無ければ作る
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        # ファイルがまだ無ければ、見出し行だけの空ファイルを作る
        if not self.csv_path.exists():
            self._write_all([])
        else:
            self._migrate_header_if_needed(record_storage)

    def _migrate_header_if_needed(
        self, record_storage: MaintenanceRecordStorage | None
    ) -> None:
        """見出し行（1行目）が今の形と違っていたら、自動で書き直す。

        例えば「担当者」列を新しく追加したときや、逆に「直近のオイル交換日」
        のような古い列を無くしたときに、ここで見出しと中身を揃え直す。
        古い列に日付が入っていれば、消える前に整備記録へ1件移す。
        """
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        if header == FIELDNAMES:
            return

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            raw_rows = list(csv.DictReader(f))

        if raw_rows and record_storage is not None:
            migrate_legacy_rows_to_records(raw_rows, record_storage)

        cars = [Car.from_row(row) for row in raw_rows]
        self._write_all(cars)

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


class CsvMaintenanceRecordStorage(MaintenanceRecordStorage):
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            self._write_all([])
        else:
            self._migrate_header_if_needed()

    def _migrate_header_if_needed(self) -> None:
        """見出し行（1行目）が今の形と違っていたら、自動で書き直す。

        例えば「走行距離」列を新しく追加したときに、ここで見出しと中身を揃え直す。
        """
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f), [])
        if header != RECORD_FIELDNAMES:
            self._write_all(self._read_all())

    # ---- ここから下は「まとめて読み書き」する内部処理 ----

    def _read_all(self) -> list[MaintenanceRecord]:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [MaintenanceRecord.from_row(row) for row in reader]

    def _write_all(self, records: list[MaintenanceRecord]) -> None:
        with self.csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RECORD_FIELDNAMES)
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_row())

    # ---- ここから下が共通ルール（MaintenanceRecordStorage）で決めたメソッド ----

    def list_records(self, car_id: str | None = None) -> list[MaintenanceRecord]:
        records = self._read_all()
        if car_id is not None:
            records = [r for r in records if r.car_id == car_id]
        return records

    def add_record(self, record: MaintenanceRecord) -> None:
        records = self._read_all()
        records.append(record)
        self._write_all(records)

    def delete_record(self, record_id: str) -> None:
        records = [r for r in self._read_all() if r.id != record_id]
        self._write_all(records)

    def delete_records_for_car(self, car_id: str) -> None:
        records = [r for r in self._read_all() if r.car_id != car_id]
        self._write_all(records)
