import time
from datetime import datetime
import os
import shutil
import pandas as pd
import webbrowser
import argparse
import paramiko

import urllib.request

import config 
import data_manager
import portfolio_tracker as tracker
import portfolio_analyzer as analyzer
import portfolio_stats as stats
import trade_analyzer
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

def create_report(figs, df_alloc, df_trades, open_report = False):
    report_path = report_manager.create_report(figs, df_alloc, df_trades)
    latest_path = os.path.join(config.OUTPUT_DIR, "portfolio_report_latest.html")
    print(f"✅ Saved report to: {report_path}")
    print(f"✅ Updated main report: {latest_path}")
    shutil.copy(report_path, latest_path)
    if open_report:
        is_open = webbrowser.open(report_path.as_uri())
        if is_open:
            print(f"✅ Opened report in browser")
        else:
            print(f"❌ Could not open browser automatically. Please open the file manually.")
    return report_path, latest_path

def upload_to_host(file_path):
    print("📤 Starting upload to host...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    private_key_path = os.path.expanduser("~/.ssh/id_ed25519")
    
    try:
        ssh.connect(
            hostname=config.HOST, 
            username=config.USER,
            key_filename=private_key_path,
            look_for_keys=True,
            timeout=10
        )

        sftp = ssh.open_sftp()
        sftp.put(file_path, config.REMOTE_REPORT_PATH)

        sftp.close()
        ssh.close()
        print("✅ Success! Portfolio updated on host.")
    
    except Exception as e:
        print(f"❌ SRCF Upload failed: {str(e)}")

def main():
    print("=" * 50)
    print(f"Updating portfolio performance as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET")
    print("-" * 50)
    df_trades = get_trade_history()
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(df_trades)
    df_history = get_portfolio_history(portfolio_tracker, update=True) 

    # Analysis and plots
    metrics = analyzer.calculate_performance_metrics(df_history)
    fig_wealth = analyzer.get_wealth_plot(df_history, show = False)
    fig_drawdown = analyzer.get_drawdown_plot(df_history, show=False)
    fig_returns = analyzer.get_returns_plot(df_history, show=False)
    fig_quant = analyzer.get_quant_plots(df_history, show=False, windows=config.QUANT_WINDOW)
    fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings = analyzer.get_allocation(df_history, df_trades, portfolio_tracker, show=False)
    fig_distribution = analyzer.get_distribution_plot(df_history, show=False)
    fig_correlation = analyzer.get_correlation_heatmap(portfolio_tracker, current_holdings, show=False)
    fig_beta_exp, df_beta = analyzer.get_beta_exposure_plot(portfolio_tracker, current_holdings, current_values, show=False)
    fig_factor, factor_results = analyzer.get_factor_analysis_plot(df_history, show=False)
    fig_mc, mc_results = stats.get_monte_carlo_plot(df_history['Daily_Return'], n_iterations=10000, show=False)
    
    # Trade Analysis
    df_completed_trades = trade_analyzer.match_trades(df_trades)
    trade_results = trade_analyzer.calculate_trade_metrics(df_completed_trades)
    fig_trades = trade_analyzer.get_trade_analysis_plots(df_completed_trades)

    # Summary sheet 
    summary_sheet = analyzer.get_summary_sheet(df_history, category_values, sector_values, current_values, current_holdings, 
                                              factor_results=factor_results, mc_results=mc_results, trade_results=trade_results)

    figs = {
        "wealth": fig_wealth,
        "drawdown": fig_drawdown,
        "returns": fig_returns,
        "alloc": fig_alloc,
        "quant": fig_quant,
        "distribution": fig_distribution,
        "correlation": fig_correlation,
        "beta_exposure": fig_beta_exp,
        "factor_analysis": fig_factor,
        "monte_carlo": fig_mc,
        "trade_analysis": fig_trades,
        "summary": summary_sheet
    }

    _, latest_path = create_report(figs, df_alloc, df_trades)
    upload_to_host(latest_path)

    print("\n")

def test():
    print("=" * 50)
    print(f"Updating portfolio performance as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET")
    print("-" * 50)
    df_trades = get_trade_history()
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(df_trades)
    df_history = get_portfolio_history(portfolio_tracker, update=False) 

    # Analysis and plots
    metrics = analyzer.calculate_performance_metrics(df_history)
    fig_wealth = analyzer.get_wealth_plot(df_history, show = False)
    fig_drawdown = analyzer.get_drawdown_plot(df_history, show=False)
    fig_returns = analyzer.get_returns_plot(df_history, show=False)
    fig_quant = analyzer.get_quant_plots(df_history, show=False, windows=config.QUANT_WINDOW)
    fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings = analyzer.get_allocation(df_history, df_trades, portfolio_tracker, show=False)
    fig_distribution = analyzer.get_distribution_plot(df_history, show=False)
    fig_correlation = analyzer.get_correlation_heatmap(portfolio_tracker, current_holdings, show=False)
    fig_beta_exp, df_beta = analyzer.get_beta_exposure_plot(portfolio_tracker, current_holdings, current_values, show=False)
    fig_factor, factor_results = analyzer.get_factor_analysis_plot(df_history, show=False)
    fig_mc, mc_results = stats.get_monte_carlo_plot(df_history['Daily_Return'], n_iterations=10000, show=False)

    # Trade Analysis
    df_completed_trades = trade_analyzer.match_trades(df_trades)
    trade_results = trade_analyzer.calculate_trade_metrics(df_completed_trades)
    fig_trades = trade_analyzer.get_trade_analysis_plots(df_completed_trades)

    # Summary sheet 
    summary_sheet = analyzer.get_summary_sheet(df_history, category_values, sector_values, current_values, current_holdings, 
                                              factor_results=factor_results, mc_results=mc_results, trade_results=trade_results)

    figs = {
        "wealth": fig_wealth,
        "drawdown": fig_drawdown,
        "returns": fig_returns,
        "alloc": fig_alloc,
        "quant": fig_quant,
        "distribution": fig_distribution,
        "correlation": fig_correlation,
        "beta_exposure": fig_beta_exp,
        "factor_analysis": fig_factor,
        "monte_carlo": fig_mc,
        "trade_analysis": fig_trades,
        "summary": summary_sheet
    }

    _, latest_path = create_report(figs, df_alloc, df_trades)

    print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio Tracker Runner")
    parser.add_argument('--test', action='store_true', help='Run in test mode (no data update)')
    args = parser.parse_args()

    if args.test:
        test()
    else:
        main()
