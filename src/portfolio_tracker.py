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
        asset_trades = self.trades[self.trades['ACTION'].isin(['BUY', 'SELL'])]
        self.symbols = asset_trades['SYMBOL'].unique().tolist()
        self.market_data = {}
        self.dividends = {}
        self.splits = {}
        self.asset_info = {}
        df_dates = pd.to_datetime(self.trades['DATE'])
        self.start_date = df_dates.min()
        self.end_date = max(datetime.now(), df_dates.max())
        self.dividend_history = []
        
    def fetch_market_data(self, update=True, show_timing=False, force_update=False, force_update_minute=False, verbose=False):
        
        collector = TimingCollector(enabled=show_timing)
        metadata_path = os.path.join(config.DATA_DIR, "portfolio_metadata.pkl")
        
        # Identify unique markets and currencies from trades
        unique_markets = self.trades['MARKET'].unique().tolist()
        
        # Also include destination markets from EXCHANGE actions
        exchange_mask = self.trades['ACTION'] == 'EXCHANGE'
        if exchange_mask.any():
            unique_markets += self.trades[exchange_mask]['SYMBOL'].unique().tolist()
            unique_markets = list(set(unique_markets))

        required_currencies = [config.MARKET_REGISTRY[m]['currency'] for m in unique_markets if m in config.MARKET_REGISTRY]
        
        # Always include base and secondary currencies
        if config.BASE_CURRENCY not in required_currencies:
            required_currencies.append(config.BASE_CURRENCY)
        if hasattr(config, 'SECONDARY_CURRENCY') and config.SECONDARY_CURRENCY and config.SECONDARY_CURRENCY not in required_currencies:
            required_currencies.append(config.SECONDARY_CURRENCY)
        
        required_currencies = list(set(required_currencies))
        
        # --- UPDATE SUPPRESSION LOGIC ---
        # If metadata exists and was updated today, skip fetching new metadata unless forced
        update_metadata = update
        if update and not force_update and os.path.exists(metadata_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(metadata_path))
            if mtime.date() == datetime.now().date():
                print(f"ℹ️  Metadata already updated today ({mtime.strftime('%H:%M:%S')}). Skipping fresh metadata fetch...")
                update_metadata = False
        
        # Pre-load metadata from cache if we are suppressing it, or if update=False
        if not update_metadata or not update:
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'rb') as f:
                        meta = pickle.load(f)
                        self.dividends = meta.get("dividends", {})
                        self.splits = meta.get("splits", {})
                        self.asset_info = meta.get("asset_info", {})
                except Exception as e:
                    print(f"Error loading metadata: {e}")
                    update_metadata = update # Force fetch if cache is corrupted
            else:
                if not update:
                    print(f"No metadata cache found.")
                update_metadata = update
            
        if not update:
            print("⚠️  Loading data from local cache...")

            for symbol in self.symbols:
                market = self.trades[self.trades['SYMBOL'] == symbol]['MARKET'].iloc[0]
                market_dir = os.path.join(config.DAILY_DATA_DIR, market)
                file_path = os.path.join(market_dir, f"{symbol}.csv")
                
                if os.path.exists(file_path):
                    df = pd.read_csv(file_path, index_col=0)
                    df.index = pd.to_datetime(df.index, errors='coerce')
                    self.market_data[symbol] = df[df.index.notna()].sort_index()
                else:
                    print(f"Warning: No local data for {symbol} in {market}")
            
            # Load FX data
            for curr in required_currencies:
                if curr == config.BASE_CURRENCY: continue
                pair = f"{curr}{config.BASE_CURRENCY}=X"
                market_dir = os.path.join(config.DAILY_DATA_DIR, "FX")
                file_path = os.path.join(market_dir, f"{pair}.csv")
                if os.path.exists(file_path):
                    df = pd.read_csv(file_path, index_col=0)
                    df.index = pd.to_datetime(df.index, errors='coerce')
                    self.market_data[pair] = df[df.index.notna()].sort_index()
            return 
            
        print(f"Processing data for markets: {unique_markets}")

        # Prepare FX pairs
        fx_pairs = [f"{curr}{config.BASE_CURRENCY}=X" for curr in required_currencies if curr != config.BASE_CURRENCY]
        all_fetch_items = [(s, self.trades[self.trades['SYMBOL'] == s]['MARKET'].iloc[0]) for s in self.symbols]
        all_fetch_items += [(p, "FX") for p in fx_pairs]

        def process_item(item):
            symbol, market = item
            try:
                ticker = yf.Ticker(symbol)
                start_str = (self.start_date - timedelta(days=5)).strftime('%Y-%m-%d')
                
                # --- DAILY DATA DOWNLOAD ---
                market_dir = os.path.join(config.DAILY_DATA_DIR, market)
                os.makedirs(market_dir, exist_ok=True)
                file_path = os.path.join(market_dir, f'{symbol}.csv')
                existing_data = pd.DataFrame()
                cache_readable = True
                
                if os.path.exists(file_path):
                    try:
                        df = pd.read_csv(file_path, index_col=0)
                        df.index = pd.to_datetime(df.index, errors='coerce')
                        existing_data = df[df.index.notna()].sort_index()
                    except Exception as e:
                        print(f"  [!] {symbol}: Error reading cache: {e}. Skipping write-back to protect history.")
                        cache_readable = False
                
                today = datetime.now().strftime('%Y-%m-%d')
                
                def try_download(current_hist_state):
                    t_start_hist = time.perf_counter()
                    new_hist = ticker.history(start=start_str, auto_adjust=False)
                    collector.record(f"Daily Data Download ({symbol})", time.perf_counter() - t_start_hist)
                    
                    if not new_hist.empty:
                        new_hist.index = new_hist.index.tz_localize(None)
                        # Drop rows where Close is NaN to prevent erasing valid cache data
                        new_hist_clean = new_hist.dropna(subset=['Close'])
                        
                        if not current_hist_state.empty:
                            combined = pd.concat([current_hist_state, new_hist_clean])
                            combined = combined[~combined.index.duplicated(keep='last')]
                            combined.sort_index(inplace=True)
                            hist = combined
                        else:
                            hist = new_hist_clean
                        
                        if cache_readable:
                            hist.to_csv(file_path)
                        return hist, new_hist_clean
                    return current_hist_state, new_hist

                # Initial attempt
                hist, new_hist = try_download(existing_data)
                
                # Check for staleness or empty download
                latest_close = hist['Close'].dropna().iloc[-1] if not hist['Close'].dropna().empty else None
                latest_date = hist['Close'].dropna().index[-1].strftime('%Y-%m-%d') if latest_close is not None else 'N/A'
                
                retried = False
                # Retry if stale OR if the initial download was empty (transient failure)
                if (latest_date != today or new_hist.empty):
                    # If it's empty, we definitely want a retry. If it's stale, we try once more.
                    reason = "Data stale" if not new_hist.empty else "No data received"
                    print(f"  [RETRY] {symbol}: {reason} ({latest_date}). Retrying...")
                    # Pass the updated state to the retry
                    hist, new_hist = try_download(hist)
                    latest_close = hist['Close'].dropna().iloc[-1] if not hist['Close'].dropna().empty else None
                    latest_date = hist['Close'].dropna().index[-1].strftime('%Y-%m-%d') if latest_close is not None else 'N/A'
                    retried = True

                t_start_proc = time.perf_counter()
                if not hist.empty:
                    self.market_data[symbol] = hist
                    if latest_close is not None:
                        status = "[OK]" if latest_date == today else "[~]"
                        # Logic: always print if not OK/-, otherwise only if verbose
                        should_print = verbose or status == "[~]"
                        
                        if should_print or (not verbose and retried):
                            # Adjust status if it was cached but today
                            final_status = status
                            if status == "[OK]" and new_hist.empty:
                                final_status = "[-]"
                                if not verbose: should_print = False # Don't print [-] in non-verbose

                            if should_print or retried:
                                action_str = f"Downloaded {len(new_hist)} rows" if not new_hist.empty else "Using cache"
                                retry_str = " (after retry)" if retried else ""
                                print(f"  {final_status} {symbol}: {action_str}{retry_str}. Last: {latest_close:.4f} ({latest_date})")
                    else:
                        print(f"  [!] {symbol}: Data exists but latest Close is NaN!")
                else:
                    print(f"  [X] {symbol}: No data found.")
                collector.record(f"Daily Data Processing ({symbol})", time.perf_counter() - t_start_proc)

                # FX pairs don't need dividends/splits/minute-data
                if market == "FX":
                    return

                # --- METADATA RETRIEVAL (DIVIDENDS, SPLITS, INFO) ---
                if update_metadata:
                    t_start_meta = time.perf_counter()
                    divs = ticker.dividends
                    splits = ticker.splits
                    self.dividends[symbol] = divs.tz_localize(None) if divs.index.tz is not None else divs
                    self.splits[symbol] = splits.tz_localize(None) if splits.index.tz is not None else splits
                    
                    try:
                        self.asset_info[symbol] = ticker.info
                    except Exception:
                        self.asset_info[symbol] = {}
                    collector.record(f"Metadata Retrieval ({symbol})", time.perf_counter() - t_start_meta)

                # --- MINUTE DATA ---
                t_start_min = time.perf_counter()
                min_market_dir = os.path.join(config.MINUTE_DATA_DIR, market)
                os.makedirs(min_market_dir, exist_ok=True)
                minute_path = os.path.join(min_market_dir, f'{symbol}.csv')
                
                should_update_minute = True
                if os.path.exists(minute_path) and not (force_update_minute or force_update):
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
                    
                    collector.record(f"Minute Data Processing ({symbol})", time.perf_counter() - t_start_min)

            except Exception as e:
                print(f"Error processing {symbol}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            executor.map(process_item, all_fetch_items)

        # --- Save metadata to cache --- 
        if update_metadata:
            try: 
                with open(metadata_path, "wb") as f:
                    pickle.dump({
                        "dividends": self.dividends,
                        "splits": self.splits,
                        "asset_info": self.asset_info
                    }, f)
                print("✅ Market data and metadata updated successfully.")
            except Exception as e:
                print(f"Error saving metadata: {e}")
        
        collector.print_summary()
            
    def process_portfolio(self):
        # 1. Setup Time Index
        date_range = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        full_idx = date_range

        # 2. Pre-process Trades
        trades = self.trades.copy()
        trades['DATE'] = pd.to_datetime(trades['DATE'])
        
        # 3. Align Market Data, Splits, Dividends, and FX
        unique_markets = trades['MARKET'].unique().tolist()
        
        # Also include destination markets from EXCHANGE actions
        exchange_mask = trades['ACTION'] == 'EXCHANGE'
        if exchange_mask.any():
            unique_markets += trades[exchange_mask]['SYMBOL'].unique().tolist()
            unique_markets = list(set(unique_markets))

        required_currencies = list(set([config.MARKET_REGISTRY[m]['currency'] for m in unique_markets if m in config.MARKET_REGISTRY]))
        
        # Always include base and secondary currencies
        if config.BASE_CURRENCY not in required_currencies:
            required_currencies.append(config.BASE_CURRENCY)
        if hasattr(config, 'SECONDARY_CURRENCY') and config.SECONDARY_CURRENCY and config.SECONDARY_CURRENCY not in required_currencies:
            required_currencies.append(config.SECONDARY_CURRENCY)
        
        required_currencies = list(set(required_currencies))
        
        price_df = pd.DataFrame(1.0, index=full_idx, columns=self.symbols)
        split_df = pd.DataFrame(1.0, index=full_idx, columns=self.symbols)
        div_df = pd.DataFrame(0.0, index=full_idx, columns=self.symbols)
        fx_df = pd.DataFrame(1.0, index=full_idx, columns=required_currencies)

        for sym in self.symbols:
            market = trades[trades['SYMBOL'] == sym]['MARKET'].iloc[0]
            # Prices - ensure we only propagate valid (non-NaN) historical prices
            if sym in self.market_data and not self.market_data[sym].empty:
                df = self.market_data[sym]
                price_df[sym] = df['Close'].dropna().reindex(full_idx, method='pad').fillna(0)
            else:
                price_df[sym] = 0.0

            # Splits
            if sym in self.splits and not self.splits[sym].empty:
                split_df[sym] = self.splits[sym].reindex(full_idx, fill_value=1.0)

            # Dividends (Net of Tax)
            if sym in self.dividends and not self.dividends[sym].empty:
                tax_rate = config.MARKET_REGISTRY.get(market, {}).get('div_tax', 0.30)
                if sym in config.NO_DIVIDEND_TAX: tax_rate = 0.0
                net_div = self.dividends[sym] * (1 - tax_rate)
                div_df[sym] = net_div.reindex(full_idx, fill_value=0.0)

        # Process FX Rates
        for curr in required_currencies:
            if curr == config.BASE_CURRENCY:
                fx_df[curr] = 1.0
                continue
            pair = f"{curr}{config.BASE_CURRENCY}=X"
            if pair in self.market_data and not self.market_data[pair].empty:
                fx_df[curr] = self.market_data[pair]['Close'].reindex(full_idx, method='pad').ffill().bfill()
            else:
                print(f"Warning: No FX data for {pair}. Using 1.0 (Normalization may be incorrect).")
                fx_df[curr] = 1.0

        # 4. Vectorized Holdings Calculation (Split-Adjusted)
        cum_split = split_df.cumprod()
        prev_cum_split = cum_split.shift(1, fill_value=1.0)
        
        asset_trades_mask = trades['ACTION'].isin(['BUY', 'SELL'])
        trade_qties = trades[asset_trades_mask].groupby(['DATE', 'SYMBOL'])['QTY'].sum().unstack().reindex(full_idx).fillna(0)
        
        # Calculate signed quantities for holdings
        signed_trade_qties = pd.DataFrame(0.0, index=full_idx, columns=self.symbols)
        for sym in self.symbols:
            sym_trades = trades[trades['SYMBOL'] == sym]
            buy_mask = (sym_trades['ACTION'] == 'BUY')
            sell_mask = (sym_trades['ACTION'] == 'SELL')
            
            sym_daily = pd.Series(0.0, index=full_idx)
            buys = sym_trades[buy_mask].groupby('DATE')['QTY'].sum()
            sells = sym_trades[sell_mask].groupby('DATE')['QTY'].sum()
            
            sym_daily = sym_daily.add(buys, fill_value=0).add(-sells, fill_value=0)
            signed_trade_qties[sym] = sym_daily

        adj_qty = signed_trade_qties / prev_cum_split
        holdings_df = adj_qty.cumsum() * cum_split
        
        # 5. Market Value (per asset) - converted to BASE_CURRENCY
        market_value_df = pd.DataFrame(0.0, index=full_idx, columns=self.symbols)
        for sym in self.symbols:
            market = trades[trades['SYMBOL'] == sym]['MARKET'].iloc[0]
            currency = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
            local_mv = holdings_df[sym] * price_df[sym]
            market_value_df[sym] = local_mv * fx_df[currency]

        daily_market_value_base = market_value_df.sum(axis=1)

        # 6. Cash Flow and Dividend Income (Per Currency)
        daily_cash_flow_per_curr = {curr: pd.Series(0.0, index=full_idx) for curr in required_currencies}
        invested_capital_base = pd.Series(0.0, index=full_idx)

        # Asset Trade Cash Flows (including fees)
        for _, row in trades[asset_trades_mask].iterrows():
            market = row['MARKET']
            curr = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
            amount = row['QTY'] * row['PRICE']
            fee = row['FEE']
            if row['ACTION'] == 'BUY':
                daily_cash_flow_per_curr[curr].loc[row['DATE']] -= (amount + fee)
            else:
                daily_cash_flow_per_curr[curr].loc[row['DATE']] += (amount - fee)

        # Dividends per currency
        for sym in self.symbols:
            market = trades[trades['SYMBOL'] == sym]['MARKET'].iloc[0]
            curr = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
            div_income = holdings_df[sym] * div_df[sym]
            daily_cash_flow_per_curr[curr] += div_income
            
            # Record Dividend History
            div_mask = div_income > 1e-6
            for date in div_mask.index[div_mask]:
                local_amount = div_income.loc[date]
                base_amount = local_amount * fx_df[curr].loc[date]
                self.dividend_history.append({
                    'Date': date.strftime('%Y-%m-%d'), 
                    'Symbol': sym, 
                    'Quantity': round(holdings_df[sym].loc[date], 4),
                    'Net DPS': round(div_df[sym].loc[date], 4),
                    'Currency': curr,
                    'Total (Local)': round(local_amount, 2),
                    f'Total ({config.BASE_CURRENCY})': round(base_amount, 2)
                })

        # Cash Trades (Deposits/Withdrawals) & Exchange
        for _, row in trades[trades['ACTION'].isin(['DEPOSIT', 'WITHDRAW', 'EXCHANGE'])].iterrows():
            if row['ACTION'] == 'EXCHANGE':
                # EXCHANGE logic: MARKET is source, SYMBOL is target market code
                src_market = row['MARKET']
                tgt_market = row['SYMBOL']
                src_curr = config.MARKET_REGISTRY.get(src_market, {}).get('currency')
                tgt_curr = config.MARKET_REGISTRY.get(tgt_market, {}).get('currency')
                
                # QTY is amount exiting source, PRICE is amount entering target
                daily_cash_flow_per_curr[src_curr].loc[row['DATE']] -= (row['QTY'] + row['FEE'])
                daily_cash_flow_per_curr[tgt_curr].loc[row['DATE']] += row['PRICE']
            else:
                market = row['MARKET']
                curr = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
                amount = row['PRICE'] # For cash, PRICE is the total amount (compatibility)
                fee = row['FEE']
                
                if row['ACTION'] == 'DEPOSIT':
                    flow = amount - fee
                    daily_cash_flow_per_curr[curr].loc[row['DATE']] += flow
                    invested_capital_base.loc[row['DATE']] += (amount * fx_df[curr].loc[row['DATE']])
                else: # WITHDRAW
                    flow = -(amount + fee)
                    daily_cash_flow_per_curr[curr].loc[row['DATE']] += flow
                    invested_capital_base.loc[row['DATE']] -= (amount * fx_df[curr].loc[row['DATE']])

        # 7. Aggregate Total Cash in BASE_CURRENCY
        total_cash_base = pd.Series(0.0, index=full_idx)
        for curr, flow_series in daily_cash_flow_per_curr.items():
            cum_cash_local = flow_series.cumsum()
            total_cash_base += (cum_cash_local * fx_df[curr])

        # 8. Final Assembly
        total_equity_base = daily_market_value_base + total_cash_base
        invested_capital_cum_base = invested_capital_base.cumsum()
        
        self.df_portfolio = pd.DataFrame({
            'Cash': total_cash_base,
            'Market_Value': daily_market_value_base,
            'Total_Equity': total_equity_base,
            'Invested_Capital': invested_capital_cum_base,
            'Net_Flow': invested_capital_base # This is already daily base flow
        }, index=full_idx)
        
        # Business days filter
        self.df_portfolio = self.df_portfolio[self.df_portfolio.index.dayofweek < 5]
        
        # Weights
        weight_df = market_value_df.divide(total_equity_base, axis=0).fillna(0)
        self.historical_weights = weight_df[weight_df.index.dayofweek < 5]
        
        return self.df_portfolio

    def calculate_correlation_matrix(self, period='3mo', holdings = True):
        """
        Calculate and plot correlation matrix for portfolio holdings
        period: '1mo', '3mo', '6mo', '1y', 'max'
        """
        last_holdings = {}
        for sym in self.symbols:
            buys = self.trades[(self.trades['SYMBOL'] == sym) & (self.trades['ACTION'] == 'BUY')]['QTY'].sum()
            sells = self.trades[(self.trades['SYMBOL'] == sym) & (self.trades['ACTION'] == 'SELL')]['QTY'].sum()
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
