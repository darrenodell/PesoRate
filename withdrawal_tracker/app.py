"""Peso Withdrawal / Conversion Tracker.

A local Streamlit app for logging Philippine peso withdrawals (ATM) and
Wise conversions, computing effective exchange rates, and comparing them
against a monthly reference rate.
"""

from __future__ import annotations

import os
from datetime import date as date_cls, datetime
from io import StringIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
TRANSACTIONS_CSV = os.path.join(DATA_DIR, "transactions.csv")
DAILY_RATES_CSV = os.path.join(DATA_DIR, "daily_rates.csv")

TRANSACTION_COLUMNS = [
    "date",
    "method",
    "peso_amount",
    "usd_amount",
    "fees_usd",
    "notes",
]

DAILY_RATE_COLUMNS = ["date", "reference_rate"]

METHODS = ["ATM", "Wise"]


def ensure_storage() -> None:
    """Create data directory and empty CSV files if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    if not os.path.exists(TRANSACTIONS_CSV):
        pd.DataFrame(columns=TRANSACTION_COLUMNS).to_csv(TRANSACTIONS_CSV, index=False)
    if not os.path.exists(DAILY_RATES_CSV):
        pd.DataFrame(columns=DAILY_RATE_COLUMNS).to_csv(DAILY_RATES_CSV, index=False)


def save_report_snapshot(df: pd.DataFrame, prefix: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(REPORTS_DIR, f"{prefix}_{ts}.csv")
    df.to_csv(path, index=False)


def load_transactions() -> pd.DataFrame:
    df = pd.read_csv(TRANSACTIONS_CSV)
    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        for col in ("peso_amount", "usd_amount", "fees_usd"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["notes"] = df["notes"].fillna("")
    return df[TRANSACTION_COLUMNS]


def load_daily_rates() -> pd.DataFrame:
    df = pd.read_csv(DAILY_RATES_CSV)
    for col in DAILY_RATE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df["reference_rate"] = pd.to_numeric(df["reference_rate"], errors="coerce")
    return df[DAILY_RATE_COLUMNS]


def append_transaction(row: dict) -> None:
    df = load_transactions()
    new_row = pd.DataFrame([row], columns=TRANSACTION_COLUMNS)
    combined = pd.concat([df, new_row], ignore_index=True)
    combined.to_csv(TRANSACTIONS_CSV, index=False)


def upsert_daily_rate(rate_date: date_cls, rate: float) -> None:
    df = load_daily_rates()
    mask = df["date"] == rate_date
    if mask.any():
        df.loc[mask, "reference_rate"] = rate
    else:
        new_row = pd.DataFrame(
            [{"date": rate_date, "reference_rate": rate}],
            columns=DAILY_RATE_COLUMNS,
        )
        df = pd.concat([df, new_row], ignore_index=True)
    df.sort_values("date", inplace=True)
    df.to_csv(DAILY_RATES_CSV, index=False)


def enrich_transactions(tx: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    """Add calculated columns: net_usd_cost, effective_rate, and reference comparison."""
    if tx.empty:
        return pd.DataFrame(
            columns=TRANSACTION_COLUMNS
            + [
                "net_usd_cost",
                "effective_rate",
                "month",
                "year",
                "reference_rate",
                "rate_difference",
                "reference_usd_cost",
                "usd_gain_loss_vs_reference",
            ]
        )

    df = tx.copy()
    df["net_usd_cost"] = df["usd_amount"] + df["fees_usd"]
    df["effective_rate"] = df["peso_amount"] / df["net_usd_cost"]

    dates = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = dates.dt.month.astype("Int64")
    df["year"] = dates.dt.year.astype("Int64")

    if rates.empty:
        df["reference_rate"] = pd.NA
    else:
        rates_slim = rates.dropna(subset=["date", "reference_rate"])
        df = df.merge(rates_slim, on="date", how="left")

    df["rate_difference"] = df["effective_rate"] - df["reference_rate"]
    df["reference_usd_cost"] = df["peso_amount"] / df["reference_rate"]
    df["usd_gain_loss_vs_reference"] = df["reference_usd_cost"] - df["net_usd_cost"]
    return df


def build_monthly_summary(enriched: pd.DataFrame) -> pd.DataFrame:
    if enriched.empty:
        return pd.DataFrame()

    df = enriched.copy()
    df["atm_effective_rate"] = df["effective_rate"].where(df["method"] == "ATM")
    df["wise_effective_rate"] = df["effective_rate"].where(df["method"] == "Wise")
    df["atm_fee"] = df["fees_usd"].where(
        (df["method"] == "ATM") & (df["fees_usd"] > 0), 0
    )
    df["wise_fee"] = df["fees_usd"].where(
        (df["method"] == "Wise") & (df["fees_usd"] > 0), 0
    )

    grouped = df.groupby(["year", "month"], dropna=False).agg(
        total_peso=("peso_amount", "sum"),
        total_net_usd_cost=("net_usd_cost", "sum"),
        avg_effective_rate=("effective_rate", "mean"),
        avg_atm_rate=("atm_effective_rate", "mean"),
        avg_wise_rate=("wise_effective_rate", "mean"),
        total_atm_fees=("atm_fee", "sum"),
        total_wise_fees=("wise_fee", "sum"),
        total_gain_loss_vs_reference=("usd_gain_loss_vs_reference", "sum"),
    ).reset_index()

    def pick_best(row: pd.Series) -> str:
        atm, wise = row["avg_atm_rate"], row["avg_wise_rate"]
        if pd.isna(atm) and pd.isna(wise):
            return ""
        if pd.isna(atm):
            return "Wise"
        if pd.isna(wise):
            return "ATM"
        # Higher pesos-per-dollar means better value for the person converting USD.
        return "ATM" if atm >= wise else "Wise"

    grouped["best_method"] = grouped.apply(pick_best, axis=1)
    grouped.sort_values(["year", "month"], inplace=True)
    return grouped


def format_transactions_for_display(enriched: pd.DataFrame) -> pd.DataFrame:
    if enriched.empty:
        return enriched

    display = enriched.copy()
    display["date"] = pd.to_datetime(display["date"], errors="coerce").dt.strftime("%b %d, %Y")
    display = display[
        [
            "date",
            "method",
            "peso_amount",
            "usd_amount",
            "fees_usd",
            "net_usd_cost",
            "effective_rate",
            "reference_rate",
            "rate_difference",
            "usd_gain_loss_vs_reference",
            "notes",
        ]
    ].rename(
        columns={
            "date": "Date",
            "method": "Method",
            "peso_amount": "Peso Amount",
            "usd_amount": "USD Amount",
            "fees_usd": "Fees",
            "net_usd_cost": "Net USD Cost",
            "effective_rate": "Effective Rate",
            "reference_rate": "Daily Reference Rate",
            "rate_difference": "Rate Difference",
            "usd_gain_loss_vs_reference": "USD Gain/Loss vs Reference",
            "notes": "Notes",
        }
    )
    return display


def format_summary_for_display(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary

    display = summary.copy()
    display["Month"] = display.apply(
        lambda r: (
            f"{int(r['year']):04d}-{int(r['month']):02d}"
            if pd.notna(r["year"]) and pd.notna(r["month"])
            else ""
        ),
        axis=1,
    )
    display = display[
        [
            "Month",
            "total_peso",
            "total_net_usd_cost",
            "avg_effective_rate",
            "avg_atm_rate",
            "avg_wise_rate",
            "total_atm_fees",
            "total_wise_fees",
            "total_gain_loss_vs_reference",
            "best_method",
        ]
    ].rename(
        columns={
            "total_peso": "Total Peso",
            "total_net_usd_cost": "Total Net USD Cost",
            "avg_effective_rate": "Avg Effective Rate",
            "avg_atm_rate": "Avg ATM Rate",
            "avg_wise_rate": "Avg Wise Rate",
            "total_atm_fees": "Total ATM Fees",
            "total_wise_fees": "Total Wise Fees",
            "total_gain_loss_vs_reference": "Total Gain/Loss vs Ref",
            "best_method": "Best Method",
        }
    )
    return display


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _rate_for(rates: pd.DataFrame, d: date_cls) -> float | None:
    if rates.empty:
        return None
    match = rates[rates["date"] == d]
    if match.empty:
        return None
    val = match["reference_rate"].iloc[0]
    return None if pd.isna(val) else float(val)


def render_transaction_form(rates: pd.DataFrame) -> None:
    st.subheader("Add Transaction")

    today = date_cls.today()
    if _rate_for(rates, today) is None:
        st.warning(
            f"No Daily Reference Rate saved for today ({today.isoformat()}). "
            "Add one in the **Daily Reference Rate** section on the left sidebar "
            "to enable auto-conversion between USD and Peso."
        )

    defaults = {
        "tx_date": today,
        "tx_method": METHODS[0],
        "tx_peso": 0.0,
        "tx_usd": 0.0,
        "tx_fees": 0.0,
        "tx_notes": "",
    }
    if st.session_state.pop("_tx_reset", False):
        for k, v in defaults.items():
            st.session_state[k] = v
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    last_saved = st.session_state.pop("_tx_last_saved", None)
    if last_saved:
        st.success(last_saved)

    def on_usd_change() -> None:
        if st.session_state.tx_usd <= 0:
            return
        r = _rate_for(rates, st.session_state.tx_date)
        if r:
            st.session_state.tx_peso = round(st.session_state.tx_usd * r, 2)
        else:
            st.session_state._missing_rate_notify = st.session_state.tx_date

    def on_peso_change() -> None:
        if st.session_state.tx_peso <= 0:
            return
        r = _rate_for(rates, st.session_state.tx_date)
        if r:
            st.session_state.tx_usd = round(st.session_state.tx_peso / r, 2)
        else:
            st.session_state._missing_rate_notify = st.session_state.tx_date

    col1, col2 = st.columns(2)
    with col1:
        st.date_input("Date", key="tx_date")
        st.number_input(
            "USD Amount",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="tx_usd",
            on_change=on_usd_change,
        )
        st.number_input(
            "Peso Amount",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            key="tx_peso",
            on_change=on_peso_change,
        )
    with col2:
        st.selectbox("Method", METHODS, key="tx_method")
        st.number_input(
            "Fees (USD)",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            key="tx_fees",
        )
        st.text_input("Notes", key="tx_notes")

    st_components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const attach = () => {
                doc.querySelectorAll('input[type="number"]').forEach(inp => {
                    if (inp.closest('[data-testid="stSidebar"]')) return;
                    if (inp.dataset.autoselectAttached === 'true') return;
                    inp.dataset.autoselectAttached = 'true';
                    inp.addEventListener('focus', () => setTimeout(() => inp.select(), 0));
                });
            };
            attach();
            setTimeout(attach, 300);
            setTimeout(attach, 1000);
        })();
        </script>
        """,
        height=0,
    )

    notify_date = st.session_state.pop("_missing_rate_notify", None)
    if notify_date:
        st.toast(
            f"No daily reference rate for {notify_date.isoformat()} — "
            "please add one in the Daily Reference Rate section."
        )
        st_components.html(
            """
            <script>
                setTimeout(function () {
                    try {
                        const doc = window.parent.document;
                        const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                        if (!sidebar) return;
                        const input = sidebar.querySelector('input');
                        if (input) input.focus();
                    } catch (e) {}
                }, 150);
            </script>
            """,
            height=0,
        )

    submitted = st.button("Save Transaction")

    if submitted:
        tx_date = st.session_state.tx_date
        method = st.session_state.tx_method
        peso_amount = float(st.session_state.tx_peso)
        usd_amount = float(st.session_state.tx_usd)
        fees_usd = float(st.session_state.tx_fees)
        notes = st.session_state.tx_notes

        errors = []
        if tx_date is None:
            errors.append("Date is required.")
        if not method:
            errors.append("Method is required.")
        if peso_amount <= 0:
            errors.append("Peso amount must be greater than zero.")
        if usd_amount <= 0:
            errors.append("USD amount must be greater than zero.")
        net = usd_amount + fees_usd
        if net <= 0:
            errors.append("Net USD cost must be greater than zero.")

        if errors:
            for err in errors:
                st.error(err)
            return

        append_transaction(
            {
                "date": tx_date.isoformat(),
                "method": method,
                "peso_amount": round(peso_amount, 2),
                "usd_amount": round(usd_amount, 2),
                "fees_usd": round(fees_usd, 2),
                "notes": notes.strip(),
            }
        )
        st.session_state._tx_last_saved = (
            f"Saved: {method} on {tx_date.isoformat()} — "
            f"effective rate {peso_amount / net:.4f}"
        )
        st.session_state._tx_reset = True
        st.rerun()


def render_daily_rate_sidebar(rates: pd.DataFrame) -> None:
    st.sidebar.header("Daily Reference Rate")
    with st.sidebar.form("daily_rate_form", clear_on_submit=False):
        rate_date = st.date_input("Date", value=date_cls.today())
        reference_rate = st.number_input(
            "Reference Rate (PHP per USD)",
            min_value=0.0,
            step=0.0001,
            format="%.4f",
        )
        submitted = st.form_submit_button("Save / Update Rate")

    if submitted:
        if reference_rate <= 0:
            st.sidebar.error("Reference rate must be greater than zero.")
        elif rate_date is None:
            st.sidebar.error("Date is required.")
        else:
            upsert_daily_rate(rate_date, float(reference_rate))
            st.sidebar.success(f"Saved rate for {rate_date.isoformat()}: {reference_rate:.4f}")
            st.rerun()

    if not rates.empty:
        st.sidebar.markdown("**Saved Rates**")
        display_rates = rates.copy().sort_values("date", ascending=False)
        display_rates["Date"] = pd.to_datetime(display_rates["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        st.sidebar.dataframe(
            display_rates[["Date", "reference_rate"]].rename(
                columns={"reference_rate": "Rate"}
            ),
            hide_index=True,
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="PesoRate Tracker", layout="wide")
    ensure_storage()

    st.title("PesoRate Tracker")

    rates = load_daily_rates()
    render_daily_rate_sidebar(rates)

    render_transaction_form(rates)

    transactions = load_transactions()
    enriched = enrich_transactions(transactions, rates)

    st.subheader("Transactions")
    if enriched.empty:
        st.info("No transactions yet. Add your first one using the form above.")
    else:
        display = format_transactions_for_display(enriched).sort_values(
            "Date", ascending=False, kind="stable"
        )
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Peso Amount": st.column_config.NumberColumn(format="%.2f"),
                "USD Amount": st.column_config.NumberColumn(format="%.2f"),
                "Fees": st.column_config.NumberColumn(format="%.2f"),
                "Net USD Cost": st.column_config.NumberColumn(format="%.2f"),
                "Effective Rate": st.column_config.NumberColumn(format="%.4f"),
                "Daily Reference Rate": st.column_config.NumberColumn(format="%.4f"),
                "Rate Difference": st.column_config.NumberColumn(format="%.4f"),
                "USD Gain/Loss vs Reference": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button(
            "Download transactions CSV",
            data=df_to_csv_bytes(display),
            file_name="transactions_export.csv",
            mime="text/csv",
            on_click=save_report_snapshot,
            args=(display, "transactions_report"),
        )

    st.subheader("Monthly Summary")
    summary = build_monthly_summary(enriched)
    if summary.empty:
        st.info("Monthly summary will appear once transactions are added.")
    else:
        summary_display = format_summary_for_display(summary)
        st.dataframe(
            summary_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Total Peso": st.column_config.NumberColumn(format="%.2f"),
                "Total Net USD Cost": st.column_config.NumberColumn(format="%.2f"),
                "Avg Effective Rate": st.column_config.NumberColumn(format="%.4f"),
                "Avg ATM Rate": st.column_config.NumberColumn(format="%.4f"),
                "Avg Wise Rate": st.column_config.NumberColumn(format="%.4f"),
                "Total ATM Fees": st.column_config.NumberColumn(format="%.2f"),
                "Total Wise Fees": st.column_config.NumberColumn(format="%.2f"),
                "Total Gain/Loss vs Ref": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button(
            "Download monthly summary CSV",
            data=df_to_csv_bytes(summary_display),
            file_name="monthly_summary_export.csv",
            mime="text/csv",
            on_click=save_report_snapshot,
            args=(summary_display, "monthly_summary_report"),
        )


if __name__ == "__main__":
    main()
