"""Peso Withdrawal / Conversion Tracker.

A local Streamlit app for logging Philippine peso withdrawals (ATM) and
Wise conversions, computing effective exchange rates, and comparing them
against a daily reference rate.
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

# When true, persist data to CSV files under data/ (local single-user mode).
# When false (default), data lives in st.session_state and each browser tab is
# an independent session — used for the deployed multi-user version.
LOCAL_MODE = os.environ.get("PESORATE_LOCAL_MODE", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

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


# Map display-format column names back to raw column names so a CSV downloaded
# from the app's Transactions table can be re-uploaded as-is.
TRANSACTIONS_DISPLAY_TO_RAW = {
    "Date": "date",
    "Method": "method",
    "Peso Amount": "peso_amount",
    "USD Amount": "usd_amount",
    "Fees": "fees_usd",
    "Notes": "notes",
}


def _clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=TRANSACTIONS_DISPLAY_TO_RAW)
    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        for col in ("peso_amount", "usd_amount", "fees_usd"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["notes"] = df["notes"].fillna("")
    return df[TRANSACTION_COLUMNS].reset_index(drop=True)


def ensure_storage() -> None:
    """Create data/reports directories and empty transactions CSV in LOCAL_MODE."""
    if not LOCAL_MODE:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    if not os.path.exists(TRANSACTIONS_CSV):
        pd.DataFrame(columns=TRANSACTION_COLUMNS).to_csv(TRANSACTIONS_CSV, index=False)


def save_report_snapshot(df: pd.DataFrame, prefix: str) -> None:
    if not LOCAL_MODE:
        return
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(REPORTS_DIR, f"{prefix}_{ts}.csv")
    df.to_csv(path, index=False)


def load_transactions() -> pd.DataFrame:
    if LOCAL_MODE:
        return _clean_transactions(pd.read_csv(TRANSACTIONS_CSV))
    df = st.session_state.get("transactions_df")
    if df is None:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return df.copy()


def load_daily_rates() -> pd.DataFrame:
    df = st.session_state.get("daily_rates_df")
    if df is None:
        return pd.DataFrame(columns=DAILY_RATE_COLUMNS)
    return df.copy()


def append_transaction(row: dict) -> None:
    df = load_transactions()
    new_row = pd.DataFrame([row], columns=TRANSACTION_COLUMNS)
    combined = pd.concat([df, new_row], ignore_index=True)
    if LOCAL_MODE:
        combined.to_csv(TRANSACTIONS_CSV, index=False)
    else:
        st.session_state.transactions_df = combined


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
    df = df.sort_values("date").reset_index(drop=True)
    st.session_state.daily_rates_df = df


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
    # Wise fees are already baked into the USD Amount debited; ATM surcharges
    # are separate charges, so they only add to cost when not refunded.
    atm_fees = df["fees_usd"].where(df["method"] == "ATM", 0)
    df["net_usd_cost"] = df["usd_amount"] + atm_fees
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


def build_all_time_summary(enriched: pd.DataFrame) -> pd.DataFrame:
    if enriched.empty:
        return pd.DataFrame()

    df = enriched.copy()
    atm_rates = df["effective_rate"].where(df["method"] == "ATM")
    wise_rates = df["effective_rate"].where(df["method"] == "Wise")
    atm_fees = df["fees_usd"].where((df["method"] == "ATM") & (df["fees_usd"] > 0), 0)
    wise_fees = df["fees_usd"].where((df["method"] == "Wise") & (df["fees_usd"] > 0), 0)

    avg_atm = atm_rates.mean()
    avg_wise = wise_rates.mean()
    if pd.isna(avg_atm) and pd.isna(avg_wise):
        best = ""
    elif pd.isna(avg_atm):
        best = "Wise"
    elif pd.isna(avg_wise):
        best = "ATM"
    else:
        best = "ATM" if avg_atm >= avg_wise else "Wise"

    return pd.DataFrame([{
        "total_peso": df["peso_amount"].sum(),
        "total_net_usd_cost": df["net_usd_cost"].sum(),
        "avg_effective_rate": df["effective_rate"].mean(),
        "avg_atm_rate": avg_atm,
        "avg_wise_rate": avg_wise,
        "total_atm_fees": atm_fees.sum(),
        "total_wise_fees": wise_fees.sum(),
        "total_gain_loss_vs_reference": df["usd_gain_loss_vs_reference"].sum(),
        "best_method": best,
    }])


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

    display = summary[
        [
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

    with st.form("transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tx_date = st.date_input("Date", value=date_cls.today())
            tx_usd = st.number_input(
                "USD Amount",
                min_value=0.0,
                step=1.0,
                format="%.2f",
            )
            tx_peso = st.number_input(
                "Peso Amount",
                min_value=0.0,
                step=100.0,
                format="%.2f",
            )
        with col2:
            tx_method = st.selectbox("Method", METHODS)
            tx_fees = st.number_input(
                "Fees (USD)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
            )
            tx_notes = st.text_input("Notes")

        submitted = st.form_submit_button("Save Transaction")

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

    if submitted:
        peso_amount = float(tx_peso)
        usd_amount = float(tx_usd)
        fees_usd = float(tx_fees)

        errors = []
        if tx_date is None:
            errors.append("Date is required.")
        if not tx_method:
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
                "method": tx_method,
                "peso_amount": round(peso_amount, 2),
                "usd_amount": round(usd_amount, 2),
                "fees_usd": round(fees_usd, 2),
                "notes": tx_notes.strip(),
            }
        )
        st.success(
            f"Saved: {tx_method} on {tx_date.isoformat()} — "
            f"effective rate {peso_amount / net:.4f}"
        )


def render_data_io_sidebar() -> None:
    """Session-mode-only sidebar section: upload prior CSV into this tab."""
    if LOCAL_MODE:
        return
    st.sidebar.header("Load / Save Data")
    st.sidebar.caption(
        "Your transactions live only in this browser tab. Upload a saved "
        "**transactions.csv** to pick up where you left off, and use the "
        "**Download** button under the Transactions table to save your "
        "progress before closing."
    )

    tx_file = st.sidebar.file_uploader(
        "Load transactions CSV", type="csv", key="tx_upload"
    )
    if tx_file is not None:
        fid = getattr(tx_file, "file_id", None) or tx_file.name
        if st.session_state.get("_tx_upload_fid") != fid:
            try:
                df = _clean_transactions(pd.read_csv(tx_file))
                st.session_state.transactions_df = df
                st.session_state._tx_upload_fid = fid
                st.sidebar.success(
                    f"Loaded {len(df)} transaction(s) from {tx_file.name}"
                )
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Could not read transactions CSV: {e}")

    st.sidebar.divider()


def render_onboarding(transactions: pd.DataFrame) -> None:
    """Session-mode-only welcome shown until the user has at least one transaction."""
    if LOCAL_MODE or not transactions.empty:
        return
    st.info(
        "**Welcome to PesoRate Tracker.**  \n"
        "Track your Wise USD→PHP conversions and ATM withdrawals to see your "
        "true effective rate on each transaction and compare it against a "
        "reference rate.\n\n"
        "- **Starting fresh?** Just add your first transaction using the form below.\n"
        "- **Coming back?** Upload your saved **transactions.csv** from **Load / Save Data** in the sidebar.\n\n"
        "Your data lives only in this browser tab — **use the Download button "
        "under the Transactions table before closing** to save your progress. "
        "Daily reference rates are session-only; re-enter them each visit."
    )


def render_daily_rate_sidebar(rates: pd.DataFrame) -> None:
    st.sidebar.header("Daily Reference Rate")
    with st.sidebar.form("daily_rate_form", clear_on_submit=True):
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
            rates = load_daily_rates()

    if not rates.empty:
        st.sidebar.markdown("**Saved Rates**")
        display_rates = rates.copy().sort_values("date", ascending=False)
        display_rates["Date"] = pd.to_datetime(display_rates["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        rates_table = display_rates[["Date", "reference_rate"]].rename(
            columns={"reference_rate": "Rate"}
        )
        st.sidebar.dataframe(
            rates_table,
            hide_index=True,
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="PesoRate Tracker", layout="wide")
    ensure_storage()

    st.title("PesoRate Tracker")

    render_data_io_sidebar()

    rates = load_daily_rates()
    render_daily_rate_sidebar(rates)
    rates = load_daily_rates()

    transactions = load_transactions()
    render_onboarding(transactions)

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

    st.subheader("All-Time Summary")
    summary = build_all_time_summary(enriched)
    if summary.empty:
        st.info("Summary will appear once transactions are added.")
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


if __name__ == "__main__":
    main()
