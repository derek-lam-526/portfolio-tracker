import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.abspath("src"))

import config
import portfolio_tracker as tracker
import portfolio_analyzer as analyzer

def run_verification():
    print("🚀 Starting Multi-Market Verification...")
    
    # 1. Create Mock Trades
    # Scenario: 
    # - Deposit 100,000 HKD
    # - Exchange 78,000 HKD to 10,000 USD (rate 7.8)
    # - Buy 100 shares of 2800.HK (HK market)
    # - Buy 10 shares of SPY (US market)
    
    today = datetime.now()
    t_minus_5 = (today - timedelta(days=5)).date()
    t_minus_4 = (today - timedelta(days=4)).date()
    t_minus_3 = (today - timedelta(days=3)).date()
    t_future = (today + timedelta(days=60)).date()
    
    trades_data = [
        {'DATE': t_minus_5, 'MARKET': 'HK', 'SYMBOL': 'CASH', 'ACTION': 'DEPOSIT', 'QTY': 1, 'PRICE': 100000, 'FEE': 0},
        {'DATE': t_minus_4, 'MARKET': 'HK', 'SYMBOL': 'US', 'ACTION': 'EXCHANGE', 'QTY': 78000, 'PRICE': 10000, 'FEE': 0},
        {'DATE': t_minus_3, 'MARKET': 'HK', 'SYMBOL': '2800.HK', 'ACTION': 'BUY', 'QTY': 100, 'PRICE': 20.0, 'FEE': 50},
        {'DATE': t_minus_3, 'MARKET': 'US', 'SYMBOL': 'SPY', 'ACTION': 'BUY', 'QTY': 10, 'PRICE': 500.0, 'FEE': 5},
        {'DATE': t_future, 'MARKET': 'US', 'SYMBOL': 'CASH', 'ACTION': 'DEPOSIT', 'QTY': 1, 'PRICE': 5000, 'FEE': 0}
    ]
    df_trades = pd.DataFrame(trades_data)
    df_trades['DATE'] = pd.to_datetime(df_trades['DATE'])
    
    print("✅ Created mock trades.")
    
    # 2. Initialize Tracker
    pt = tracker.PortfolioTracker(df_trades)
    
    # 3. Fetch Data (with update=True to get FX and HK ticker)
    # Note: This will actually attempt to download data from Yahoo Finance
    print("📥 Fetching market data (including FX and HK)...")
    pt.fetch_market_data(update=True, show_timing=True)
    
    # 4. Process Portfolio
    print("⚙️ Processing portfolio...")
    df_history = pt.process_portfolio()
    
    # 5. Verify Results
    last_row = df_history.iloc[-1]
    print("\n--- Portfolio Summary (Normalized to USD) ---")
    print(f"Total Equity:  ${last_row['Total_Equity']:,.2f}")
    print(f"Invested Cap:  ${last_row['Invested_Capital']:,.2f}")
    print(f"Cash Bucket:   ${last_row['Cash']:,.2f}")
    print(f"Market Value:  ${last_row['Market_Value']:,.2f}")
    
    # Basic Checks
    # 100,000 HKD original deposit should be ~12,820 USD
    expected_cap = 100000 / 7.8 # Roughly
    if abs(last_row['Invested_Capital'] - expected_cap) < 500:
        print("\n✅ Invested Capital (Normalized) looks correct.")
    else:
        print(f"\n⚠️ Invested Capital might be off: Expected ~{expected_cap:.2f}, got {last_row['Invested_Capital']:.2f}")

    # Check if HK ticker is in market data
    if '2800.HK' in pt.market_data:
        print("✅ HK Ticker (2800.HK) successfully fetched.")
    else:
        print("❌ HK Ticker (2800.HK) missing from market data.")

    # Check for FX pairs
    if 'HKDUSD=X' in pt.market_data:
         print("✅ FX pair (HKDUSD=X) successfully fetched.")
    else:
         print("❌ FX pair (HKDUSD=X) missing.")

    print("\n🚀 Verification Complete.")

if __name__ == "__main__":
    run_verification()
