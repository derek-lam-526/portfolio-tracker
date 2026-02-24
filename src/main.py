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
    
from utils import Timer

def get_trade_history() -> pd.DataFrame:
    data_manager.create_trade_csv()
    trades_df = data_manager.load_trade_history(filepath=config.TRADE_HISTORY_FILE)
    return trades_df

def get_portfolio_history(portfolio_tracker, update=True, show_timing=False, force_update_minute=False) -> pd.DataFrame:
    with Timer(f"Fetching market data{' (no update)' if not update else ''}", enabled=show_timing):
        portfolio_tracker.fetch_market_data(update=update, show_timing=show_timing, force_update_minute=force_update_minute)
    
    with Timer("Processing portfolio history", enabled=show_timing):
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

def run_portfolio_update(update_market_data=True, upload_results=True, show_timing=False, force_update_minute=False):
    start_time = time.perf_counter()
    mode_str = " (TEST MODE)" if not upload_results else ""
    
    print("=" * 50)
    print(f"Updating portfolio performance as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET{mode_str}")
    print("-" * 50)
    
    with Timer("Fetching trade history", enabled=show_timing):
        df_trades = get_trade_history()
    
    # Initialise tracker
    portfolio_tracker = tracker.PortfolioTracker(df_trades)
    
    # Fetch and process history
    df_history = get_portfolio_history(portfolio_tracker, update=update_market_data, show_timing=show_timing, force_update_minute=force_update_minute) 

    # Initialise analyzer
    pa = analyzer.PortfolioAnalyzer(df_history, df_trades, portfolio_tracker)
    
    # Analysis and plots
    with Timer("Calculating performance metrics", enabled=show_timing):
        metrics = pa.calculate_metrics()
        
    with Timer("Generating core plots", enabled=show_timing):
        fig_wealth = pa.get_wealth_plot(show=False)
        fig_drawdown = pa.get_drawdown_plot(show=False)
        fig_returns = pa.get_returns_plot(show=False)
        
    with Timer("Generating quantitative plots", enabled=show_timing):
        fig_quant = pa.get_quant_plots(show=False, windows=config.QUANT_WINDOW)
        
    with Timer("Generating allocation analysis", enabled=show_timing):
        a_data = pa.get_allocation(show=False)
        fig_alloc, df_alloc = a_data['fig'], a_data['df_alloc']
        
    with Timer("Generating distribution and correlation analysis", enabled=show_timing):
        fig_distribution = pa.get_distribution_plot(show=False)
        fig_correlation = pa.get_correlation_heatmap(show=False)
        
    with Timer("Generating beta exposure and factor analysis", enabled=show_timing):
        fig_beta_exp, df_beta = pa.get_beta_exposure_plot(show=False)
        fig_factor, factor_results = pa.get_factor_analysis_plot(show=False)
        
    with Timer("Running Monte Carlo simulation", enabled=show_timing):
        fig_mc, mc_results = stats.get_monte_carlo_plot(pa.history_df['Daily_Return'], n_iterations=10000, show=False)

    # Trade Analysis
    with Timer("Analyzing trades", enabled=show_timing):
        df_completed_trades = trade_analyzer.match_trades(df_trades)
        trade_results = trade_analyzer.calculate_trade_metrics(df_completed_trades)
        fig_trades = trade_analyzer.get_trade_analysis_plots(df_completed_trades)

    # Summary data
    with Timer("Generating summary sheet", enabled=show_timing):
        summary_sheet = pa.get_summary_data(factor_results=factor_results, mc_results=mc_results, trade_results=trade_results)

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

    with Timer("Creating HTML report", enabled=show_timing):
        _, latest_path = create_report(figs, df_alloc, df_trades)
        
    if upload_results:
        with Timer("Uploading to host", enabled=show_timing):
            upload_to_host(latest_path)

    if show_timing:
        total_duration = time.perf_counter() - start_time
        print("-" * 50)
        print(f"✅ Total process completed in {total_duration:.2f}s")
    
    print("=" * 50)
    print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio Tracker Runner")
    parser.add_argument('--test', action='store_true', help='Run in test mode (no upload, show timing)')
    parser.add_argument('--no-update', action='store_true', help='Use cached market data (do not fetch new data)')
    parser.add_argument('--force-minute', action='store_true', help='Force update minute data even if already updated today')
    args = parser.parse_args()

    # Determine update flag
    # If explicitly --no-update, we skip. Otherwise, we update.
    update_data = not args.no_update

    if args.test:
        run_portfolio_update(update_market_data=update_data, upload_results=False, show_timing=True, force_update_minute=args.force_minute)
    else:
        run_portfolio_update(update_market_data=update_data, upload_results=True, show_timing=False, force_update_minute=args.force_minute)
