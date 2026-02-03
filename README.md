# Portfolio Performance Tracker

A comprehensive Python-based tool that tracks investment portfolio performance, calculates risk metrics (Sharpe, Sortino, Alpha, Beta), and generates interactive HTML reports. It uses `yfinance` for market data and supports cash flow management (deposits/withdrawals).

## Features

* **Automated Data Fetching:** Retrieves historical price data using Yahoo Finance.
* **Performance Analysis:** Calculates Daily Returns, Cumulative Returns, and PnL.
* **Risk Metrics:** Computes Sharpe Ratio, Sortino Ratio, Beta (vs SPY), Alpha, and VaR (Value at Risk).
* **Interactive Reporting:** Generates a standalone HTML dashboard with interactive plots (Plotly) and sortable holdings tables.
* **Cash Flow Handling:** Accurately adjusts for Deposits and Withdrawals to calculate Time-Weighted or Money-Weighted returns.

## Project Structure

* `main.py`: Entry point. Orchestrates data fetching, processing, and reporting.
* `portfolio_tracker.py`: Core logic for portfolio state reconstruction (daily holdings/equity).
* `portfolio_analyzer.py`: logic for mathematical/statistical metric calculations.
* `data_manager.py`: Handles Excel ingestion and CSV conversion.
* `report_manager.py`: Compiles figures and stats into the final HTML report.
* `config.py`: Configuration settings and path management.

## Installation

1.  **Clone the repository** (or download source files).
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Environment Setup:**
    Create a `.env` file in the project root directory to point to your Excel trade file:
    ```env
    TRADE_EXCEL_FILE="C:/path/to/your/Financials.xlsx"
    TRADE_EXCEL_SHEET="excel sheet name"
    ```

## Input Data Format (Crucial)

The system ingests trades from an Excel file (specified in your `.env`).

### Columns
The Excel file should have the following headers:
| DATE | MARKET | SYMBOL | BUY/SELL | QTY | PRICE | AMT |
|------|--------|--------|----------|-----|-------|-----|

### Trade Validation ("BUY/SELL" Column)
The **BUY/SELL** column is strictly validated. You must use one of the following four options:

1.  **Buy**: Purchase of an asset.
2.  **Sell**: Sale of an asset.
3.  **Deposit**: Cash addition to the portfolio (increases Invested Capital).
4.  **Withdraw**: Cash removal from the portfolio (decreases Invested Capital).

> **Note:** The `Deposit` and `Withdraw` options are for **CASH** adjustments only. When using these, ensure the `SYMBOL` column is set to a cash placeholder (e.g., `CASH`) if required by your specific logic, though the tracker primarily looks at the monetary value impact.

## Usage

1.  Update your Excel file with your latest trades.
2.  Run the main script:
    ```bash
    python main.py
    ```
3.  **View Report:**
    * The script will generate `trade_history.csv` in the `input/` folder.
    * The final HTML report will be saved to the `output/` folder (e.g., `portfolio_report_2023-10-27.html`).
    * Open the HTML file in any web browser to view your performance dashboard.

## Metrics Explained (in Report)

* **Sharpe Ratio:** Excess return per unit of total risk (volatility).
* **Sortino Ratio:** Excess return per unit of downside risk (harmful volatility).
* **Alpha:** The excess return of the portfolio over the benchmark (SPY) given its risk (Beta).
* **Beta:** The portfolio's volatility relative to the market. A beta of 1.5 means the portfolio is 50% more volatile than the market.
