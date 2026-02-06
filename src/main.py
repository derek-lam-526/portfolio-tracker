import time
import os
import pandas as pd
import webbrowser
import argparse

import config 
import data_manager
import portfolio_tracker as tracker
import portfolio_analyzer as analyzer
import report_manager

pd.set_option('display.max_rows', 100)
pd.set_option('display.float_format', '{:.2f}'.format)

os.environ['TZ'] = 'America/New_York'
try:
    time.tzset()
except AttributeError:
    pass
    
def get_trade_history() -> pd.DataFrame:
    data_manager.create_trade_csv()
    trades_df = data_manager.load_trade_history(filepath=config.TRADE_HISTORY_FILE)
    return trades_df

def get_portfolio_history(portfolio_tracker, update=True) -> pd.DataFrame:
    portfolio_tracker.fetch_market_data(update=update)
    history_df = portfolio_tracker.process_portfolio()
    return history_df

def create_report(figs, df_alloc, df_trades):
    report_path = report_manager.create_report(figs, df_alloc, df_trades)
    print(f"✅ Report saved to: {report_path}")
    is_open = webbrowser.open(report_path.as_uri())
    if is_open:
        print(f"✅ Opened report in browser")
    else:
        print(f"❌ Could not open browser automatically. Please open the file manually.")

def main():
    # Get trades from excel trade history
    df_trades = get_trade_history()
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(df_trades)
    df_history = get_portfolio_history(portfolio_tracker, update=True) 

    # Analysis and plots
    metrics = analyzer.calculate_performance_metrics(df_history)
    fig_wealth = analyzer.get_wealth_plot(df_history, show = False)
    fig_drawdown = analyzer.get_drawdown_plot(df_history, show=False)
    fig_returns = analyzer.get_returns_plot(df_history, show=False)
    fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings = analyzer.get_allocation(df_history, df_trades, portfolio_tracker, show=False)

    # Summary sheet 
    summary_sheet = analyzer.get_summary_sheet(df_history, category_values, sector_values, current_values, current_holdings)

    figs = {
        "wealth": fig_wealth,
        "drawdown": fig_drawdown,
        "returns": fig_returns,
        "alloc": fig_alloc,
        "summary": summary_sheet
    }

    create_report(figs, df_alloc, df_trades)

def test():
    df_trades = get_trade_history()

    # print(df_trades.tail())
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(df_trades)
    df_history = get_portfolio_history(portfolio_tracker, update=False) # Use cached data

    # Analysis and plots
    metrics = analyzer.calculate_performance_metrics(df_history)
    fig_wealth = analyzer.get_wealth_plot(df_history, show = False)
    fig_drawdown = analyzer.get_drawdown_plot(df_history, show=False)
    fig_returns = analyzer.get_returns_plot(df_history, show=False)
    fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings = analyzer.get_allocation(df_history, df_trades, portfolio_tracker, show=False)

    # print(df_alloc)

    # Summary sheet 
    summary_sheet = analyzer.get_summary_sheet(df_history, category_values, sector_values, current_values, current_holdings)

    figs = {
        "wealth": fig_wealth,
        "drawdown": fig_drawdown,
        "returns": fig_returns,
        "alloc": fig_alloc,
        "summary": summary_sheet
    }

    create_report(figs, df_alloc, df_trades)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio Tracker Runner")
    parser.add_argument('--test', action='store_true', help='Run in test mode (no data update)')
    args = parser.parse_args()

    if args.test:
        test()
    else:
        main()
