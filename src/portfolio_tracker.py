import config
import os 
import pandas as pd 
import numpy as np 
from scipy import stats
import yfinance as yf 
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns
from plotly.subplots import make_subplots
import concurrent.futures
import warnings


class PortfolioTracker:
    def __init__(self, trades_df):
        self.trades = trades_df.copy()
        self.symbols = self.trades[self.trades['SYMBOL'] != 'CASH']['SYMBOL'].unique().tolist()
        self.market_data = {}
        self.dividends = {}
        self.splits = {}
        self.asset_info = {}
        self.start_date = self.trades['DATE'].min()
        self.end_date = datetime.now()
        self.dividend_history = []
        
    def fetch_market_data(self):
        print(f"Fetching data for: {self.symbols}")

        def process_symbol(symbol):
            try:
                ticker = yf.Ticker(symbol)
                start_str = (self.start_date - timedelta(days=5)).strftime('%Y-%m-%d')
                
                # --- DAILY DATA ---
                file_name = f'{symbol}.csv'
                daily_path = os.path.join(config.DAILY_DATA_DIR, file_name)
                existing_data = pd.DataFrame()
                
                if os.path.exists(daily_path):
                    try:
                        existing_data = pd.read_csv(daily_path, index_col=0, parse_dates=True)
                    except Exception: pass
                
                new_hist = ticker.history(start=start_str, auto_adjust=False)
                
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

                # --- DIVIDENDS & SPLITS ---
                divs = ticker.dividends
                splits = ticker.splits
                self.dividends[symbol] = divs.tz_localize(None) if divs.index.tz is not None else divs
                self.splits[symbol] = splits.tz_localize(None) if splits.index.tz is not None else splits
                
                # --- ASSET INFO ---
                try:
                    self.asset_info[symbol] = ticker.info
                except Exception:
                    self.asset_info[symbol] = {}

                # --- MINUTE DATA ---
                minute_path = os.path.join(config.MINUTE_DATA_DIR, file_name)
                existing_min = pd.DataFrame()
                if os.path.exists(minute_path):
                    try:
                        existing_min = pd.read_csv(minute_path, index_col=0, parse_dates=True)
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
                        
            except Exception as e:
                print(f"Error processing {symbol}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(process_symbol, self.symbols)
            
    def process_portfolio(self):
        date_range = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        
        # Initialize tracking variables
        portfolio_history = []
        holdings = {sym: 0 for sym in self.symbols}
        cash = 0.0
        invested_capital = 0.0

        weight_history = []
        
        # Iterate through each day
        for current_date in date_range:
            daily_net_flow = 0.0 
            
            # Process trades for this day
            day_trades = self.trades[self.trades['DATE'] == current_date]
            for _, trade in day_trades.iterrows():
                symbol = trade['SYMBOL']
                qty = trade['QTY']
                price = trade['PRICE']
                amt = trade['AMT']
                type_ = trade['BUY/SELL']
                
                if symbol == 'CASH':
                    if type_ == 'DEPOSIT':
                        cash += amt
                        invested_capital += amt
                        daily_net_flow += amt
                    elif type_ == 'WITHDRAW':
                        cash -= amt
                        invested_capital -= amt
                        daily_net_flow -= amt
                else:
                    if type_ == 'BUY':
                        holdings[symbol] += qty
                        cash -= amt
                        # Transaction cost can be added here
                    elif type_ == 'SELL':
                        holdings[symbol] -= qty
                        cash += amt
            
            # Process Dividends & Splits
            daily_value = 0.0
            current_asset_values = {} # Store value per asset for weight calc
            
            for symbol in self.symbols:
                if symbol not in self.market_data or self.market_data[symbol].empty:
                    current_asset_values[symbol] = 0.0
                    continue
                    
                df = self.market_data[symbol]
                
                # Get price
                try:
                    idx = df.index.get_indexer([current_date], method='pad')[0]
                    if idx == -1:
                        price = 0 # Before data start
                    else:
                        price = df.iloc[idx]['Close']
                        
                    # Check for Split
                    if current_date in self.splits[symbol].index:
                        split_ratio = self.splits[symbol].loc[current_date]
                        holdings[symbol] *= split_ratio
                        
                    # Check for Dividend
                    if current_date in self.dividends[symbol].index:
                        div_amt = self.dividends[symbol].loc[current_date]
                        # Check if treasury (simple check for now, can be expanded)
                        is_treasury = symbol in config.NO_DIVIDEND_TAX 
                        tax_rate = 0.0 if is_treasury else 0.30
                        net_div = div_amt * (1 - tax_rate)
                        total_div = holdings[symbol] * net_div
                        
                        if total_div > 0:
                            cash += total_div
                            self.dividend_history.append({
                                'Date': current_date,
                                'Symbol': symbol,
                                'Amount': total_div
                            })
                    
                    val = holdings[symbol] * price
                    daily_value += val
                    current_asset_values[symbol] = val
                        
                except Exception as e:
                    price = 0
                
            total_equity = daily_value + cash

            # --- Record Weights ---
            if total_equity > 0:
                daily_weights = {k: v / total_equity for k, v in current_asset_values.items()}
            else:
                daily_weights = {k: 0 for k in current_asset_values}
            
            daily_weights['Date'] = current_date
            weight_history.append(daily_weights)
            
            portfolio_history.append({
                'Date': current_date,
                'Cash': cash,
                'Market_Value': daily_value,
                'Total_Equity': total_equity,
                'Invested_Capital': invested_capital,
                'Net_Flow': daily_net_flow
            })

        # Convert to DataFrame
        self.df_portfolio = pd.DataFrame(portfolio_history).set_index('Date')
        self.df_portfolio = self.df_portfolio[self.df_portfolio.index.dayofweek < 5]

        self.historical_weights = pd.DataFrame(weight_history).set_index('Date')
        self.historical_weights = self.historical_weights[self.historical_weights.index.dayofweek < 5]
        
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
            print("  No highly correlated pairs found")
            
        return correlation_matrix
