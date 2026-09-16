"""車の状態を横並びで比較する「マトリックス表」ページ。

縦に項目（車検・オイル交換など）、横に車を並べた表で、どの車の何が
危ないかを一目で比較できるようにする画面。登録・編集は app.py 側のまま。

判定ロジック（🔴🟡🟢⚪の付け方）は src/maintenance.py を app.py とそのまま
共用しているので、一覧画面とこのページで結果がズレることはありません。
"""
from __future__ import annotations

import streamlit as st

from src import config, maintenance
from src.maintenance import Status
from src.storage import get_storages

# 縦の行（項目）の並び順
ROW_NAMES = ["車検", "オイル交換", "タイヤ交換", "自動車税", "自賠責保険", "任意保険"]


def _cell_caption(item: maintenance.ItemCheck) -> str:
    """セルの下段に出す小さめの文字（期限までの日数・距離）。"""
    if item.status == Status.UNKNOWN:
        return "未設定"

    parts = []
    if item.days_left is not None:
        if item.days_left < 0:
            parts.append(f"{abs(item.days_left)}日超過")
        else:
            parts.append(f"あと{item.days_left}日")
    if item.distance_left_km is not None:
        if item.distance_left_km < 0:
            parts.append(f"{abs(item.distance_left_km):,}km超過")
        else:
            parts.append(f"あと{item.distance_left_km:,}km")
    return " / ".join(parts) if parts else "-"


# ---- 画面全体の設定（横に長い表なので wide レイアウト）----
st.set_page_config(page_title="マトリックス表", page_icon="📊", layout="wide")

st.title("📊 マトリックス表")
st.caption("車ごとの状態を、項目を縦・車を横にして比較できます。")

storage, record_storage = get_storages()

try:
    cars = storage.list_cars()
    records = record_storage.list_records()
except Exception as e:
    st.error(f"車のデータを読み込めませんでした。\n\n{e}")
    st.stop()

if not cars:
    st.info("まだ車が登録されていません。「登録一覧」ページから登録してください。")
    st.stop()

# 緊急な車が左に来るよう、一覧画面と同じ並び順を使う
checks = maintenance.check_all(cars, records)

# ---- 絞り込み（担当者）。一覧画面と同じ考え方 ----
owner_options = sorted({c.owner for c in cars if c.owner} | set(config.OWNER_OPTIONS))
selected_owners = st.multiselect(
    "担当者で絞り込み", options=owner_options, placeholder="すべて"
)

filtered = checks
if selected_owners:
    filtered = [cc for cc in filtered if cc.car.owner in selected_owners]

if not filtered:
    st.info("絞り込み条件に一致する車がありません。")
    st.stop()

st.caption("🔴 期限切れ　🟡 期限が近い　🟢 まだ余裕　⚪ 未設定")
st.caption("車の名前をタップすると、登録一覧ページでその車を開いて確認・編集できます。")

# ---- 横スクロール用の入れ物 ----
# st.container(key=...) には自動で "st-key-<key>" というCSSクラスが付くので、
# それを目印にして横スクロールのスタイルを当てる。
st.markdown(
    """
    <style>
    .st-key-matrix_scroll {
        overflow-x: auto;
        padding-bottom: 0.75rem;
    }
    .st-key-matrix_scroll [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap;
    }
    .st-key-matrix_scroll [data-testid="stHorizontalBlock"] > div {
        min-width: 7rem;
    }
    .st-key-matrix_scroll [data-testid="stHorizontalBlock"] > div:first-child {
        min-width: 6rem;
        /* 項目名の列を横スクロールしても画面に固定する */
        position: sticky;
        left: 0;
        z-index: 1;
        background-color: #ffffff;
        box-shadow: 2px 0 4px -2px rgba(0, 0, 0, 0.25);
    }
    @media (prefers-color-scheme: dark) {
        .st-key-matrix_scroll [data-testid="stHorizontalBlock"] > div:first-child {
            background-color: rgb(14, 17, 23);
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

column_widths = [1.4] + [1.0] * len(filtered)

with st.container(key="matrix_scroll"):
    # ---- 見出し行（車の名前。タップで登録一覧のその車へ）----
    header_cols = st.columns(column_widths)
    with header_cols[0]:
        st.markdown("**項目**")
    for col, cc in zip(header_cols[1:], filtered):
        with col:
            st.page_link(
                "app.py",
                label=f"{maintenance.STATUS_EMOJI[cc.status]} {cc.car.name}",
                query_params={"car_id": cc.car.id},
            )

    # ---- 項目ごとの行 ----
    for row_name in ROW_NAMES:
        row_cols = st.columns(column_widths)
        with row_cols[0]:
            st.markdown(f"**{row_name}**")
        for col, cc in zip(row_cols[1:], filtered):
            item = cc.item(row_name)
            with col:
                st.markdown(f"### {maintenance.STATUS_EMOJI[item.status]}")
                st.caption(_cell_caption(item))
