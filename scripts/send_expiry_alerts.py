"""期限が近い/過ぎている車があれば、メールで知らせるスクリプト。

GitHub Actions から毎週1回自動実行される想定ですが、ターミナルで
    python scripts/send_expiry_alerts.py
と実行すれば手元でも試せます（🔴🟡の車が無ければ何も送られません）。

このスクリプトが使う設定（環境変数）:
  - CAR_APP_BACKEND        … "gsheets" にしておく
  - CAR_APP_SPREADSHEET_URL または CAR_APP_SPREADSHEET_ID … 対象のスプレッドシート
  - CAR_APP_TOKEN_JSON     … Google へのログイン情報（.streamlit/secrets.cloud.toml の
                              [google] token_json と同じ中身）
  - GMAIL_ADDRESS          … 送信元の Gmail アドレス
  - GMAIL_APP_PASSWORD     … Gmail の「アプリパスワード」（16桁、スペース無し）
  - ALERT_EMAIL_TO         … 送信先のメールアドレス（複数宛てたいときはカンマ区切り。
                              例: "a@example.com,b@example.com"）

これらは GitHub Actions 上では GitHub Secrets から渡します
（.github/workflows/check_expiry.yml を参照）。
ローカルで試す場合は、ターミナルで一時的に環境変数を設定してから実行してください。
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

# このスクリプトを直接叩いても src/ を import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import maintenance  # noqa: E402
from src.maintenance import CarCheck, Status  # noqa: E402
from src.storage import get_storages  # noqa: E402

ALERT_STATUSES = (Status.OVERDUE, Status.SOON)

# アプリのURL（メール本文の最後に案内として載せる）
APP_URL = "https://carmaintenanceapp-52pjmtle42xaqgdbdhxrhx.streamlit.app/"


def _item_alert_line(item: maintenance.ItemCheck) -> str:
    """1項目（車検など）を、メール本文用の1行テキストにする。

    詳しい文章の組み立ては src/maintenance.py の item_detail_text() に
    まとめてあり、アプリ画面（app.py）と共用しています。
    """
    emoji = maintenance.STATUS_EMOJI[item.status]
    detail = maintenance.item_detail_text(item)
    return f"　{emoji} {item.name}：{detail}"


def _car_alert_block(cc: CarCheck) -> str:
    """1台分を、メール本文用の段落にする（🔴🟡の項目だけ載せる）。"""
    car = cc.car
    title = f"■ {car.name}"
    if car.owner:
        title += f"（担当: {car.owner}）"
    if car.plate_number:
        title += f" / {car.plate_number}"
    lines = [title]
    for item in cc.items:
        if item.status in ALERT_STATUSES:
            lines.append(_item_alert_line(item))
    return "\n".join(lines)


def build_email_body(alert_checks: list[CarCheck]) -> str:
    """要確認の車たちから、メール本文をまとめて作る。"""
    blocks = [_car_alert_block(cc) for cc in alert_checks]
    return (
        "車の情報管理アプリからの自動通知です。\n"
        "以下の車で、期限切れ（🔴）または期限が近い（🟡）項目があります。\n\n"
        + "\n\n".join(blocks)
        + "\n\n---\n"
        + f"詳細はこちらから確認してください：\n{APP_URL}\n\n"
        + "このメールは GitHub Actions から毎週自動送信されています。"
    )


def _recipients() -> list[str]:
    """ALERT_EMAIL_TO をカンマ区切りで複数アドレスに分ける。"""
    raw = os.environ["ALERT_EMAIL_TO"]
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def send_email(subject: str, body: str) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipients = _recipients()

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, app_password)
        server.send_message(msg, to_addrs=recipients)


def main() -> None:
    storage, record_storage = get_storages()
    cars = storage.list_cars()
    records = record_storage.list_records()
    checks = maintenance.check_all(cars, records)

    alert_checks = [cc for cc in checks if cc.status in ALERT_STATUSES]

    if not alert_checks:
        print("対応が必要な車はありません。メールは送信しません。")
        return

    overdue_count = sum(1 for cc in alert_checks if cc.status == Status.OVERDUE)
    soon_count = sum(1 for cc in alert_checks if cc.status == Status.SOON)
    subject = (
        f"【車メンテ】要確認の車が{len(alert_checks)}台あります"
        f"（期限切れ{overdue_count}台・期限が近い{soon_count}台）"
    )
    body = build_email_body(alert_checks)

    send_email(subject, body)
    print(f"メールを送信しました。宛先: {', '.join(_recipients())}")
    print(f"対象: {len(alert_checks)}台")
    for cc in alert_checks:
        print(f"  - {maintenance.STATUS_EMOJI[cc.status]} {cc.car.name}")


if __name__ == "__main__":
    main()
