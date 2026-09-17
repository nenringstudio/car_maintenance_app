"""家族用 車の情報管理アプリ

  ・車の情報を「登録」して「一覧表示」する
  ・車検 / 自動車税 / 自賠責保険 / 任意保険 / オイル交換 / タイヤ交換
    の期限が近い車を色分けで表示する
  ・オイル交換 / タイヤ交換 / 車検 / その他の整備記録を、車ごとに履歴として残す
（メール送信は次のステップで追加します）

起動方法（ターミナルで）:
    streamlit run app.py
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import config, maintenance
from src.maintenance import Status
from src.models import RECORD_TYPE_LABELS, Car, MaintenanceRecord, RecordType
from src.storage import get_storages


def _show(value: date | None) -> str:
    """日付を画面表示用の文字列にする。未設定なら「未設定」。"""
    return value.strftime("%Y/%m/%d") if value else "未設定"


def _item_line(item: maintenance.ItemCheck) -> str:
    """1項目（車検など）を、色つきの1行テキストにする。"""
    emoji = maintenance.STATUS_EMOJI[item.status]
    color = maintenance.STATUS_COLOR[item.status]

    if item.status == Status.UNKNOWN:
        return f"{emoji} **{item.name}**：:gray[未設定]"

    parts = []
    if item.due_date is not None:
        when = item.due_date.strftime("%Y/%m/%d")
        suffix = "・目安" if item.is_estimate else ""
        if item.days_left is not None and item.days_left < 0:
            parts.append(f"{when}{suffix} を {abs(item.days_left)}日 超過")
        else:
            parts.append(f"あと {item.days_left}日（{when}{suffix}）")
    if item.distance_left_km is not None:
        if item.distance_left_km < 0:
            parts.append(f"{abs(item.distance_left_km):,}km 超過")
        else:
            parts.append(f"あと {item.distance_left_km:,}km")
    detail = "　／　".join(parts)
    return f"{emoji} **{item.name}**：:{color}[{detail}]"


def _elapsed_years_months(start: date, today: date) -> tuple[int, int] | None:
    """start から today までの経過期間を (年, 月) で返す。

    start が未来の日付など計算できない場合は None。
    """
    if start > today:
        return None
    years = today.year - start.year
    months = today.month - start.month
    if today.day < start.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return years, months


def _record_line(record: MaintenanceRecord) -> str:
    """整備記録1件を、1行のテキストにする。"""
    label = RECORD_TYPE_LABELS[record.record_type]
    when = record.date.strftime("%Y/%m/%d")
    text = f"{when}　**{label}**"
    if record.odometer_km is not None:
        text += f"　{record.odometer_km:,}km"
    if record.cost is not None:
        text += f"　￥{record.cost:,}"
    if record.memo:
        text += f"　{record.memo}"
    return text


# ---- 画面全体の設定（スマホ向けに centered = 中央寄せの1カラム）----
# initial_sidebar_state="expanded" を指定しないと、初期値の "auto" では
# 画面が狭いときにページ切り替えサイドバーが自動で閉じてしまうため明示している。
st.set_page_config(
    page_title="車の情報管理",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 保存先（今は CSV。将来スプレッドシートに差し替え予定）
# storage ……… 車の基本情報　/　record_storage ……… 整備記録（履歴）
storage, record_storage = get_storages()

st.title("🚗 車の情報管理")
st.caption("家族で使う、車検・オイル交換・タイヤ交換の記録アプリ")


# =====================================================================
# 1. 登録されている車の一覧（期限が近い順・色分け）
# =====================================================================
st.header("登録されている車")

try:
    cars = storage.list_cars()
    records = record_storage.list_records()
except Exception as e:
    st.error(f"車のデータを読み込めませんでした。\n\n{e}")
    st.stop()

if not cars:
    st.info("まだ車が登録されていません。下の「車を追加する」から登録してください。")
else:
    # 期限チェック（緊急な車が先頭にくるよう並べ替え済み）
    # ※ オイル/タイヤの「次回目安」は、整備記録の中で一番新しい日付から自動計算しています。
    checks = maintenance.check_all(cars, records)

    # マトリックス表などから「この車を見たい」と指定されて来た場合の car_id
    focus_car_id = st.query_params.get("car_id")

    # (a) 絞り込み（担当者 / 状態）
    #     ※ ここで絞り込んでも、並び順は checks の順番（緊急な車が先頭）のまま変わりません。
    owner_options = sorted(
        {c.owner for c in cars if c.owner} | set(config.PERSON_IN_CHARGE)
    )
    status_options = [Status.OVERDUE, Status.SOON, Status.OK, Status.UNKNOWN]

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_owners = st.multiselect(
            "担当者で絞り込み", options=owner_options, placeholder="すべて"
        )
    with filter_col2:
        selected_statuses = st.multiselect(
            "状態で絞り込み",
            options=status_options,
            format_func=lambda s: f"{maintenance.STATUS_EMOJI[s]} {maintenance.STATUS_LABEL[s]}",
            placeholder="すべて",
        )

    filtered = checks
    if selected_owners:
        filtered = [cc for cc in filtered if cc.car.owner in selected_owners]
    if selected_statuses:
        filtered = [cc for cc in filtered if cc.status in selected_statuses]

    # マトリックス表から来た車が絞り込みで隠れてしまわないよう、そのときは絞り込みを外す
    if focus_car_id and not any(cc.car.id == focus_car_id for cc in filtered):
        filtered = checks

    # (b) 全体のお知らせ（絞り込み後の件数）
    overdue = [cc for cc in filtered if cc.status == Status.OVERDUE]
    soon = [cc for cc in filtered if cc.status == Status.SOON]
    if overdue:
        st.error(f"🔴 期限切れの項目がある車が {len(overdue)}台 あります")
    if soon:
        st.warning(f"🟡 期限が近い項目がある車が {len(soon)}台 あります")
    if not overdue and not soon:
        st.success("🟢 いま対応が必要な車はありません")

    st.caption("🔴 期限切れ　🟡 期限が近い　🟢 まだ余裕　⚪ 未設定")

    if not filtered:
        st.info("絞り込み条件に一致する車がありません。")
    else:
        # (c) 表でざっと確認（横スクロールできます）
        st.dataframe(
            [
                {
                    "状態": f"{maintenance.STATUS_EMOJI[cc.status]} "
                    f"{maintenance.STATUS_LABEL[cc.status]}",
                    "名前": cc.car.name,
                    "担当者": cc.car.owner or "-",
                    "ナンバー": cc.car.plate_number or "-",
                    "車検期限": _show(cc.item("車検").due_date),
                    "自動車税": _show(cc.item("自動車税").due_date),
                    "自賠責保険": _show(cc.item("自賠責保険").due_date),
                    "任意保険": _show(cc.item("任意保険").due_date),
                    "次回オイル目安": _show(cc.item("オイル交換").due_date),
                    "次回タイヤ目安": _show(cc.item("タイヤ交換").due_date),
                }
                for cc in filtered
            ],
            width="stretch",
            hide_index=True,
        )

        # (d) スマホ向け: 1台ずつカードで表示（危ない車は開いた状態）
        st.subheader("車ごとの詳細")
        for cc in filtered:
            c = cc.car
            title = f"{maintenance.STATUS_EMOJI[cc.status]} {c.name}"
            if c.owner:
                title += f"（担当: {c.owner}）"
            editing = st.session_state.get(f"editing_car_{c.id}", False)
            is_focused = c.id == focus_car_id
            confirming_delete = st.session_state.get(
                f"confirm_delete_car_{c.id}", False
            )

            with st.expander(
                title,
                expanded=editing
                or is_focused
                or confirming_delete
                or cc.status in (Status.OVERDUE, Status.SOON),
            ):
                if is_focused:
                    st.caption("📊 マトリックス表からこの車が指定されています。")
                if editing:
                    # ---- 編集フォーム（登録時と同じ項目に、今の内容を入れた状態）----
                    with st.form(f"edit-car-{c.id}"):
                        st.caption(
                            "オイル/タイヤ交換は下の「整備記録」から、"
                            "自動車税は自動計算のため、ここでは編集しません。"
                        )
                        edit_name = st.text_input(
                            "車の名前 *", value=c.name, key=f"edit-name-{c.id}"
                        )
                        owner_choices = list(config.PERSON_IN_CHARGE)
                        if c.owner and c.owner not in owner_choices:
                            owner_choices.append(c.owner)
                        owner_select_options = ["（未設定）"] + owner_choices
                        current_owner_index = (
                            owner_select_options.index(c.owner) if c.owner else 0
                        )
                        edit_owner = st.selectbox(
                            "担当者",
                            options=owner_select_options,
                            index=current_owner_index,
                            key=f"edit-owner-{c.id}",
                        )
                        edit_plate = st.text_input(
                            "ナンバー",
                            value=c.plate_number,
                            key=f"edit-plate-{c.id}",
                        )
                        edit_inspection = st.date_input(
                            "車検の期限日",
                            value=c.inspection_due_date,
                            format="YYYY/MM/DD",
                            key=f"edit-inspection-{c.id}",
                        )
                        edit_ins_col1, edit_ins_col2 = st.columns(2)
                        with edit_ins_col1:
                            edit_compulsory = st.date_input(
                                "自賠責保険の満期日",
                                value=c.compulsory_insurance_due_date,
                                format="YYYY/MM/DD",
                                key=f"edit-compulsory-{c.id}",
                            )
                        with edit_ins_col2:
                            edit_voluntary = st.date_input(
                                "任意保険の満期日",
                                value=c.voluntary_insurance_due_date,
                                format="YYYY/MM/DD",
                                key=f"edit-voluntary-{c.id}",
                            )
                        edit_delivery_col1, edit_delivery_col2 = st.columns(2)
                        with edit_delivery_col1:
                            edit_delivery_date = st.date_input(
                                "納車日",
                                value=c.delivery_date,
                                format="YYYY/MM/DD",
                                key=f"edit-delivery-date-{c.id}",
                            )
                        with edit_delivery_col2:
                            edit_delivery_odometer = st.number_input(
                                "納車時の走行距離（km）",
                                min_value=0,
                                step=100,
                                value=c.delivery_odometer_km,
                                key=f"edit-delivery-odometer-{c.id}",
                            )

                        save_col, cancel_col = st.columns(2)
                        with save_col:
                            save_clicked = st.form_submit_button(
                                "保存する", width="stretch"
                            )
                        with cancel_col:
                            cancel_clicked = st.form_submit_button(
                                "キャンセル", width="stretch"
                            )

                        if save_clicked:
                            if not edit_name.strip():
                                st.error("「車の名前」は必須です。")
                            else:
                                c.name = edit_name.strip()
                                c.owner = (
                                    ""
                                    if edit_owner == "（未設定）"
                                    else edit_owner
                                )
                                c.plate_number = edit_plate.strip()
                                c.inspection_due_date = edit_inspection
                                c.compulsory_insurance_due_date = edit_compulsory
                                c.voluntary_insurance_due_date = edit_voluntary
                                c.delivery_date = edit_delivery_date
                                c.delivery_odometer_km = (
                                    int(edit_delivery_odometer)
                                    if edit_delivery_odometer is not None
                                    else None
                                )
                                try:
                                    storage.update_car(c)
                                except Exception as e:
                                    st.error(f"更新に失敗しました。\n\n{e}")
                                    st.stop()
                                st.session_state[f"editing_car_{c.id}"] = False
                                st.success("車の情報を更新しました。")
                                st.rerun()
                        if cancel_clicked:
                            st.session_state[f"editing_car_{c.id}"] = False
                            st.rerun()
                else:
                    if c.plate_number:
                        st.caption(f"ナンバー: {c.plate_number}")
                    for item in cc.items:
                        st.markdown(_item_line(item))
                    st.caption(
                        "オイル/タイヤの「次回目安」は、整備記録の中で一番新しい日付"
                        "＋推奨間隔で計算しています。自動車税は「毎年5月」を目安に自動計算です"
                        "（間隔や月日は src/config.py で変更できます）。"
                        "オイル交換は、月数と走行距離のどちらか早く来た方で判定します。"
                    )

                    # ---- 納車日からの経過期間 / 納車後の総走行距離 ----
                    # 納車日・納車時の走行距離が未入力の車は、この行を出さない。
                    if c.delivery_date is not None:
                        elapsed = _elapsed_years_months(c.delivery_date, date.today())
                        if elapsed is not None:
                            elapsed_years, elapsed_months = elapsed
                            st.caption(
                                f"納車日: {c.delivery_date.strftime('%Y/%m/%d')}"
                                f"（経過 {elapsed_years}年{elapsed_months}か月）"
                            )
                    if (
                        c.current_odometer_km is not None
                        and c.delivery_odometer_km is not None
                    ):
                        distance_since_delivery = (
                            c.current_odometer_km - c.delivery_odometer_km
                        )
                        st.caption(f"納車後の走行距離: {distance_since_delivery:,}km")

                # ---- 現在の走行距離（更新用） ----
                odometer_text = (
                    f"{c.current_odometer_km:,}km"
                    if c.current_odometer_km is not None
                    else "未設定"
                )
                st.caption(f"現在の総走行距離: {odometer_text}")
                with st.form(f"update-odometer-{c.id}", clear_on_submit=False):
                    new_odometer = st.number_input(
                        "現在の総走行距離（km）",
                        min_value=0,
                        step=100,
                        value=c.current_odometer_km,
                    )
                    odometer_submitted = st.form_submit_button(
                        "更新する", width="stretch"
                    )
                    if odometer_submitted:
                        c.current_odometer_km = (
                            int(new_odometer) if new_odometer is not None else None
                        )
                        try:
                            storage.update_car(c)
                        except Exception as e:
                            st.error(f"更新に失敗しました。\n\n{e}")
                            st.stop()
                        st.success("走行距離を更新しました。")
                        st.rerun()

                # ---- 整備履歴（新しい順） ----
                st.markdown("**整備履歴**")
                car_records = sorted(
                    (r for r in records if r.car_id == c.id),
                    key=lambda r: r.date,
                    reverse=True,
                )
                if not car_records:
                    st.caption("まだ記録がありません。")
                else:
                    for r in car_records:
                        line_col, delete_col = st.columns([5, 1])
                        with line_col:
                            st.markdown(_record_line(r))
                        with delete_col:
                            if st.button("削除", key=f"delete-record-{r.id}"):
                                try:
                                    record_storage.delete_record(r.id)
                                except Exception as e:
                                    st.error(f"削除に失敗しました。\n\n{e}")
                                    st.stop()
                                st.rerun()

                # ---- 整備記録を追加するフォーム ----
                with st.form(f"add-record-{c.id}", clear_on_submit=True):
                    st.caption("整備記録を追加する")
                    rec_col1, rec_col2 = st.columns(2)
                    with rec_col1:
                        record_date = st.date_input(
                            "作業日", value=date.today(), format="YYYY/MM/DD"
                        )
                    with rec_col2:
                        record_type = st.selectbox(
                            "作業内容",
                            options=list(RecordType),
                            format_func=lambda t: RECORD_TYPE_LABELS[t],
                        )
                    rec_col3, rec_col4 = st.columns(2)
                    with rec_col3:
                        cost = st.number_input(
                            "費用（円・任意）", min_value=0, step=100, value=None
                        )
                    with rec_col4:
                        record_odometer_km = st.number_input(
                            "走行距離（km・任意）", min_value=0, step=100, value=None
                        )
                    memo = st.text_input("メモ（任意）", placeholder="例: 4本とも交換")
                    record_submitted = st.form_submit_button(
                        "記録を追加する", width="stretch"
                    )
                    if record_submitted:
                        try:
                            record_storage.add_record(
                                MaintenanceRecord(
                                    car_id=c.id,
                                    date=record_date,
                                    record_type=record_type,
                                    cost=int(cost) if cost is not None else None,
                                    memo=memo.strip(),
                                    odometer_km=(
                                        int(record_odometer_km)
                                        if record_odometer_km is not None
                                        else None
                                    ),
                                )
                            )
                        except Exception as e:
                            st.error(f"記録の追加に失敗しました。\n\n{e}")
                            st.stop()
                        st.success("整備記録を追加しました。")
                        st.rerun()

                if not editing:
                    if confirming_delete:
                        st.warning(
                            f"「{c.name}」を削除します。整備記録もすべて削除され、"
                            "元に戻せません。本当に削除しますか？"
                        )
                        confirm_col, cancel_col = st.columns(2)
                        with confirm_col:
                            if st.button(
                                "はい、削除する",
                                key=f"confirm-delete-{c.id}",
                                width="stretch",
                            ):
                                try:
                                    storage.delete_car(c.id)
                                    record_storage.delete_records_for_car(c.id)
                                except Exception as e:
                                    st.error(f"削除に失敗しました。\n\n{e}")
                                    st.stop()
                                st.session_state[f"confirm_delete_car_{c.id}"] = False
                                st.rerun()
                        with cancel_col:
                            if st.button(
                                "キャンセル",
                                key=f"cancel-delete-{c.id}",
                                width="stretch",
                            ):
                                st.session_state[f"confirm_delete_car_{c.id}"] = False
                                st.rerun()
                    else:
                        edit_btn_col, delete_btn_col = st.columns(2)
                        with edit_btn_col:
                            if st.button(
                                "編集する", key=f"edit-{c.id}", width="stretch"
                            ):
                                st.session_state[f"editing_car_{c.id}"] = True
                                st.rerun()
                        with delete_btn_col:
                            if st.button(
                                "この車を削除する",
                                key=f"delete-{c.id}",
                                width="stretch",
                            ):
                                st.session_state[f"confirm_delete_car_{c.id}"] = True
                                st.rerun()


# =====================================================================
# 2. 車を追加するフォーム
# =====================================================================
st.header("車を追加する")

with st.form("add-car-form", clear_on_submit=True):
    name = st.text_input("車の名前 *", placeholder="例: パパの車")
    owner = st.selectbox(
        "担当者",
        options=["（未設定）"] + config.PERSON_IN_CHARGE,
        help="選択肢を増やしたり変えたりしたいときは src/config.py の PERSON_IN_CHARGE を編集してください。",
    )
    plate_number = st.text_input("ナンバー", placeholder="例: 品川 300 あ 12-34")
    inspection_due_date = st.date_input(
        "車検の期限日", value=None, format="YYYY/MM/DD"
    )

    ins_col1, ins_col2 = st.columns(2)
    with ins_col1:
        compulsory_insurance_due_date = st.date_input(
            "自賠責保険の満期日", value=None, format="YYYY/MM/DD"
        )
    with ins_col2:
        voluntary_insurance_due_date = st.date_input(
            "任意保険の満期日", value=None, format="YYYY/MM/DD"
        )

    current_odometer_km = st.number_input(
        "現在の総走行距離（km・任意）", min_value=0, step=100, value=None
    )

    delivery_col1, delivery_col2 = st.columns(2)
    with delivery_col1:
        delivery_date = st.date_input(
            "納車日（任意）", value=None, format="YYYY/MM/DD"
        )
    with delivery_col2:
        delivery_odometer_km = st.number_input(
            "納車時の走行距離（km・任意）", min_value=0, step=100, value=None
        )

    st.caption("直近の交換日が分かれば、整備履歴の1件目として登録されます（任意）。")
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
            new_car = Car(
                name=name.strip(),
                owner="" if owner == "（未設定）" else owner,
                plate_number=plate_number.strip(),
                inspection_due_date=inspection_due_date,
                compulsory_insurance_due_date=compulsory_insurance_due_date,
                voluntary_insurance_due_date=voluntary_insurance_due_date,
                current_odometer_km=(
                    int(current_odometer_km) if current_odometer_km is not None else None
                ),
                delivery_date=delivery_date,
                delivery_odometer_km=(
                    int(delivery_odometer_km)
                    if delivery_odometer_km is not None
                    else None
                ),
            )
            try:
                storage.add_car(new_car)
                if last_oil_change_date:
                    record_storage.add_record(
                        MaintenanceRecord(
                            car_id=new_car.id,
                            date=last_oil_change_date,
                            record_type=RecordType.OIL,
                        )
                    )
                if last_tire_change_date:
                    record_storage.add_record(
                        MaintenanceRecord(
                            car_id=new_car.id,
                            date=last_tire_change_date,
                            record_type=RecordType.TIRE,
                        )
                    )
            except Exception as e:
                st.error(f"追加に失敗しました。\n\n{e}")
                st.stop()
            st.success(f"「{name.strip()}」を追加しました。")
            st.rerun()
