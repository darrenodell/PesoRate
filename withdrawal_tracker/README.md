# Peso Withdrawal / Conversion Tracker

A small local app for tracking Philippine peso withdrawals (from ATMs) and
Wise USD-to-PHP conversions. It automatically calculates your **effective
exchange rate** on each transaction and compares it against a monthly
reference rate you set.

No cloud accounts, no logins, no API keys. Everything is stored in local
CSV files inside the `data/` folder.

---

## 1. Install Python

You need Python 3.9 or newer.

- **macOS**: open Terminal and run `python3 --version`. If it prints a
  version, you're set. Otherwise, install from
  [python.org/downloads](https://www.python.org/downloads/) or via Homebrew:
  `brew install python`.
- **Windows**: download the installer from
  [python.org/downloads](https://www.python.org/downloads/). During install,
  check the box **"Add Python to PATH"**.

Verify with:

```
python3 --version
```

## 2. Install the app's dependencies

Open a terminal, `cd` into this folder, and run:

```
pip install -r requirements.txt
```

If `pip` isn't found, try `pip3` instead.

## 3. Run the app

From this folder:

```
streamlit run app.py
```

Your browser will open at `http://localhost:8501` with the tracker.

To stop the app, press `Ctrl+C` in the terminal.

---

## Using the app

### Set a monthly reference rate (sidebar)

Use the left sidebar to enter the reference rate for a given month/year.
This is the rate you'll compare each transaction against. Saving with the
same month/year again will update the existing rate.

### Add a transaction (main page)

Fill in:

- **Date** — the day of the transaction.
- **Method** — `ATM` or `Wise`.
- **Peso Amount** — pesos received or converted.
- **USD Amount** — USD debited from your account.
- **Adjustment (USD)** — signed rebate or fee (see below).
- **Notes** — anything you want to remember (which bank, which card, etc.).

Click **Save Transaction**.

### The Adjustment field — SIGNED

This field is signed, so the sign matters:

- **ATM rebate of $4.08** → enter `4.08` (positive)
- **Wise fee of $1.21** → enter `-1.21` (negative)

The formula treats rebates as reducing your USD cost, and fees as adding
to it.

### Calculations

```
net_usd_cost   = usd_amount - adjustment_usd
effective_rate = peso_amount / net_usd_cost
```

**Example 1 — ATM with rebate**

```
peso_amount    = 20,000.00
usd_amount     = 330.09
adjustment     = 4.08

net_usd_cost   = 330.09 - 4.08 = 326.01
effective_rate = 20000 / 326.01 = 61.3478
```

**Example 2 — Wise with fee**

```
peso_amount    = 10,035.00
usd_amount     = 162.86
adjustment     = -1.21

net_usd_cost   = 162.86 - (-1.21) = 164.07
effective_rate = 10035 / 164.07 = 61.1629
```

### Comparison against the monthly reference rate

For each transaction, the app also computes:

```
rate_difference             = effective_rate - reference_rate
reference_usd_cost          = peso_amount / reference_rate
usd_gain_loss_vs_reference  = reference_usd_cost - net_usd_cost
```

- **Positive** gain/loss = you did **better** than the monthly reference.
- **Negative** gain/loss = you did **worse** than the monthly reference.

### Monthly summary

Grouped by month, showing total pesos, total net USD cost, average
effective rate overall and per method, total ATM rebates, total Wise fees,
total gain/loss vs. reference, and which method had the better average
effective rate that month.

### Export

Download buttons under each table export the current view to CSV.

---

## Files

```
withdrawal_tracker/
  app.py               # the Streamlit app
  requirements.txt     # Python dependencies
  README.md            # this file
  data/
    transactions.csv   # your saved transactions
    monthly_rates.csv  # your monthly reference rates
  sample_data.csv      # example rows in the expected format
```

CSV files are created automatically the first time you run the app. Your
data never leaves your computer.
