# Portfolio Performance Tracker

A comprehensive, Python-based investment portfolio tracker that automates data fetching, calculates professional-grade risk metrics, and generates an interactive HTML dashboard. 

Built with **Pandas**, **yfinance**, and **Plotly**, this tool reconstructs your portfolio's daily history from a simple list of trades to provide deep insights into your investing performance.

## 🚀 Key Features

* **Vectorized Performance Engine**: Optimized with NumPy and Pandas vectorization to calculate 1500+ days of portfolio history and complex risk metrics in milliseconds.
* **Automated Data Engine**: Fetches historical price data (Daily & Minute resolution) using `yfinance`.
* **Smart Caching & Optimization**:
    * Caches market data and metadata locally (`data/portfolio_metadata.pkl`) to minimize API requests.
    * **Fama-French Factor Caching**: Local storage of risk factors to speed up quantitative analysis.
    * **Minute Data Throttling**: Automatically limits minute-data updates to once per day to ensure stability.
* **Scalable Asset Categorization**: Uses a dynamic mapping system (`mappings.py`) to classify holdings into groups like **Technology**, **Consumer Staples**, and **International Broad Market** based on asset metadata.
* **Advanced Risk Analysis**:
    * **Performance**: Cumulative Returns, Daily PnL, Drawdowns.
    * **Metrics**: Sharpe Ratio, Sortino Ratio, Alpha, Beta (vs Benchmark), Value at Risk (VaR 95%).
    * **Exposure**: Side-by-side comparison of nominal allocation vs. beta-adjusted exposure.
* **Interactive Dashboard**: 
    * Generates a standalone HTML file with zoomable Plotly charts.
    * Includes a **searchable, sortable Holdings Table** using DataTables.
    * Visualizes Monthly Returns with a heatmap.
* **Cash Flow Management**: Accurately handles Deposits and Withdrawals to track Invested Capital vs. Market Value.

---

## 📂 Project Structure

* `main.py`: Entry point. Orchestrates the workflow and handles CLI arguments.
* `portfolio_tracker.py`: Core engine. Vectorized reconstruction of portfolio state, handles dividends/splits, and data caching.
* `portfolio_analyzer.py`: Statistical engine. Calculates core financial metrics (Alpha, Beta, etc.) and prepares plot data.
* `portfolio_stats.py`: Statistics and simulation engine. Runs Monte Carlo bootstrap simulations and permutation tests for Sharpe ratio significance.
* `trade_analyzer.py`: Trade matching and analysis. Implements FIFO logic to calculate realized PnL and trade-level performance metrics.
* `report_manager.py`: Report generator. Renders the interactive HTML dashboard using Jinja2 templates.
* `templates/`: Contains HTML/CSS templates used by `report_manager.py` for report generation.
* `data_manager.py`: Data I/O utilities. Handles Excel-to-CSV conversion and loading of trade history.
* `mappings.py`: Centralized home for asset classification rules and ticker overrides.
* `utils.py`: Shared utilities including performance timing and thread-safe collectors.
* `config.py`: Central configuration. Manages file paths, benchmarks, and tax settings.

---

## ⚙️ Configuration & Setup

This project uses `python-dotenv` to manage sensitive paths and configuration separate from the code.

### 1. Environment Variables (`.env`)
Create a file named `.env` in the root directory:
```ini
TRADE_EXCEL_FILE="C:/Users/YourName/Documents/Finance/MyTrades.xlsx"
TRADE_EXCEL_SHEET="Sheet1"

# (Optional) Remote Upload Settings
HOST="your.host.server"
HOST_USER="your_username"
SUBPAGE="sub-directory"
```

### 2. General Settings (`config.py`)
* `METRICS_BENCHMARK`: Ticker for Alpha/Beta calculations (Default: `"SPY"`).
* `PLOT_BENCHMARK`: Benchmarks to plot for comparison (Default: `["SPY", "QQQ", "VEU"]`).
* `NO_DIVIDEND_TAX`: Tickers exempt from dividend tax adjustments.

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
| **DATE** | Transaction date (format: `DD/MM/YYYY` or Excel Date format). |
| **MARKET** | Specific market code for the asset (e.g., US). |
| **SYMBOL** | Ticker symbol. Use **CASH** for Deposits/Withdrawals. |
| **BUY/SELL** | Action taken: `Buy`, `Sell`, `Deposit`, `Withdraw`. |
| **QTY** | Number of shares. |
| **PRICE** | Price per share (or total amount for Cash actions). |
| **FEE** | (Optional) Transaction fees. |

---

## 🛠️ Usage

1. **Install Dependencies:**
```bash
pip install pandas numpy yfinance plotly scipy matplotlib seaborn python-dotenv openpyxl paramiko
```

2. **Run the Tracker:**
```bash
# Standard run (updates data and generates report)
python src/main.py

# Test mode (local data only, granular timing enabled)
python src/main.py --test --no-update
```

### **Advanced CLI Options**
* `--test`: Enables granular timing instrumentation and skips remote uploads.
* `--no-update`: Uses cached local data instead of fetching fresh market prices.
* `--force-minute`: Overrides the daily limit for minute-data downloads.

---

## 📉 Metrics Glossary

* **Sharpe Ratio:** Risk-adjusted return (Excess return / Volatility).
* **Sortino Ratio:** Sharp ratio variant that only penalizes *downside* volatility.
* **Alpha:** Excess return relative to the benchmark.
* **Beta:** Sensitivity to market movements (Beta 1.0 = same as market).
* **VaR (95%):** Maximum expected loss in one day with 95% confidence.
