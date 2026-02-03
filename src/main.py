import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, date
import time
from zoneinfo import ZoneInfo
from IPython.display import display, HTML
import os
import concurrent.futures
import warnings

import config 
import data_manager
import portfolio_tracker as tracker
import portfolio_analyzer as analyzer
import report_manager

pd.set_option('display.max_rows', 100)
pd.set_option('display.float_format', '{:.2f}'.format)

os.environ['TZ'] = 'America/New_York'
time.tzset()
    
def get_trade_history() -> pd.DataFrame:
    data_manager.create_trade_csv()
    trades_df = data_manager.load_trade_history(filepath=config.TRADE_HISTORY_FILE)
    return trades_df

def get_portfolio_history(portfolio_tracker) -> pd.DataFrame:
    portfolio_tracker.fetch_market_data()
    history_df = portfolio_tracker.process_portfolio()
    return history_df

def main():
    # Get trades from excel trade history
    trades_df = get_trade_history()
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(trades_df)
    history_df = get_portfolio_history(portfolio_tracker)

    # Analysis and plots
    metrics = analyzer.calculate_performance_metrics(history_df)
    fig_pnl = analyzer.get_pnl_plot(history_df, show = False)
    fig_return = analyzer.get_returns_plot(history_df, show=False)
    fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings = analyzer.get_allocation(history_df, trades_df, portfolio_tracker, show=False)

    # Summary sheet 
    summary_sheet = analyzer.get_summary_sheet(history_df, category_values, sector_values, current_values, current_holdings)

    # Create report
    report_path = report_manager.create_report(fig_pnl, fig_return, fig_alloc, summary_sheet, df_alloc)
    print(f"✅ Report saved to: {report_path}")
    
if __name__ == "__main__":
    main()
