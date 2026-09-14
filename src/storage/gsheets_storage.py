"""保存先の「Google スプレッドシート版」。

CSV 版(csv_storage.py)とまったく同じメソッドを持つので、
app.py から見れば CSV かスプレッドシートかを気にせず使えます。

・車の情報は "cars" シート、整備記録は "maintenance_records" シートに分けて保存
・列の並びは CSV と同じ（models.py の FIELDNAMES / RECORD_FIELDNAMES）
・1行目 = 見出し、2行目以降 = データ1件ずつ
・日付は "2026-11-20" の形の文字列でそのまま入れる（RAW）

ログイン（OAuth）について:
  初回だけターミナルで `python scripts/authorize_google.py` を実行し、
  ブラウザで自分の Google アカウントを許可します。
  その結果（トークン）が .streamlit/token.json に保存され、
  以降はブラウザなしで自動的に使われます（期限切れも自動更新）。
"""
from __future__ import annotations

import json

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src import config
from src.models import FIELDNAMES, RECORD_FIELDNAMES, Car, MaintenanceRecord
from src.storage.base import CarStorage, MaintenanceRecordStorage
from src.storage.legacy import migrate_legacy_rows_to_records

# gspread の例外（バージョン差を吸収）
try:  # gspread 6.x
    from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
except ImportError:  # 念のため
    APIError = Exception  # type: ignore
    SpreadsheetNotFound = Exception  # type: ignore
    WorksheetNotFound = Exception  # type: ignore


def _api_error_message(ex: BaseException) -> str:
    """Google から返ってきたエラーの詳細メッセージを取り出す（無ければ空文字）。"""
    response = getattr(ex, "response", None)
    if response is None:
        return ""
    try:
        return response.json().get("error", {}).get("message", "")
    except Exception:
        return getattr(response, "text", "") or ""


# =========================================================================
# 接続まわり（CarStorage / MaintenanceRecordStorage 共通の内部処理）
# =========================================================================


def _credentials() -> Credentials:
    """保存済みトークンを読み込む。期限切れなら自動更新する。"""
    info = None
    if config.GOOGLE_TOKEN_JSON:
        info = json.loads(config.GOOGLE_TOKEN_JSON)
    elif config.GOOGLE_TOKEN_PATH.exists():
        info = json.loads(config.GOOGLE_TOKEN_PATH.read_text(encoding="utf-8"))

    if not info:
        raise RuntimeError(
            "Google へのログインがまだです。\n"
            "ターミナルで次を1回だけ実行してください:\n"
            "    python scripts/authorize_google.py"
        )

    creds = Credentials.from_authorized_user_info(info, config.GOOGLE_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # 更新後のトークンをファイルに書き戻す（ファイル運用のときだけ）
            if not config.GOOGLE_TOKEN_JSON and config.GOOGLE_TOKEN_PATH.exists():
                config.GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                "Google のログイン情報が古くなっています。\n"
                "もう一度 `python scripts/authorize_google.py` を実行してください。"
            )
    return creds


def _open_spreadsheet(client: gspread.Client, spreadsheet_id: str):
    """スプレッドシートを開く。よくあるエラーは分かりやすいメッセージにする。"""
    try:
        return client.open_by_key(spreadsheet_id)
    except SpreadsheetNotFound as ex:
        raise RuntimeError(
            "スプレッドシートが見つかりません。\n"
            f"指定している ID: {spreadsheet_id}\n"
            ".streamlit/secrets.toml の spreadsheet_url が正しいか確認してください。"
        ) from ex
    except PermissionError as ex:
        detail = _api_error_message(ex.__cause__ or ex)
        msg = (
            "スプレッドシートを開く権限がありません（403 Forbidden）。\n"
            "考えられる原因を上から順に確認してください。\n\n"
            "① Google Sheets API が有効化されていない\n"
            "    → Google Cloud Console →「APIとサービス」→「有効なAPIとサービス」で\n"
            "      'Google Sheets API' が有効になっているか確認してください。\n\n"
            "② python scripts/authorize_google.py を実行したときに、\n"
            "    このスプレッドシートを持っているのと別の Google アカウントでログインした\n"
            "    → .streamlit/token.json を削除してから\n"
            "      python scripts/authorize_google.py をもう一度実行し、\n"
            "      スプレッドシートの持ち主のアカウントでログインし直してください。\n\n"
            "③ .streamlit/secrets.toml の spreadsheet_url が別のシートを指している"
        )
        if detail:
            msg += f"\n\n（Googleからのエラー詳細: {detail}）"
        raise RuntimeError(msg) from ex
    except APIError as ex:
        detail = _api_error_message(ex) or str(ex)
        raise RuntimeError(
            f"Google スプレッドシートへの接続でエラーが発生しました。\n{detail}"
        ) from ex


def _get_or_create_worksheet(spreadsheet, worksheet_name: str, cols: int):
    """指定した名前のシート（タブ）を返す。無ければ新しく作る。"""
    try:
        return spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=cols)


def _last_column_letter(fieldnames: list[str]) -> str:
    """列の数から最後の列の記号を作る（例: 6列なら "F"）。26列までの想定。"""
    return chr(ord("A") + len(fieldnames) - 1)


# =========================================================================
# GoogleSheetsCarStorage: 車の情報
# =========================================================================


class GoogleSheetsCarStorage(CarStorage):
    def __init__(
        self,
        spreadsheet_id: str | None = None,
        worksheet_name: str | None = None,
        record_storage: MaintenanceRecordStorage | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or config.SPREADSHEET_ID
        self.worksheet_name = worksheet_name or config.WORKSHEET_NAME
        self.record_storage = record_storage
        if not self.spreadsheet_id:
            raise RuntimeError(
                "スプレッドシートの ID が設定されていません。\n"
                ".streamlit/secrets.toml に spreadsheet_id または spreadsheet_url を書いてください。"
            )
        self._ws = None  # 実際の接続は最初に使うときまで遅らせる

    def _worksheet(self):
        """使うシート（タブ）を返す。無ければ作り、見出し行も揃える。"""
        if self._ws is not None:
            return self._ws

        client = gspread.authorize(_credentials())
        spreadsheet = _open_spreadsheet(client, self.spreadsheet_id)
        ws = _get_or_create_worksheet(spreadsheet, self.worksheet_name, len(FIELDNAMES))
        self._sync_header(ws)

        self._ws = ws
        return ws

    def _sync_header(self, ws) -> None:
        """見出し行が今の形と違っていたら、シート全体を今の形に書き直す。

        列を追加しただけのときも、逆に「直近のオイル交換日」のような
        古い列を無くしたときも、これで対応できる。
        古い列に日付が入っていれば、消える前に整備記録へ1件移す。
        """
        first_row = ws.row_values(1)
        if first_row == FIELDNAMES:
            return

        raw_rows = ws.get_all_records(numericise_ignore=["all"]) if first_row else []

        if raw_rows and self.record_storage is not None:
            migrate_legacy_rows_to_records(raw_rows, self.record_storage)

        cars = [Car.from_row(row) for row in raw_rows]
        grid = [FIELDNAMES] + [
            [car.to_row()[name] for name in FIELDNAMES] for car in cars
        ]
        ws.clear()
        ws.update(grid, range_name="A1", value_input_option="RAW")

    def _rows(self) -> list[dict]:
        """データ部分を辞書のリストで返す（すべて文字列のまま）。"""
        return self._worksheet().get_all_records(numericise_ignore=["all"])

    def _row_number_of(self, car_id: str) -> int | None:
        """指定 id の車が何行目にあるか（見出しが1行目なので2始まり）。"""
        cell = self._worksheet().find(car_id, in_column=1)
        return cell.row if cell else None

    # ---------------------------------------------------------------
    # ここからが共通ルール（CarStorage）で決めたメソッド
    # ---------------------------------------------------------------

    def list_cars(self) -> list[Car]:
        return [Car.from_row(row) for row in self._rows()]

    def get_car(self, car_id: str) -> Car | None:
        for car in self.list_cars():
            if car.id == car_id:
                return car
        return None

    def add_car(self, car: Car) -> None:
        row = car.to_row()
        self._worksheet().append_row(
            [row[name] for name in FIELDNAMES], value_input_option="RAW"
        )

    def update_car(self, car: Car) -> None:
        row_number = self._row_number_of(car.id)
        if row_number is None:
            raise ValueError(f"更新対象の車が見つかりません: {car.id}")
        row = car.to_row()
        last_col = _last_column_letter(FIELDNAMES)
        self._worksheet().update(
            [[row[name] for name in FIELDNAMES]],
            range_name=f"A{row_number}:{last_col}{row_number}",
            value_input_option="RAW",
        )

    def delete_car(self, car_id: str) -> None:
        row_number = self._row_number_of(car_id)
        if row_number is None:
            return  # すでに無ければ何もしない
        self._worksheet().delete_rows(row_number)


# =========================================================================
# GoogleSheetsMaintenanceRecordStorage: 整備記録（履歴）
# =========================================================================


class GoogleSheetsMaintenanceRecordStorage(MaintenanceRecordStorage):
    def __init__(
        self,
        spreadsheet_id: str | None = None,
        worksheet_name: str | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or config.SPREADSHEET_ID
        self.worksheet_name = worksheet_name or config.RECORDS_WORKSHEET_NAME
        if not self.spreadsheet_id:
            raise RuntimeError(
                "スプレッドシートの ID が設定されていません。\n"
                ".streamlit/secrets.toml に spreadsheet_id または spreadsheet_url を書いてください。"
            )
        self._ws = None

    def _worksheet(self):
        if self._ws is not None:
            return self._ws

        client = gspread.authorize(_credentials())
        spreadsheet = _open_spreadsheet(client, self.spreadsheet_id)
        ws = _get_or_create_worksheet(
            spreadsheet, self.worksheet_name, len(RECORD_FIELDNAMES)
        )

        first_row = ws.row_values(1)
        if first_row != RECORD_FIELDNAMES:
            ws.update([RECORD_FIELDNAMES], range_name="A1", value_input_option="RAW")

        self._ws = ws
        return ws

    def _rows(self) -> list[dict]:
        return self._worksheet().get_all_records(numericise_ignore=["all"])

    def _row_number_of(self, record_id: str) -> int | None:
        cell = self._worksheet().find(record_id, in_column=1)
        return cell.row if cell else None

    # ---------------------------------------------------------------
    # ここからが共通ルール（MaintenanceRecordStorage）で決めたメソッド
    # ---------------------------------------------------------------

    def list_records(self, car_id: str | None = None) -> list[MaintenanceRecord]:
        records = [MaintenanceRecord.from_row(row) for row in self._rows()]
        if car_id is not None:
            records = [r for r in records if r.car_id == car_id]
        return records

    def add_record(self, record: MaintenanceRecord) -> None:
        row = record.to_row()
        self._worksheet().append_row(
            [row[name] for name in RECORD_FIELDNAMES], value_input_option="RAW"
        )

    def delete_record(self, record_id: str) -> None:
        row_number = self._row_number_of(record_id)
        if row_number is None:
            return
        self._worksheet().delete_rows(row_number)

    def delete_records_for_car(self, car_id: str) -> None:
        # 該当する行を後ろから消す（前から消すと行番号がずれるため）
        rows_to_delete = [
            i + 2  # 1行目は見出しなので、データは2行目から
            for i, row in enumerate(self._rows())
            if (row.get("car_id") or "").strip() == car_id
        ]
        for row_number in sorted(rows_to_delete, reverse=True):
            self._worksheet().delete_rows(row_number)
