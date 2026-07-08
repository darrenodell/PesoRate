"""Peso Withdrawal / Conversion Tracker.

A local Streamlit app for logging Philippine peso withdrawals (ATM) and
Wise conversions, computing effective exchange rates, and comparing them
against a monthly reference rate.
"""

from __future__ import annotations

import os
from datetime import date as date_cls
from io import StringIO

import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TRANSACTIONS_CSV = os.path.join(DATA_DIR, "transactions.csv")
MONTHLY_RATES_CSV = os.path.join(DATA_DIR, "monthly_rates.csv")

TRANSACTION_COLUMNS = [
    "date",
    "method",
    "peso_amount",
    "usd_amount",
    "adjustment_usd",
    "notes",
]

MONTHLY_RATE_COLUMNS = ["month", "year", "reference_rate"]

METHODS = ["ATM", "Wise"]


def ensure_storage() -> None:
    """Create data directory and empty CSV files if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TRANSACTIONS_CSV):
        pd.DataFrame(columns=TRANSACTION_COLUMNS).to_csv(TRANSACTIONS_CSV, index=False)
    if not os.path.exists(MONTHLY_RATES_CSV):
        pd.DataFrame(columns=MONTHLY_RATE_COLUMNS).to_csv(MONTHLY_RATES_CSV, index=False)


def load_transactions() -> pd.DataFrame:
    df = pd.read_csv(TRANSACTIONS_CSV)
    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        for col in ("peso_amount", "usd_amount", "adjustment_usd"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["notes"] = df["notes"].fillna("")
    return df[TRANSACTION_COLUMNS]


def load_monthly_rates() -> pd.DataFrame:
    df = pd.read_csv(MONTHLY_RATES_CSV)
    for col in MONTHLY_RATE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="float")
    if not df.empty:
        df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["reference_rate"] = pd.to_numeric(df["reference_rate"], errors="coerce")
    return df[MONTHLY_RATE_COLUMNS]


def append_transaction(row: dict) -> None:
    df = load_transactions()
    new_row = pd.DataFrame([row], columns=TRANSACTION_COLUMNS)
    combined = pd.concat([df, new_row], ignore_index=True)
    combined.to_csv(TRANSACTIONS_CSV, index=False)


def upsert_monthly_rate(month: int, year: int, rate: float) -> None:
    df = load_monthly_rates()
    mask = (df["month"] == month) & (df["year"] == year)
    if mask.any():
        df.loc[mask, "reference_rate"] = rate
    else:
        new_row = pd.DataFrame(
            [{"month": month, "year": year, "reference_rate": rate}],
            columns=MONTHLY_RATE_COLUMNS,
        )
        df = pd.concat([df, new_row], ignore_index=True)
    df.sort_values(["year", "month"], inplace=True)
    df.to_csv(MONTHLY_RATES_CSV, index=False)


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
    df["net_usd_cost"] = df["usd_amount"] - df["adjustment_usd"]
    df["effective_rate"] = df["peso_amount"] / df["net_usd_cost"]

    dates = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = dates.dt.month.astype("Int64")
    df["year"] = dates.dt.year.astype("Int64")

    if rates.empty:
        df["reference_rate"] = pd.NA
    else:
        rates_slim = rates.dropna(subset=["month", "year", "reference_rate"])
        df = df.merge(rates_slim, on=["month", "year"], how="left")

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
    df["atm_rebate"] = df["adjustment_usd"].where(
        (df["method"] == "ATM") & (df["adjustment_usd"] > 0), 0
    )
    df["wise_fee"] = (-df["adjustment_usd"]).where(
        (df["method"] == "Wise") & (df["adjustment_usd"] < 0), 0
    )

    grouped = df.groupby(["year", "month"], dropna=False).agg(
        total_peso=("peso_amount", "sum"),
        total_net_usd_cost=("net_usd_cost", "sum"),
        avg_effective_rate=("effective_rate", "mean"),
        avg_atm_rate=("atm_effective_rate", "mean"),
        avg_wise_rate=("wise_effective_rate", "mean"),
        total_atm_rebates=("atm_rebate", "sum"),
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
            "adjustment_usd",
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
            "adjustment_usd": "Adjustment",
            "net_usd_cost": "Net USD Cost",
            "effective_rate": "Effective Rate",
            "reference_rate": "Monthly Reference Rate",
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
            "total_atm_rebates",
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
            "total_atm_rebates": "Total ATM Rebates",
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


def render_transaction_form() -> None:
    st.subheader("Add Transaction")
    with st.form("transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tx_date = st.date_input("Date", value=date_cls.today())
            method = st.selectbox("Method", METHODS)
            peso_amount = st.number_input(
                "Peso Amount", min_value=0.0, step=100.0, format="%.2f"
            )
        with col2:
            usd_amount = st.number_input(
                "USD Amount", min_value=0.0, step=1.0, format="%.2f"
            )
            adjustment_usd = st.number_input(
                "Adjustment (USD)",
                value=0.0,
                step=0.01,
                format="%.2f",
                help="Positive for ATM rebates, negative for Wise fees.",
            )
            notes = st.text_input("Notes", value="")

        submitted = st.form_submit_button("Save Transaction")

    if submitted:
        errors = []
        if tx_date is None:
            errors.append("Date is required.")
        if not method:
            errors.append("Method is required.")
        if peso_amount <= 0:
            errors.append("Peso amount must be greater than zero.")
        if usd_amount <= 0:
            errors.append("USD amount must be greater than zero.")
        net = usd_amount - adjustment_usd
        if net <= 0:
            errors.append("Net USD cost (USD - adjustment) must be greater than zero.")

        if errors:
            for err in errors:
                st.error(err)
            return

        append_transaction(
            {
                "date": tx_date.isoformat(),
                "method": method,
                "peso_amount": round(float(peso_amount), 2),
                "usd_amount": round(float(usd_amount), 2),
                "adjustment_usd": round(float(adjustment_usd), 2),
                "notes": notes.strip(),
            }
        )
        st.success(
            f"Saved: {method} on {tx_date.isoformat()} — "
            f"effective rate {peso_amount / net:.4f}"
        )
        st.rerun()


def render_monthly_rate_sidebar(rates: pd.DataFrame) -> None:
    st.sidebar.header("Monthly Reference Rate")
    today = date_cls.today()
    with st.sidebar.form("monthly_rate_form", clear_on_submit=False):
        month = st.number_input("Month", min_value=1, max_value=12, value=today.month, step=1)
        year = st.number_input(
            "Year", min_value=2000, max_value=2100, value=today.year, step=1
        )
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
        else:
            upsert_monthly_rate(int(month), int(year), float(reference_rate))
            st.sidebar.success(f"Saved rate for {int(year)}-{int(month):02d}: {reference_rate:.4f}")
            st.rerun()

    if not rates.empty:
        st.sidebar.markdown("**Saved Rates**")
        display_rates = rates.copy()
        display_rates["Period"] = display_rates.apply(
            lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}", axis=1
        )
        st.sidebar.dataframe(
            display_rates[["Period", "reference_rate"]].rename(
                columns={"reference_rate": "Rate"}
            ),
            hide_index=True,
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="Peso Withdrawal / Conversion Tracker", layout="wide")
    ensure_storage()

    st.title("Peso Withdrawal / Conversion Tracker")

    rates = load_monthly_rates()
    render_monthly_rate_sidebar(rates)

    render_transaction_form()

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
                "Adjustment": st.column_config.NumberColumn(format="%.2f"),
                "Net USD Cost": st.column_config.NumberColumn(format="%.2f"),
                "Effective Rate": st.column_config.NumberColumn(format="%.4f"),
                "Monthly Reference Rate": st.column_config.NumberColumn(format="%.4f"),
                "Rate Difference": st.column_config.NumberColumn(format="%.4f"),
                "USD Gain/Loss vs Reference": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button(
            "Download transactions CSV",
            data=df_to_csv_bytes(display),
            file_name="transactions_export.csv",
            mime="text/csv",
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
                "Total ATM Rebates": st.column_config.NumberColumn(format="%.2f"),
                "Total Wise Fees": st.column_config.NumberColumn(format="%.2f"),
                "Total Gain/Loss vs Ref": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button(
            "Download monthly summary CSV",
            data=df_to_csv_bytes(summary_display),
            file_name="monthly_summary_export.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
