"""車ごと・年ごとの維持費（税金・保険料・整備費）を記録・比較するページ。

期限チェック（🔴🟡🟢⚪、src/maintenance.py）とは完全に別のデータです。
ここでの入力・表示は、登録一覧ページ・マトリックス表ページ・週次メールの
いずれにも一切影響しません。

維持費は2種類の出どころがあります。
  ・税金・保険料（自動車税・重量税・自賠責保険・任意保険）
    … このページの入力フォームから「年間費用」シートに保存
  ・整備費（オイル・タイヤ・車検整備・その他）
    … 登録一覧ページの「整備記録」に入力された費用を、このページが
      表示のたびに集計するだけ。別の場所にコピーはしない
        （同じ金額が2か所に残らないようにするため）。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.models import AnnualCost, MaintenanceRecord, RecordType
from src.storage import get_annual_cost_storage, get_record_storage, get_storage

# 税金・保険料（AnnualCostのフィールド名, 画面表示用のラベル）
COST_FIELDS = [
    ("vehicle_tax", "自動車税"),
    ("weight_tax", "重量税"),
    ("compulsory_insurance", "自賠責保険"),
    ("voluntary_insurance", "任意保険"),
]

# 整備費の内訳（RecordType, 画面表示用のラベル）
# ※ 車検の整備記録には「整備費・手数料だけ」を入れる運用。重量税・自賠責は
#   上のCOST_FIELDS側（年間費用）に入れるので、ここでの「車検整備」と
#   二重計上にはならない。
MAINTENANCE_CATEGORIES = [
    (RecordType.OIL, "オイル"),
    (RecordType.TIRE, "タイヤ"),
    (RecordType.INSPECTION, "車検整備"),
    (RecordType.OTHER, "その他"),
]


def _format_yen(value: int | None) -> str:
    """金額を「12,300円」の形にする。未入力なら「未入力」。"""
    return f"{value:,}円" if value is not None else "未入力"


def _format_diff(diff: int | None) -> str:
    """前年との差額の表示（比較対象が無ければ"-"）。"""
    if diff is None:
        return "-"
    if diff > 0:
        return f"+{diff:,}円"
    if diff < 0:
        return f"{diff:,}円"
    return "±0円"


def _new_maintenance_entry() -> dict:
    """整備費の集計結果1件分の入れ物（作業内容ごとの合計・費用未入力の件数）。"""
    return {"by_type": {rt: 0 for rt, _ in MAINTENANCE_CATEGORIES}, "missing_count": 0}


def _add_record_to_entry(entry: dict, record: MaintenanceRecord) -> None:
    """整備記録1件を、集計結果に足し込む。

    費用が空欄（None）の記録は合計には含めず、missing_count だけ増やす
    （0円の記録は0円として普通に合計する＝空欄と0円を区別する）。
    """
    if record.cost is None:
        entry["missing_count"] += 1
    else:
        entry["by_type"][record.record_type] = (
            entry["by_type"].get(record.record_type, 0) + record.cost
        )


def _aggregate_maintenance_by_year(records: list[MaintenanceRecord]) -> dict[int, dict]:
    """整備記録を「日付の年」ごとに集計する（渡した records が対象のすべて）。"""
    agg: dict[int, dict] = {}
    for r in records:
        entry = agg.setdefault(r.date.year, _new_maintenance_entry())
        _add_record_to_entry(entry, r)
    return agg


def _aggregate_maintenance_by_car_year(
    records: list[MaintenanceRecord],
) -> dict[tuple[str, int], dict]:
    """整備記録を (車, 日付の年) ごとに集計する。"""
    agg: dict[tuple[str, int], dict] = {}
    for r in records:
        key = (r.car_id, r.date.year)
        entry = agg.setdefault(key, _new_maintenance_entry())
        _add_record_to_entry(entry, r)
    return agg


def _maintenance_total(entry: dict | None) -> int:
    """整備費の合計（入力済みの記録だけを足す）。"""
    return sum(entry["by_type"].values()) if entry else 0


def _format_maintenance_total(entry: dict | None) -> str:
    """整備費合計欄の表示。費用未入力の記録があれば件数を添える。"""
    text = f"{_maintenance_total(entry):,}円"
    missing = entry["missing_count"] if entry else 0
    if missing > 0:
        text += f"　※整備費の未入力が{missing}件"
    return text


def _sum_annual_costs(records: list[AnnualCost], year: int) -> AnnualCost | None:
    """指定した年の年間費用記録を、全車ぶんまとめて1件に合算する。

    項目ごとに「1台でも入力があれば合算、全車とも未入力ならその項目はNoneのまま」
    にすることで、合算結果にも AnnualCost.total / has_missing_amount が使える。
    """
    year_records = [r for r in records if r.year == year]
    if not year_records:
        return None
    summed: dict[str, int | None] = {}
    for field, _ in COST_FIELDS:
        values = [getattr(r, field) for r in year_records]
        known = [v for v in values if v is not None]
        summed[field] = sum(known) if known else None
    return AnnualCost(car_id="(全車合計)", year=year, **summed)


def _grand_total_value(annual: AnnualCost | None, maint: dict | None) -> int:
    """維持費の総額（税・保険の合計 ＋ 整備費の合計）。"""
    tax_total = annual.total if annual is not None else 0
    return tax_total + _maintenance_total(maint)


def _format_grand_total(annual: AnnualCost | None, maint: dict | None) -> str:
    """維持費の総額欄の表示。未入力があれば注記を添える（複数付くこともある）。"""
    text = f"{_grand_total_value(annual, maint):,}円"
    notes = []
    if annual is None or annual.has_missing_amount:
        notes.append("※一部未入力")
    missing = maint["missing_count"] if maint else 0
    if missing > 0:
        notes.append(f"※整備費の未入力が{missing}件")
    if notes:
        text += "　" + "　".join(notes)
    return text


def _build_cost_row(year: int, annual: AnnualCost | None, maint: dict | None) -> dict:
    """1年ぶんの表の行（年・税保険4項目・整備費内訳4項目・整備費合計・維持費総額）を作る。

    「前年差」はこの行には含めない（前年の合計が分かっている場所で別途付け足す）。
    """
    row: dict = {"年": year}
    for field, label in COST_FIELDS:
        row[label] = _format_yen(getattr(annual, field) if annual else None)
    for rt, label in MAINTENANCE_CATEGORIES:
        row[label] = f"{(maint['by_type'].get(rt, 0) if maint else 0):,}円"
    row["整備費合計"] = _format_maintenance_total(maint)
    row["維持費総額"] = _format_grand_total(annual, maint)
    return row


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
    "車ごと・年ごとの維持費を記録して比較できます。"
    "自動車税・重量税・自賠責保険・任意保険はこのページで入力し、"
    "整備費（オイル・タイヤ・車検整備・その他）は登録一覧ページの「整備記録」から"
    "自動で集計します（同じ金額が2か所に残らないよう、整備費はコピーしません）。"
    "期限チェック（🔴🟡🟢⚪）やマトリックス表、週次メールには一切影響しません。"
)

storage = get_storage()
cost_storage = get_annual_cost_storage()
record_storage = get_record_storage()

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

try:
    maintenance_records = record_storage.list_records()
except Exception as e:
    st.error(f"整備記録のデータを読み込めませんでした。\n\n{e}")
    st.stop()

cars_by_id = {c.id: c for c in cars}

# =====================================================================
# 1. 記録する・修正する（税金・保険料のみ。整備費は登録一覧ページから）
# =====================================================================
st.header("記録する・修正する")
st.caption("ここで入力するのは自動車税・重量税・自賠責保険・任意保険だけです。")

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
# 2. 比較する（税金・保険料 ＋ 整備記録から集計した整備費）
# =====================================================================
st.header("比較する")

if not all_costs and not maintenance_records:
    st.info(
        "まだ費用の記録がありません。上のフォームか、登録一覧ページの"
        "「整備記録」から記録してください。"
    )
else:
    all_years = sorted(
        {r.year for r in all_costs} | {r.date.year for r in maintenance_records}
    )
    maint_by_year_all = _aggregate_maintenance_by_year(maintenance_records)
    maint_by_car_year = _aggregate_maintenance_by_car_year(maintenance_records)
    annual_by_car_year = {(r.car_id, r.year): r for r in all_costs}

    # ---- 2-1. 選んだ車の年別推移 ----
    st.subheader(f"「{selected_car.name}」の年別推移")
    st.caption("表は横スクロールできます。")
    car_maint_by_year = {
        year: entry
        for year, entry in _aggregate_maintenance_by_year(
            [r for r in maintenance_records if r.car_id == selected_car_id]
        ).items()
    }
    car_annual_by_year = {
        r.year: r for r in all_costs if r.car_id == selected_car_id
    }
    car_years = sorted(set(car_annual_by_year) | set(car_maint_by_year))
    if not car_years:
        st.caption("この車の記録はまだありません。")
    else:
        trend_rows = []
        prev_total: int | None = None
        for year in car_years:
            annual = car_annual_by_year.get(year)
            maint = car_maint_by_year.get(year)
            row = _build_cost_row(year, annual, maint)
            total = _grand_total_value(annual, maint)
            row["前年差"] = _format_diff(
                total - prev_total if prev_total is not None else None
            )
            trend_rows.append(row)
            prev_total = total
        st.dataframe(trend_rows, hide_index=True, width="stretch")

    # ---- 2-2. 全車の年別合計 ----
    st.subheader("全車の年別合計")
    st.caption("表は横スクロールできます。")
    yearly_rows = []
    prev_total_all: int | None = None
    for year in all_years:
        annual_sum = _sum_annual_costs(all_costs, year)
        maint = maint_by_year_all.get(year)
        row = _build_cost_row(year, annual_sum, maint)
        total = _grand_total_value(annual_sum, maint)
        row["前年差"] = _format_diff(
            total - prev_total_all if prev_total_all is not None else None
        )
        yearly_rows.append(row)
        prev_total_all = total
    st.dataframe(yearly_rows, hide_index=True, width="stretch")

    # ---- 2-3. 年を1つ選んで車同士を比較 ----
    st.subheader("車同士を比較する")
    st.caption("表は横スクロールできます。")
    compare_year = st.selectbox(
        "比較する年", options=all_years, index=len(all_years) - 1, key="compare-year"
    )
    compare_rows = []
    for field, label in COST_FIELDS:
        row = {"項目": label}
        for c in cars:
            annual = annual_by_car_year.get((c.id, compare_year))
            row[c.name] = _format_yen(getattr(annual, field) if annual else None)
        compare_rows.append(row)
    for rt, label in MAINTENANCE_CATEGORIES:
        row = {"項目": label}
        for c in cars:
            maint = maint_by_car_year.get((c.id, compare_year))
            row[c.name] = f"{(maint['by_type'].get(rt, 0) if maint else 0):,}円"
        compare_rows.append(row)
    maint_total_row = {"項目": "整備費合計"}
    for c in cars:
        maint_total_row[c.name] = _format_maintenance_total(
            maint_by_car_year.get((c.id, compare_year))
        )
    compare_rows.append(maint_total_row)
    grand_row = {"項目": "維持費総額"}
    for c in cars:
        annual = annual_by_car_year.get((c.id, compare_year))
        maint = maint_by_car_year.get((c.id, compare_year))
        grand_row[c.name] = _format_grand_total(annual, maint)
    compare_rows.append(grand_row)
    st.dataframe(compare_rows, hide_index=True, width="stretch")

    # ---- 2-4. 棒グラフ（税・保険 と 整備費 を色分けして積み上げ） ----
    st.subheader("年別の維持費総額の推移（グラフ）")
    graph_target = st.selectbox(
        "グラフの対象", options=["全車合計"] + [c.name for c in cars], key="graph-target"
    )
    if graph_target == "全車合計":
        tax_values = [
            (_sum_annual_costs(all_costs, y).total if _sum_annual_costs(all_costs, y) else 0)
            for y in all_years
        ]
        maint_values = [_maintenance_total(maint_by_year_all.get(y)) for y in all_years]
    else:
        target_car_id = next(c.id for c in cars if c.name == graph_target)
        target_annual_by_year = {
            r.year: r for r in all_costs if r.car_id == target_car_id
        }
        target_maint_by_year = _aggregate_maintenance_by_year(
            [r for r in maintenance_records if r.car_id == target_car_id]
        )
        tax_values = [
            (target_annual_by_year[y].total if y in target_annual_by_year else 0)
            for y in all_years
        ]
        maint_values = [
            _maintenance_total(target_maint_by_year.get(y)) for y in all_years
        ]
    chart_df = pd.DataFrame(
        {"税・保険": tax_values, "整備費": maint_values}, index=all_years
    )
    st.bar_chart(chart_df, stack=True)
