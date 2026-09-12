"""【初回に1回だけ】Google アカウントでログインして、トークンを保存するスクリプト。

使い方（ターミナルで）:
    python scripts/authorize_google.py

やること:
  1. ブラウザが開くので、スプレッドシートを持っている自分の Google アカウントを選ぶ
  2. 「このアプリを許可しますか？」で許可する
  3. ログイン結果（トークン）が .streamlit/token.json に保存される

一度実行すれば、あとはアプリ側が自動でトークンを使います
（期限切れも自動で更新されるので、基本もう実行不要）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# このスクリプトを直接叩いても src/ を import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from src import config  # noqa: E402


def main() -> None:
    secret_path = config.GOOGLE_CLIENT_SECRET_PATH
    if not secret_path.exists():
        print("❌ OAuth クライアントのカギが見つかりません。")
        print(f"   探した場所: {secret_path}")
        print("   Google Cloud でダウンロードした client_secret_*.json を")
        print("   プロジェクト直下（car_maintenance_app/）に置いてください。")
        sys.exit(1)

    print(f"使用するカギ : {secret_path.name}")
    print("ブラウザが開きます。スプレッドシートを持っている Google アカウントで許可してください…\n")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secret_path), scopes=config.GOOGLE_SCOPES
    )
    # port=0 で空いているポートを自動選択。ローカルで完結します。
    creds = flow.run_local_server(port=0, prompt="consent")

    token_path = config.GOOGLE_TOKEN_PATH
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")

    print("\n✅ ログイン成功！トークンを保存しました。")
    print(f"   保存先: {token_path}")
    print("   （このファイルは .gitignore 済み。GitHub には上がりません）")
    if config.SPREADSHEET_ID:
        print(f"   使うスプレッドシート ID: {config.SPREADSHEET_ID}")
    else:
        print("   次は .streamlit/secrets.toml に spreadsheet_id を設定してください。")


if __name__ == "__main__":
    main()
