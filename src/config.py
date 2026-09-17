"""アプリ全体の設定をまとめる場所。

「保存先をどこにするか」などをここで一括管理します。
将来 Google スプレッドシートに切り替えるときも、基本はこのファイルと
storage フォルダだけをいじれば済むようにしてあります。

設定の読み込み順（先に見つかったものを採用）:
  1. 環境変数（例: CAR_APP_BACKEND）
  2. .streamlit/secrets.toml のキー（例: backend）
  3. このファイルに書いた初期値
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

# このプロジェクトの一番上のフォルダ（car_maintenance_app/）
BASE_DIR = Path(__file__).resolve().parent.parent

# .streamlit/secrets.toml があれば読み込んでおく（無くてもOK）
_SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"
try:
    _SECRETS: dict = tomllib.loads(_SECRETS_PATH.read_text(encoding="utf-8"))
except (FileNotFoundError, tomllib.TOMLDecodeError):
    _SECRETS = {}


def _setting(name: str, default: str = "") -> str:
    """設定を1つ取り出す。環境変数 → secrets.toml → 初期値 の順。

    name は小文字で渡す（例: "backend"）。
    環境変数は CAR_APP_BACKEND のように大文字＋接頭辞で探します。
    """
    env_value = os.environ.get(f"CAR_APP_{name.upper()}")
    if env_value:
        return env_value
    if name in _SECRETS:
        return str(_SECRETS[name])
    # [google] セクションの中も見る
    google = _SECRETS.get("google", {})
    if isinstance(google, dict) and name in google:
        return str(google[name])
    return default


# =====================================================================
# 保存先の設定
# =====================================================================

# "csv"（ローカルのCSVファイル） または "gsheets"（Googleスプレッドシート）
DATA_BACKEND = _setting("backend", "csv")

# CSV で保存するときのファイルの場所（car_maintenance_app/data/cars.csv）
CSV_PATH = Path(_setting("csv_path", str(BASE_DIR / "data" / "cars.csv")))

# 整備記録（履歴）を CSV で保存するときのファイルの場所
RECORDS_CSV_PATH = Path(
    _setting("records_csv_path", str(BASE_DIR / "data" / "maintenance_records.csv"))
)


# =====================================================================
# Google スプレッドシート連携の設定（DATA_BACKEND = "gsheets" のとき使用）
# =====================================================================

def _spreadsheet_id() -> str:
    """スプレッドシートの ID。URL を貼っても ID を取り出せるようにする。"""
    raw = _setting("spreadsheet_id") or _setting("spreadsheet_url")
    if "/spreadsheets/d/" in raw:
        # https://docs.google.com/spreadsheets/d/<ここがID>/edit... から抜き出す
        return raw.split("/spreadsheets/d/")[1].split("/")[0]
    return raw


SPREADSHEET_ID = _spreadsheet_id()

# シート（タブ）の名前。無ければアプリが自動で作ります。
WORKSHEET_NAME = _setting("worksheet_name", "cars")

# 整備記録（履歴）用のシート（タブ）の名前。無ければアプリが自動で作ります。
RECORDS_WORKSHEET_NAME = _setting("records_worksheet_name", "maintenance_records")


def _client_secret_path() -> Path:
    """OAuth クライアントのカギ（client_secret_*.json）の場所を探す。"""
    explicit = _setting("google_client_secret_path")
    if explicit:
        return Path(explicit)
    candidates = sorted(BASE_DIR.glob("client_secret_*.json"))
    if candidates:
        return candidates[0]
    return BASE_DIR / "client_secret.json"  # 見つからない場合の仮の場所


GOOGLE_CLIENT_SECRET_PATH = _client_secret_path()

# ログイン結果（トークン）の保存場所。ここは絶対に GitHub に上げない。
GOOGLE_TOKEN_PATH = Path(
    _setting("google_token_path", str(BASE_DIR / ".streamlit" / "token.json"))
)

# デプロイ時用: トークンの中身を文字列で直接渡したいとき（Streamlit Cloud の Secrets など）
# secrets.toml では [google] セクションの token_json に書く想定
GOOGLE_TOKEN_JSON = _setting("token_json")

# Google に許可をもらう範囲：スプレッドシートの読み書きのみ
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# =====================================================================
# 担当者タグの設定
#
# 車を登録するときに選べる「担当者」の選択肢です。
# 増やしたり減らしたり、名前を変えたりしたいときは、このリストを直接編集してください。
# （例: 名前を変える、増やす、減らす、など）
# =====================================================================

PERSON_IN_CHARGE = ["和男", "幸子", "紘子", "英紀"]


# =====================================================================
# 期限チェックの設定（ステップ2で使用）
#
# ・「あと何日で警告(黄色)にするか」＝ WARN_DAYS
# ・オイル/タイヤは「前回の日付」しか記録しないので、
#   「前回 ＋ 推奨間隔（月）」を次回の目安日として計算します。
#   家庭の使い方に合わせて数字を変えてOKです。
# =====================================================================

# --- 車検 ---
# 車検は「期限日」そのものを記録しているので間隔の設定は不要。
INSPECTION_WARN_DAYS = 60          # 期限まで60日以内になったら黄色

# --- オイル交換（月数） ---
OIL_CHANGE_INTERVAL_MONTHS = 6     # 前回から6か月で交換の目安
OIL_CHANGE_WARN_DAYS = 30          # 目安日まで30日以内になったら黄色

# --- オイル交換（距離） ---
# 月数と距離、早く来た方（悪い方）の状態が採用されます。
# 走行距離は「車ごとの現在の総走行距離」と「オイル交換時に記録した距離」の差で計算します。
# どちらかが未入力のときは、距離での判定はできません（月数だけで判定）。
OIL_CHANGE_WARN_KM = 5000          # 前回交換から5000km走ったら黄色
OIL_CHANGE_OVERDUE_KM = 6000       # 前回交換から6000km走ったら赤

# --- タイヤ交換 ---
# 夏タイヤ⇔冬タイヤの入れ替えなら 6 くらい、
# すり減りによる買い替え目安なら 48〜60（4〜5年）くらいに変更してください。
TIRE_CHANGE_INTERVAL_MONTHS = 6
TIRE_CHANGE_WARN_DAYS = 30

# --- 自動車税 ---
# 車ごとの日付は持たず、「毎年○月○日」を目安に自動で判定します。
# （初期値: 5月31日。都道府県によって多少前後する場合は日付を調整してください）
VEHICLE_TAX_DUE_MONTH = 5
VEHICLE_TAX_DUE_DAY = 31
VEHICLE_TAX_WARN_DAYS = 60         # 目安日まで60日以内になったら黄色

# --- 自賠責保険 ---
# 満期日は車ごとに直接入力します（車検と同じ扱い）。
COMPULSORY_INSURANCE_WARN_DAYS = 60

# --- 任意保険 ---
# 満期日は車ごとに直接入力します（車検と同じ扱い）。
VOLUNTARY_INSURANCE_WARN_DAYS = 60
