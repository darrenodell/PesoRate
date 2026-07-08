# PesoRate Tracker

A small local app for tracking Philippine peso withdrawals (from ATMs) and
Wise USD-to-PHP conversions. It automatically calculates your **effective
exchange rate** on each transaction and compares it against a daily
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

### Set a daily reference rate (sidebar)

Use the left sidebar to enter the reference rate for a given date. This is
the rate you'll compare each transaction against. Saving with the same date
again will update the existing rate. Only transactions on days that have a
saved rate will show a comparison.

### Add a transaction (main page)

Fill in:

- **Date** — the day of the transaction.
- **Method** — `ATM` or `Wise`.
- **Peso Amount** — pesos received or converted.
- **USD Amount** — USD debited from your account.
- **Fees (USD)** — any USD fee paid on the transaction (ATM surcharge or
  Wise fee). Positive number; leave at `0` if none.
- **Notes** — anything you want to remember (which bank, which card, etc.).

Click **Save Transaction**.

### Calculations

```
net_usd_cost   = usd_amount + fees_usd
effective_rate = peso_amount / net_usd_cost
```

**Example 1 — ATM with surcharge**

```
peso_amount    = 20,000.00
usd_amount     = 330.09
fees           = 4.08

net_usd_cost   = 330.09 + 4.08 = 334.17
effective_rate = 20000 / 334.17 = 59.8497
```

**Example 2 — Wise with fee**

```
peso_amount    = 10,035.00
usd_amount     = 162.86
fees           = 1.21

net_usd_cost   = 162.86 + 1.21 = 164.07
effective_rate = 10035 / 164.07 = 61.1629
```

### Comparison against the daily reference rate

For each transaction, the app also computes:

```
rate_difference             = effective_rate - reference_rate
reference_usd_cost          = peso_amount / reference_rate
usd_gain_loss_vs_reference  = reference_usd_cost - net_usd_cost
```

- **Positive** gain/loss = you did **better** than that day's reference.
- **Negative** gain/loss = you did **worse** than that day's reference.

### Monthly summary

Grouped by month, showing total pesos, total net USD cost, average
effective rate overall and per method, total ATM fees, total Wise fees,
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
    daily_rates.csv    # your daily reference rates
  sample_data.csv      # example rows in the expected format
```

CSV files are created automatically the first time you run the app. Your
data never leaves your computer.
