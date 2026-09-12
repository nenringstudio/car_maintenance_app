"""家族用 車の情報管理アプリ

ステップ2まで:
  ・車の情報を「登録」して「一覧表示」する
  ・車検 / オイル交換 / タイヤ交換 の期限が近い車を色分けで表示する
（メール送信は次のステップで追加します）

起動方法（ターミナルで）:
    streamlit run app.py
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import maintenance
from src.maintenance import Status
from src.models import Car
from src.storage import get_storage


def _show(value: date | None) -> str:
    """日付を画面表示用の文字列にする。未設定なら「未設定」。"""
    return value.strftime("%Y/%m/%d") if value else "未設定"


def _item_line(item: maintenance.ItemCheck) -> str:
    """1項目（車検など）を、色つきの1行テキストにする。"""
    emoji = maintenance.STATUS_EMOJI[item.status]
    color = maintenance.STATUS_COLOR[item.status]

    if item.status == Status.UNKNOWN:
        return f"{emoji} **{item.name}**：:gray[未設定]"

    when = item.due_date.strftime("%Y/%m/%d")
    suffix = "・目安" if item.is_estimate else ""
    if item.status == Status.OVERDUE:
        detail = f"{when}{suffix} を {abs(item.days_left)}日 超過"
    else:
        detail = f"あと {item.days_left}日（{when}{suffix}）"
    return f"{emoji} **{item.name}**：:{color}[{detail}]"


# ---- 画面全体の設定（スマホ向けに centered = 中央寄せの1カラム）----
st.set_page_config(page_title="車の情報管理", page_icon="🚗", layout="centered")

# 保存先（今は CSV。将来スプレッドシートに差し替え予定）
storage = get_storage()

st.title("🚗 車の情報管理")
st.caption("家族で使う、車検・オイル交換・タイヤ交換の記録アプリ")


# =====================================================================
# 1. 登録されている車の一覧（期限が近い順・色分け）
# =====================================================================
st.header("登録されている車")

try:
    cars = storage.list_cars()
except Exception as e:
    st.error(f"車のデータを読み込めませんでした。\n\n{e}")
    st.stop()

if not cars:
    st.info("まだ車が登録されていません。下の「車を追加する」から登録してください。")
else:
    # 期限チェック（緊急な車が先頭にくるよう並べ替え済み）
    checks = maintenance.check_all(cars)

    # (a) 全体のお知らせ
    overdue = [cc for cc in checks if cc.status == Status.OVERDUE]
    soon = [cc for cc in checks if cc.status == Status.SOON]
    if overdue:
        st.error(f"🔴 期限切れの項目がある車が {len(overdue)}台 あります")
    if soon:
        st.warning(f"🟡 期限が近い項目がある車が {len(soon)}台 あります")
    if not overdue and not soon:
        st.success("🟢 いま対応が必要な車はありません")

    st.caption("🔴 期限切れ　🟡 期限が近い　🟢 まだ余裕　⚪ 未設定")

    # (b) 表でざっと確認（横スクロールできます）
    st.dataframe(
        [
            {
                "状態": f"{maintenance.STATUS_EMOJI[cc.status]} "
                f"{maintenance.STATUS_LABEL[cc.status]}",
                "名前": cc.car.name,
                "ナンバー": cc.car.plate_number or "-",
                "車検期限": _show(cc.car.inspection_due_date),
                "前回オイル交換": _show(cc.car.last_oil_change_date),
                "前回タイヤ交換": _show(cc.car.last_tire_change_date),
            }
            for cc in checks
        ],
        width="stretch",
        hide_index=True,
    )

    # (c) スマホ向け: 1台ずつカードで表示（危ない車は開いた状態）
    st.subheader("車ごとの詳細")
    for cc in checks:
        c = cc.car
        title = f"{maintenance.STATUS_EMOJI[cc.status]} {c.name}"
        if c.plate_number:
            title += f"（{c.plate_number}）"
        with st.expander(title, expanded=cc.status in (Status.OVERDUE, Status.SOON)):
            for item in cc.items:
                st.markdown(_item_line(item))
            st.caption(
                "オイル/タイヤの日付は「前回＋推奨間隔」で計算した目安です"
                "（間隔は src/config.py で変更できます）。"
            )
            if st.button("この車を削除する", key=f"delete-{c.id}"):
                try:
                    storage.delete_car(c.id)
                except Exception as e:
                    st.error(f"削除に失敗しました。\n\n{e}")
                    st.stop()
                st.rerun()


# =====================================================================
# 2. 車を追加するフォーム
# =====================================================================
st.header("車を追加する")

with st.form("add-car-form", clear_on_submit=True):
    name = st.text_input("車の名前 *", placeholder="例: パパの車")
    plate_number = st.text_input("ナンバー", placeholder="例: 品川 300 あ 12-34")
    inspection_due_date = st.date_input(
        "車検の期限日", value=None, format="YYYY/MM/DD"
    )

    col1, col2 = st.columns(2)
    with col1:
        last_oil_change_date = st.date_input(
            "直近のオイル交換日", value=None, format="YYYY/MM/DD"
        )
    with col2:
        last_tire_change_date = st.date_input(
            "直近のタイヤ交換日", value=None, format="YYYY/MM/DD"
        )

    submitted = st.form_submit_button("追加する", width="stretch")

    if submitted:
        if not name.strip():
            st.error("「車の名前」は必須です。")
        else:
            try:
                storage.add_car(
                    Car(
                        name=name.strip(),
                        plate_number=plate_number.strip(),
                        inspection_due_date=inspection_due_date,
                        last_oil_change_date=last_oil_change_date,
                        last_tire_change_date=last_tire_change_date,
                    )
                )
            except Exception as e:
                st.error(f"追加に失敗しました。\n\n{e}")
                st.stop()
            st.success(f"「{name.strip()}」を追加しました。")
            st.rerun()
