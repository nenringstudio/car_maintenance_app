"""保存先の「Google スプレッドシート版」。

CSV 版(csv_storage.py)とまったく同じ5つのメソッドを持つので、
app.py から見れば CSV かスプレッドシートかを気にせず使えます。

・列の並びは CSV と同じ（models.py の FIELDNAMES）
・1行目 = 見出し、2行目以降 = 車1台ずつ
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
from src.models import FIELDNAMES, Car
from src.storage.base import CarStorage

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


class GoogleSheetsCarStorage(CarStorage):
    def __init__(
        self,
        spreadsheet_id: str | None = None,
        worksheet_name: str | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or config.SPREADSHEET_ID
        self.worksheet_name = worksheet_name or config.WORKSHEET_NAME
        if not self.spreadsheet_id:
            raise RuntimeError(
                "スプレッドシートの ID が設定されていません。\n"
                ".streamlit/secrets.toml に spreadsheet_id または spreadsheet_url を書いてください。"
            )
        self._ws = None  # 実際の接続は最初に使うときまで遅らせる

    # ---------------------------------------------------------------
    # 接続まわり（内部処理）
    # ---------------------------------------------------------------

    def _credentials(self) -> Credentials:
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
                    config.GOOGLE_TOKEN_PATH.write_text(
                        creds.to_json(), encoding="utf-8"
                    )
            else:
                raise RuntimeError(
                    "Google のログイン情報が古くなっています。\n"
                    "もう一度 `python scripts/authorize_google.py` を実行してください。"
                )
        return creds

    def _worksheet(self):
        """使うシート（タブ）を返す。無ければ作り、見出し行も用意する。"""
        if self._ws is not None:
            return self._ws

        client = gspread.authorize(self._credentials())

        try:
            spreadsheet = client.open_by_key(self.spreadsheet_id)
        except SpreadsheetNotFound as ex:
            raise RuntimeError(
                "スプレッドシートが見つかりません。\n"
                f"指定している ID: {self.spreadsheet_id}\n"
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

        try:
            ws = spreadsheet.worksheet(self.worksheet_name)
        except WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                title=self.worksheet_name, rows=100, cols=len(FIELDNAMES)
            )

        # 1行目が空なら見出しを書き込む
        first_row = ws.row_values(1)
        if first_row != FIELDNAMES:
            ws.update([FIELDNAMES], range_name="A1", value_input_option="RAW")

        self._ws = ws
        return ws

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
        last_col = chr(ord("A") + len(FIELDNAMES) - 1)  # 例: "F"
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
