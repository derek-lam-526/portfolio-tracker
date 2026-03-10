# 📈 Portfolio Performance Tracker

A professional-grade, automated investment tracker that transforms your trade history into a deep-dive performance dashboard. 

This tool is designed for investors who trade across multiple markets (US, HK, etc.) and want a clear, unified view of their returns, risk metrics, and asset allocation—all converted into a single base currency of their choice.

---

## 🌟 What This Project Does
1.  **Reconstructs History**: Takes your list of buys, sells, and deposits to build a day-by-day history of your portfolio's value.
2.  **Multi-Currency Handling**: Automatically handles different currencies (USD, HKD, GBP, JPY). It fetches historical FX rates to show everything in your local currency.
3.  **Professional Metrics**: Calculates Sharpe Ratio, Alpha/Beta (vs S&P 500 or HSI), Drawdowns, and Value at Risk (VaR).
4.  **Interactive Dashboard**: Generates an HTML report with zoomable charts and searchable tables.

---

## 🛠️ Setup Guide (For New Users)

### 1. Install Python & Dependencies
Ensure you have Python installed, then run this command in your terminal to install the necessary libraries:

```bash
pip install pandas numpy yfinance plotly scipy matplotlib seaborn python-dotenv openpyxl paramiko
```

### 2. Configure Your Settings
Create a file named `.env` in the project root and add the path to your Excel file:

```ini
TRADE_EXCEL_FILE="C:/Users/Name/Documents/MyTrades.xlsx"
TRADE_EXCEL_SHEET="Sheet1"
```

In `src/config.py`, check these two important settings:
*   `BASE_CURRENCY`: The currency you want your entire report to be displayed in (e.g., `'HKD'`).
*   `SECONDARY_CURRENCY`: An optional second currency to display in grey for quick reference (e.g., `'USD'`).

---

## 📊 How to Prepare Your Excel Input
The Excel file is the "brain" of the tracker. It must have these **7 columns** (exact names matter):

| DATE | MARKET | SYMBOL | BUY/SELL | QTY | PRICE | FEE |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01/01/2024 | US | CASH | DEPOSIT | 1 | 10000 | 0 |
| 05/01/2024 | US | NVDA | BUY | 10 | 480.50 | 1.50 |
| 10/02/2024 | HK | 2800.HK | BUY | 500 | 20.30 | 18.00 |
| 15/03/2024 | HK | US | EXCHANGE | 7800 | 1000 | 0 |

### **Action Types (BUY/SELL Column)**

| Action | When to use it? | Column Details |
| :--- | :--- | :--- |
| **DEPOSIT** | When you add cash to your brokerage. | `SYMBOL`="CASH", `PRICE`=Amount added. |
| **WITHDRAW** | When you take cash out. | `SYMBOL`="CASH", `PRICE`=Amount removed. |
| **BUY** | When you buy a stock or ETF. | `QTY`=Shares, `PRICE`=Price per share. |
| **SELL** | When you sell a stock or ETF. | `QTY`=Shares, `PRICE`=Price per share. |
| **EXCHANGE**| Moving funds between currencies. | See "The Exchange Rule" below. |

### **The "EXCHANGE" Rule**
If you exchange HKD to USD to buy US stocks, record it like this:
*   **MARKET**: The source market (e.g., `HK`).
*   **SYMBOL**: The destination market (e.g., `US`).
*   **BUY/SELL**: `EXCHANGE`.
*   **QTY**: The amount of **source** currency leaving (e.g., 7800 HKD).
*   **PRICE**: The amount of **destination** currency entering (e.g., 1000 USD).

---

## 🚀 Running the Tracker

1.  **Run the update**:
    ```bash
    python src/main.py
    ```
2.  **Check the output**:
    The report will be saved in the `output/` folder as `portfolio_report_latest.html`. Simply double-click it to open it in your browser.

---

## 📂 Troubleshooting & Tips
*   **Ticker Suffixes**: For Hong Kong stocks, always add `.HK` (e.g., `0700.HK`). For US, just the ticker (e.g., `AAPL`).
*   **Market Registry**: If you trade in London (`L`) or Japan (`J`), ensure they are defined in `src/config.py` with their respective currencies.
*   **Missing Data**: If a chart looks empty, check that your `DATE` column is formatted correctly in Excel (as a Date, not Text).

---

## 📉 Financial Glossary for the Report
*   **Sharpe Ratio**: Measures if your returns are worth the risk. >1.0 is good, >2.0 is great.
*   **Alpha**: How much you beat the market benchmark (e.g., S&P 500).
*   **Beta**: Your portfolio's sensitivity. Beta 1.2 means if the market goes up 10%, you likely go up 12%.
*   **Max Drawdown**: The biggest "peak-to-trough" drop your portfolio has experienced.
