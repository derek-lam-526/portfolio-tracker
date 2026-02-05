# Portfolio Performance Tracker

A comprehensive, Python-based investment portfolio tracker that automates data fetching, calculates professional-grade risk metrics, and generates an interactive HTML dashboard. 

Built with **Pandas**, **yfinance**, and **Plotly**, this tool reconstructs your portfolio's daily history from a simple list of trades to provide deep insights into your investing performance.

## 🚀 Key Features

* **Automated Data Engine**: Fetches historical price data (Daily & Minute resolution) using `yfinance`.
* **Smart Caching**: Caches market data and metadata locally (`data/portfolio_metadata.pkl`) to significantly speed up subsequent runs and minimize API rate limits.
* **Advanced Risk Analysis**:
    * **Performance**: Cumulative Returns, Daily PnL, Drawdowns.
    * **Metrics**: Sharpe Ratio, Sortino Ratio, Alpha, Beta (vs SPY), Value at Risk (VaR 95%), and Tracking Error.
    * **Concentration**: Analyzes top holdings and sector allocation.
* **Interactive Dashboard**: 
    * Generates a standalone HTML file with zoomable Plotly charts.
    * Includes a **searchable, sortable Holdings Table** using DataTables.
    * Visualizes Monthly Returns with a heatmap.
* **Cash Flow Management**: accurately handles Deposits and Withdrawals to track Invested Capital vs. Market Value.

---

## 📂 Project Structure

* `main.py`: The entry point. Orchestrates the workflow from data loading to report generation.
* `config.py`: Central configuration. Manages file paths, constants (like Benchmarks), and environment variables.
* `portfolio_tracker.py`: Core engine. Reconstructs portfolio state day-by-day, handles dividends/splits, and manages the data cache.
* `portfolio_analyzer.py`: Statistical engine. Calculates all financial metrics (Alpha, Beta, etc.) and prepares plot data.
* `report_manager.py`: Renders the final HTML report, embedding plots and JavaScript for interactivity.
* `data_manager.py`: Utilities for reading your Excel trade log and converting it to a standardized CSV.

---

## ⚙️ Configuration & Setup

This project uses `python-dotenv` to manage sensitive paths and configuration separate from the code.

### 1. Environment Variables (`.env`)
Create a file named `.env` in the root directory of the project. Add the absolute path to your trade Excel file:

```ini
# .env file content
TRADE_EXCEL_FILE="C:/Users/YourName/Documents/Finance/MyTrades.xlsx"
TRADE_EXCEL_SHEET="Sheet1"

```

### 2. General Settings (`config.py`)

You can modify `config.py` to customize analysis parameters:

* `METRICS_BENCHMARK`: Ticker used for Alpha/Beta calculations (Default: `"SPY"`).
* `PLOT_BENCHMARK`: List of tickers to plot for comparison (Default: `["SPY", "QQQ", "VEU"]`).
* `NO_DIVIDEND_TAX`: List of tickers exempt from dividend tax adjustments (e.g., `['SHV', 'SGOV']`).

---

## 📊 Input File Format (Excel)

Your Excel file acts as the source of truth. It **must** contain the following columns (headers are case-insensitive).

### **Excel Sample**

| DATE | MARKET | SYMBOL | BUY/SELL | QTY | PRICE | FEE |
| --- | --- | --- | --- | --- | --- | --- |
| 05/01/2025 | US | CASH | Deposit | 1 | 5000 | 0 |
| 15/01/2025 | US | AAPL | Buy | 10 | 145.50 | 2.00 |
| 11/02/2025 | US | MSFT | Buy | 5 | 260.00 | 1.50 |
| 03/08/2025 | US | AAPL | Sell | 5 | 160.00 | 2.00 |
| 12/12/2025 | US | CASH | Withdraw | 1 | 1000 | 0 |


### **Column Definitions**

| Column | Description |
| --- | --- |
| **DATE** | The transaction date (format: `DD/MM/YYYY` or Excel Date format). |
| **MARKET** | The specific market code for the asset (e.g., US).
| **SYMBOL** | Ticker symbol (e.g., `AAPL`, `TSLA`). **Use `CASH` for Deposits/Withdrawals.** |
| **BUY/SELL** | The action taken. Must be one of: `Buy`, `Sell`, `Deposit`, `Withdraw`. |
| **QTY** | Number of shares. (Use `1` for Deposits/Withdrawals if putting full amount in Price). |
| **PRICE** | Price per share. (For Deposits/Withdrawals, this is the total cash amount). |
| **FEE** | (Optional) Brokerage commission or fees paid. Defaults to 0 if left blank. |

> **Note on Cash Flows:** > * **Deposit**: Increases your "Invested Capital".
> * **Withdraw**: Decreases your "Invested Capital".
> * The script calculates the total transaction amount automatically: `(QTY * PRICE)`.
> 
> 

---

## 🛠️ Usage

1. **Install Dependencies:**
```bash
pip install pandas numpy yfinance plotly scipy matplotlib seaborn python-dotenv openpyxl pickle

```

2. **Run the Tracker:**
```bash
python main.py

```


3. **View Output:**
* The script will process your trades, fetch missing market data, and calculate metrics.
* A new report will be generated in the `output/` folder: `portfolio_report_YYYY-MM-DD.html`.
* The report automatically opens in your default web browser.


---

## 📉 Metrics Glossary

The generated report includes the following financial metrics:

* **Sharpe Ratio:** Measure of risk-adjusted return. (Excess return / Volatility).
* **Sortino Ratio:** Similar to Sharpe, but only penalizes *downside* volatility.
* **Alpha:** The excess return of the portfolio relative to the benchmark (`SPY`).
* **Beta:** Volatility relative to the market. (Beta > 1.0 means more volatile than the market).
* **VaR (95%):** Value at Risk. The maximum expected loss in a single day with 95% confidence.
* **Tracking Error:** The standard deviation of the difference between your portfolio returns and the benchmark.
