"""車ごと・年ごとの維持費（税金・保険料）を記録・比較するページ。

期限チェック（🔴🟡🟢⚪、src/maintenance.py）とは完全に別のデータです。
ここでの入力・表示は、登録一覧ページ・マトリックス表ページ・週次メールの
いずれにも一切影響しません（保存先も別のシート/ファイルです）。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.models import AnnualCost
from src.storage import get_annual_cost_storage, get_storage

# (内部名, 画面表示用のラベル) の組。表の列や集計で使い回す。
COST_FIELDS = [
    ("vehicle_tax", "自動車税"),
    ("weight_tax", "重量税"),
    ("compulsory_insurance", "自賠責保険"),
    ("voluntary_insurance", "任意保険"),
]


def _format_yen(value: int | None) -> str:
    """金額を「12,300円」の形にする。未入力なら「未入力」。"""
    return f"{value:,}円" if value is not None else "未入力"


def _format_total(record: AnnualCost | None) -> str:
    """合計欄の表示。入力済みの項目だけを足し、未入力があれば注記を添える。"""
    if record is None or not record.has_any_amount:
        return "未入力"
    text = f"{record.total:,}円"
    if record.has_missing_amount:
        text += "　※一部未入力"
    return text


def _format_diff(diff: int | None) -> str:
    """前年との差額の表示（増減が無ければ"-"）。"""
    if diff is None:
        return "-"
    if diff > 0:
        return f"+{diff:,}円"
    if diff < 0:
        return f"{diff:,}円"
    return "±0円"


# ---- 画面全体の設定 ----
# initial_sidebar_state="expanded" を指定しないと、初期値の "auto" では
# 画面が狭いときにページ切り替えサイドバーが自動で閉じてしまうため明示している。
st.set_page_config(
    page_title="費用管理",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("💰 費用管理")
st.caption(
    "車ごと・年ごとの維持費（自動車税・重量税・自賠責保険・任意保険）を記録して比較できます。"
    "期限チェック（🔴🟡🟢⚪）やマトリックス表、週次メールには一切影響しません。"
)

storage = get_storage()
cost_storage = get_annual_cost_storage()

try:
    cars = storage.list_cars()
except Exception as e:
    st.error(f"車のデータを読み込めませんでした。\n\n{e}")
    st.stop()

if not cars:
    st.info("まだ車が登録されていません。「登録一覧」ページから登録してください。")
    st.stop()

try:
    all_costs = cost_storage.list_annual_costs()
except Exception as e:
    st.error(f"年間費用のデータを読み込めませんでした。\n\n{e}")
    st.stop()

cars_by_id = {c.id: c for c in cars}

# =====================================================================
# 1. 記録する・修正する
# =====================================================================
st.header("記録する・修正する")

car_options = {c.id: c.name for c in cars}
selected_car_id = st.selectbox(
    "車", options=list(car_options.keys()), format_func=lambda cid: car_options[cid]
)
selected_car = cars_by_id[selected_car_id]

this_year = date.today().year
selected_year_input = st.number_input(
    "年（西暦）", min_value=2000, max_value=this_year + 1, value=this_year, step=1
)
selected_year = int(selected_year_input)

existing = next(
    (r for r in all_costs if r.car_id == selected_car_id and r.year == selected_year),
    None,
)
if existing is not None:
    st.caption(
        f"「{selected_car.name}」の{selected_year}年の記録が既にあります。"
        "内容を修正してそのまま保存できます。"
    )
else:
    st.caption(f"「{selected_car.name}」の{selected_year}年はまだ記録がありません。")

# 車・年の組み合わせごとにフォーム/入力欄のキーを変え、切り替えたときに
# 前に選んでいた車・年の入力値が残ってしまわないようにする。
form_key = f"{selected_car_id}-{selected_year}"
with st.form(f"annual-cost-form-{form_key}"):
    cost_col1, cost_col2 = st.columns(2)
    with cost_col1:
        vehicle_tax = st.number_input(
            "自動車税（円）",
            min_value=0,
            step=100,
            value=existing.vehicle_tax if existing else None,
            key=f"vehicle_tax-{form_key}",
        )
        compulsory_insurance = st.number_input(
            "自賠責保険料（円）",
            min_value=0,
            step=100,
            value=existing.compulsory_insurance if existing else None,
            key=f"compulsory_insurance-{form_key}",
        )
    with cost_col2:
        weight_tax = st.number_input(
            "重量税（円）",
            min_value=0,
            step=100,
            value=existing.weight_tax if existing else None,
            key=f"weight_tax-{form_key}",
        )
        voluntary_insurance = st.number_input(
            "任意保険料（円）",
            min_value=0,
            step=100,
            value=existing.voluntary_insurance if existing else None,
            key=f"voluntary_insurance-{form_key}",
        )
    memo = st.text_input(
        "メモ（任意）",
        value=existing.memo if existing else "",
        key=f"memo-{form_key}",
    )
    submitted = st.form_submit_button("保存する", width="stretch")

    if submitted:
        record = AnnualCost(
            car_id=selected_car_id,
            year=selected_year,
            vehicle_tax=int(vehicle_tax) if vehicle_tax is not None else None,
            weight_tax=int(weight_tax) if weight_tax is not None else None,
            compulsory_insurance=(
                int(compulsory_insurance) if compulsory_insurance is not None else None
            ),
            voluntary_insurance=(
                int(voluntary_insurance) if voluntary_insurance is not None else None
            ),
            memo=memo.strip(),
        )
        try:
            cost_storage.upsert_annual_cost(record)
        except Exception as e:
            st.error(f"保存に失敗しました。\n\n{e}")
            st.stop()
        st.success(f"「{selected_car.name}」の{selected_year}年の記録を保存しました。")
        st.rerun()

st.divider()

# =====================================================================
# 2. 比較する
# =====================================================================
st.header("比較する")

if not all_costs:
    st.info("まだ年間費用の記録がありません。上のフォームから記録してください。")
else:
    years = sorted({r.year for r in all_costs})

    # ---- 2-1. 選んだ車の年別推移 ----
    st.subheader(f"「{selected_car.name}」の年別推移")
    st.caption("表は横スクロールできます。")
    car_costs = sorted(
        (r for r in all_costs if r.car_id == selected_car_id), key=lambda r: r.year
    )
    if not car_costs:
        st.caption("この車の記録はまだありません。")
    else:
        trend_rows = []
        prev_total: int | None = None
        for r in car_costs:
            diff = r.total - prev_total if prev_total is not None else None
            row = {"年": r.year}
            for field, label in COST_FIELDS:
                row[label] = _format_yen(getattr(r, field))
            row["合計"] = _format_total(r)
            row["前年差"] = _format_diff(diff)
            trend_rows.append(row)
            prev_total = r.total
        st.dataframe(trend_rows, hide_index=True, width="stretch")

    # ---- 2-2. 全車の年別合計 ----
    st.subheader("全車の年別合計")
    st.caption("表は横スクロールできます。")
    yearly_rows = []
    for year in years:
        year_records = [r for r in all_costs if r.year == year]
        sums = {field: 0 for field, _ in COST_FIELDS}
        has_missing = False
        for r in year_records:
            for field, _ in COST_FIELDS:
                v = getattr(r, field)
                if v is not None:
                    sums[field] += v
                else:
                    has_missing = True
        total = sum(sums.values())
        total_text = f"{total:,}円" + ("　※一部未入力" if has_missing else "")
        row = {"年": year}
        for field, label in COST_FIELDS:
            row[label] = f"{sums[field]:,}円"
        row["合計"] = total_text
        yearly_rows.append(row)
    st.dataframe(yearly_rows, hide_index=True, width="stretch")

    # ---- 2-3. 年を1つ選んで車同士を比較 ----
    st.subheader("車同士を比較する")
    st.caption("表は横スクロールできます。")
    compare_year = st.selectbox(
        "比較する年", options=years, index=len(years) - 1, key="compare-year"
    )
    costs_by_car_year = {(r.car_id, r.year): r for r in all_costs}
    compare_rows = []
    for field, label in COST_FIELDS:
        row = {"項目": label}
        for c in cars:
            rec = costs_by_car_year.get((c.id, compare_year))
            row[c.name] = _format_yen(getattr(rec, field)) if rec else "記録なし"
        compare_rows.append(row)
    total_row = {"項目": "合計"}
    for c in cars:
        rec = costs_by_car_year.get((c.id, compare_year))
        total_row[c.name] = _format_total(rec) if rec else "記録なし"
    compare_rows.append(total_row)
    st.dataframe(compare_rows, hide_index=True, width="stretch")

    # ---- 2-4. 棒グラフ ----
    st.subheader("年別の合計推移（グラフ）")
    graph_target = st.selectbox(
        "グラフの対象", options=["全車合計"] + [c.name for c in cars], key="graph-target"
    )
    if graph_target == "全車合計":
        chart_values = [sum(r.total for r in all_costs if r.year == y) for y in years]
    else:
        target_car_id = next(c.id for c in cars if c.name == graph_target)
        chart_values = [
            sum(r.total for r in all_costs if r.year == y and r.car_id == target_car_id)
            for y in years
        ]
    chart_df = pd.DataFrame({"合計（円）": chart_values}, index=years)
    st.bar_chart(chart_df)
