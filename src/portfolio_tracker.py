import config
import os 
import pandas as pd 
import numpy as np 
import yfinance as yf 
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import concurrent.futures
import pickle
import time
from utils import TimingCollector

class PortfolioTracker:
    def __init__(self, trades_df):
        self.trades = trades_df.copy()
        # Symbols are now identified by any ticker that is actually bought or sold as an asset
        asset_trades = self.trades[self.trades['BUY/SELL'].isin(['BUY', 'SELL'])]
        self.symbols = asset_trades['SYMBOL'].unique().tolist()
        self.market_data = {}
        self.dividends = {}
        self.splits = {}
        self.asset_info = {}
        self.start_date = self.trades['DATE'].min()
        self.end_date = datetime.now()
        self.dividend_history = []
        
    def fetch_market_data(self, update=True, show_timing=False, force_update_minute=False):
        
        collector = TimingCollector(enabled=show_timing)
        metadata_path = os.path.join(config.DATA_DIR, "portfolio_metadata.pkl")
        
        if not update:
            print("⚠️  Update=False: Loading data from local cache...")

            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'rb') as f:
                        meta = pickle.load(f)
                        self.dividends = meta.get("dividends", {})
                        self.splits = meta.get("splits", {})
                        self.asset_info = meta.get("asset_info", {})
                except Exception as e:
                    print(f"Error loading metadata: {e}")
            else:
                print(f"No metadata cache found.")

            for symbol in self.symbols:
                file_name = f"{symbol}.csv"
                daily_path = os.path.join(config.DAILY_DATA_DIR, file_name)
                if os.path.exists(daily_path):
                    df = pd.read_csv(daily_path, index_col=0)
                    df.index = pd.to_datetime(df.index, errors='coerce')
                    self.market_data[symbol] = df[df.index.notna()].sort_index()
                else:
                    print(f"Warning: No local data for {symbol}")
            return 
            
        print(f"Processing data for: {self.symbols}")

        def process_symbol(symbol):
            try:
                ticker = yf.Ticker(symbol)
                start_str = (self.start_date - timedelta(days=5)).strftime('%Y-%m-%d')
                
                # --- DAILY DATA DOWNLOAD ---
                file_name = f'{symbol}.csv'
                daily_path = os.path.join(config.DAILY_DATA_DIR, file_name)
                existing_data = pd.DataFrame()
                
                if os.path.exists(daily_path):
                    try:
                        df = pd.read_csv(daily_path, index_col=0)
                        df.index = pd.to_datetime(df.index, errors='coerce')
                        existing_data = df[df.index.notna()].sort_index()
                    except Exception: pass
                
                t_start_hist = time.perf_counter()
                new_hist = ticker.history(start=start_str, auto_adjust=False)
                collector.record("Daily Data Download", time.perf_counter() - t_start_hist)
                
                # --- DAILY DATA PROCESSING/APPEND ---
                t_start_proc = time.perf_counter()
                if not new_hist.empty:
                    new_hist.index = new_hist.index.tz_localize(None)
                    if not existing_data.empty:
                        combined = pd.concat([existing_data, new_hist])
                        combined = combined[~combined.index.duplicated(keep='last')]
                        combined.sort_index(inplace=True)
                        hist = combined
                    else:
                        hist = new_hist
                    hist.to_csv(daily_path)
                    self.market_data[symbol] = hist
                elif not existing_data.empty:
                    self.market_data[symbol] = existing_data
                else:
                    self.market_data[symbol] = pd.DataFrame()
                collector.record("Daily Data Processing & Save", time.perf_counter() - t_start_proc)

                # --- METADATA RETRIEVAL (DIVIDENDS, SPLITS, INFO) ---
                t_start_meta = time.perf_counter()
                divs = ticker.dividends
                splits = ticker.splits
                self.dividends[symbol] = divs.tz_localize(None) if divs.index.tz is not None else divs
                self.splits[symbol] = splits.tz_localize(None) if splits.index.tz is not None else splits
                
                try:
                    self.asset_info[symbol] = ticker.info
                except Exception:
                    self.asset_info[symbol] = {}
                collector.record("Metadata Retrieval (Divs/Splits/Info)", time.perf_counter() - t_start_meta)

                # --- MINUTE DATA ---
                t_start_min = time.perf_counter()
                minute_path = os.path.join(config.MINUTE_DATA_DIR, file_name)
                
                should_update_minute = True
                if os.path.exists(minute_path) and not force_update_minute:
                    mtime = datetime.fromtimestamp(os.path.getmtime(minute_path))
                    if mtime.date() == datetime.now().date():
                        should_update_minute = False

                if should_update_minute:
                    existing_min = pd.DataFrame()
                    if os.path.exists(minute_path):
                        try:
                            df = pd.read_csv(minute_path, index_col=0)
                            df.index = pd.to_datetime(df.index, errors='coerce')
                            existing_min = df[df.index.notna()].sort_index()
                        except: pass
                    
                    new_min = ticker.history(period='7d', interval='1m', auto_adjust=False)
                    if not new_min.empty:
                        new_min.index = new_min.index.tz_localize(None)
                        if not existing_min.empty:
                            combined_min = pd.concat([existing_min, new_min])
                            combined_min = combined_min[~combined_min.index.duplicated(keep='last')]
                            combined_min.sort_index(inplace=True)
                            combined_min.to_csv(minute_path)
                        else:
                            new_min.to_csv(minute_path)
                
                collector.record("Minute Data Download & Save", time.perf_counter() - t_start_min)

            except Exception as e:
                print(f"Error processing {symbol}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            executor.map(process_symbol, self.symbols)

        # --- Save metadata to cache --- 
        try: 
            with open(metadata_path, "wb") as f:
                pickle.dump({
                    "dividends": self.dividends,
                    "splits": self.splits,
                    "asset_info": self.asset_info
                }, f)
            print("✅ Market data and metadata updated successfully.")
            collector.print_summary()
        except Exception as e:
            print(f"Error saving metadata: {e}")
            
    def process_portfolio(self):
        # 1. Setup Time Index
        date_range = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        full_idx = date_range

        # 2. Pre-process Trades
        trades = self.trades.copy()
        trades['DATE'] = pd.to_datetime(trades['DATE'])
        
        # Sign QTY and Cash Flows based on BUY/SELL
        # In iterative logic:
        # BUY:  holdings[symbol] += qty, cash -= (amt + fee)
        # SELL: holdings[symbol] -= qty, cash += (amt - fee)
        trades['SIGNED_QTY'] = 0.0
        trades['NET_ASSET_CASH'] = 0.0
        
        buy_mask = trades['BUY/SELL'] == 'BUY'
        sell_mask = trades['BUY/SELL'] == 'SELL'
        
        trades.loc[buy_mask, 'SIGNED_QTY'] = trades['QTY']
        trades.loc[buy_mask, 'NET_ASSET_CASH'] = -(trades['AMT'] + trades['FEE'])
        
        trades.loc[sell_mask, 'SIGNED_QTY'] = -trades['QTY']
        trades.loc[sell_mask, 'NET_ASSET_CASH'] = +(trades['AMT'] - trades['FEE'])

        # 3. Align Market Data, Splits, and Dividends
        price_df = pd.DataFrame(1.0, index=full_idx, columns=self.symbols)
        split_df = pd.DataFrame(1.0, index=full_idx, columns=self.symbols)
        div_df = pd.DataFrame(0.0, index=full_idx, columns=self.symbols)

        for sym in self.symbols:
            # Prices
            if sym in self.market_data and not self.market_data[sym].empty:
                df = self.market_data[sym]
                # Pad to fill non-trading days
                price_df[sym] = df['Close'].reindex(full_idx, method='pad').fillna(0)
            else:
                price_df[sym] = 0.0

            # Splits
            # In iterative: holdings[symbol] *= split_ratio on the day of the split
            if sym in self.splits and not self.splits[sym].empty:
                split_df[sym] = self.splits[sym].reindex(full_idx, fill_value=1.0)

            # Dividends (Net of Tax)
            if sym in self.dividends and not self.dividends[sym].empty:
                is_treasury = sym in config.NO_DIVIDEND_TAX
                tax_rate = 0.0 if is_treasury else 0.30
                net_div = self.dividends[sym] * (1 - tax_rate)
                div_df[sym] = net_div.reindex(full_idx, fill_value=0.0)

        # 4. Vectorized Holdings Calculation (Split-Adjusted)
        cum_split = split_df.cumprod()
        prev_cum_split = cum_split.shift(1, fill_value=1.0)
        
        asset_mask = trades['BUY/SELL'].isin(['BUY', 'SELL'])
        trade_qties = trades[asset_mask].groupby(['DATE', 'SYMBOL'])['SIGNED_QTY'].sum().unstack().reindex(full_idx).fillna(0)
        
        for sym in self.symbols:
            if sym not in trade_qties.columns:
                trade_qties[sym] = 0.0
        trade_qties = trade_qties[self.symbols]

        adj_qty = trade_qties / prev_cum_split
        holdings_df = adj_qty.cumsum() * cum_split
        
        # 5. Market Value
        market_value_df = holdings_df * price_df
        daily_market_value = market_value_df.sum(axis=1)

        # 6. Cash Flow and Dividend History
        daily_div_income = (holdings_df * div_df).sum(axis=1)
        
        # Record Dividend History
        div_hits = (holdings_df * div_df)
        div_mask = div_hits > 1e-6 # Avoid precision noise
        for date in div_mask.index[div_mask.any(axis=1)]:
            for sym in div_mask.columns[div_mask.loc[date]]:
                self.dividend_history.append({
                    'Date': date, 'Symbol': sym, 'Amount': div_hits.loc[date, sym]
                })

        # Asset Trade Cash Flows
        daily_asset_cash_flow = trades[asset_mask].groupby('DATE')['NET_ASSET_CASH'].sum().reindex(full_idx).fillna(0)
        
        # Cash Trades (Deposits/Withdrawals)
        cash_mask = trades['BUY/SELL'].isin(['DEPOSIT', 'WITHDRAW'])
        cash_trades = trades[cash_mask].copy()
        cash_trades['FLOW'] = 0.0
        cash_trades['CAPITAL_CHANGE'] = 0.0
        
        dep_mask = cash_trades['BUY/SELL'] == 'DEPOSIT'
        wit_mask = cash_trades['BUY/SELL'] == 'WITHDRAW'
        
        cash_trades.loc[dep_mask, 'FLOW'] = cash_trades['AMT'] - cash_trades['FEE']
        cash_trades.loc[dep_mask, 'CAPITAL_CHANGE'] = cash_trades['AMT']
        
        # Withdraw iterative: cash -= (amt + fee), invested -= amt
        cash_trades.loc[wit_mask, 'FLOW'] = -(cash_trades['AMT'] + cash_trades['FEE'])
        cash_trades.loc[wit_mask, 'CAPITAL_CHANGE'] = -cash_trades['AMT']
        
        daily_cash_trades_flow = cash_trades.groupby('DATE')['FLOW'].sum().reindex(full_idx).fillna(0)
        daily_capital_change = cash_trades.groupby('DATE')['CAPITAL_CHANGE'].sum().reindex(full_idx).fillna(0)
        
        total_cash_change = daily_asset_cash_flow + daily_cash_trades_flow + daily_div_income
        cash_series = total_cash_change.cumsum()
        invested_capital_series = daily_capital_change.cumsum()
        
        # 7. Final Assembly
        total_equity = daily_market_value + cash_series
        
        self.df_portfolio = pd.DataFrame({
            'Cash': cash_series,
            'Market_Value': daily_market_value,
            'Total_Equity': total_equity,
            'Invested_Capital': invested_capital_series,
            'Net_Flow': daily_capital_change
        }, index=full_idx)
        
        # Business days filter
        self.df_portfolio = self.df_portfolio[self.df_portfolio.index.dayofweek < 5]
        
        # Weights
        weight_df = market_value_df.divide(total_equity, axis=0).fillna(0)
        self.historical_weights = weight_df[weight_df.index.dayofweek < 5]
        
        return self.df_portfolio

    def calculate_correlation_matrix(self, period='3mo', holdings = True):
        """
        Calculate and plot correlation matrix for portfolio holdings
        period: '1mo', '3mo', '6mo', '1y', 'max'
        """
        last_holdings = {}
        for sym in self.symbols:
            buys = self.trades[(self.trades['SYMBOL'] == sym) & (self.trades['BUY/SELL'] == 'BUY')]['QTY'].sum()
            sells = self.trades[(self.trades['SYMBOL'] == sym) & (self.trades['BUY/SELL'] == 'SELL')]['QTY'].sum()
            last_holdings[sym] = buys - sells

        current_holdings = [k for k, v in last_holdings.items() if v > 0]

        if holdings:
            sym_list = current_holdings
        else:
            sym_list = self.symbols

        returns_data = {}
        
        for symbol in sym_list:
            if symbol in self.market_data and not self.market_data[symbol].empty:
                try:
                    # Get closing prices
                    prices = self.market_data[symbol]['Close']
                    
                    # Handle different periods
                    if period != 'max':
                        if period == '1mo':
                            cutoff_date = prices.index[-1] - pd.DateOffset(months=1)
                        elif period == '3mo':
                            cutoff_date = prices.index[-1] - pd.DateOffset(months=3)
                        elif period == '6mo':
                            cutoff_date = prices.index[-1] - pd.DateOffset(months=6)
                        elif period == '1y':
                            cutoff_date = prices.index[-1] - pd.DateOffset(years=1)
                        
                        prices = prices.loc[prices.index >= cutoff_date]
                    
                    # Calculate daily returns
                    returns = prices.pct_change().dropna()
                    if len(returns) > 10: 
                        returns_data[symbol] = returns
                        
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
        
        if not returns_data:
            print("No valid returns data found")
            return None
        
        # Create returns DataFrame and align dates
        returns_df = pd.DataFrame(returns_data)
        returns_df = returns_df.dropna()
        
        if returns_df.empty:
            print("No common dates found after alignment")
            return None
        
        # Calculate correlation matrix
        correlation_matrix = returns_df.corr()
        
        # Plot correlation matrix
        plt.figure(figsize=(10, 8))
        mask = np.triu(np.ones_like(correlation_matrix, dtype=bool))
        sns.heatmap(correlation_matrix, 
                   annot=True, 
                   cmap='RdYlBu_r', 
                   center=0,
                   square=True,
                   mask=mask,
                   fmt='.2f',
                   cbar_kws={'shrink': 0.6})
        
        plt.title(f'Portfolio Correlation Matrix ({period} period)', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.show()
        
        # Print high correlation pairs (for risk analysis)
        print("\nHigh Correlation Pairs (|correlation| > 0.7):")
        high_corr_pairs = []
        for i in range(len(correlation_matrix.columns)):
            for j in range(i+1, len(correlation_matrix.columns)):
                corr = correlation_matrix.iloc[i, j]
                if abs(corr) > 0.7:
                    high_corr_pairs.append((
                        correlation_matrix.columns[i],
                        correlation_matrix.columns[j],
                        corr
                    ))
        
        if high_corr_pairs:
            for pair in sorted(high_corr_pairs, key=lambda x: abs(x[2]), reverse=True):
                print(f"  {pair[0]} - {pair[1]}: {pair[2]:.3f}")
        else:
            print("No highly correlated pairs found")
            
        return correlation_matrix
