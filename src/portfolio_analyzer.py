import config
import os
import mappings

import pandas as pd 
import numpy as np 
from scipy import stats
from scipy.stats import skew, kurtosis as sp_kurtosis
import yfinance as yf 
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Modern Fintech Palette
COLOR_PORT_MAIN = '#2563eb'  # Premium Blue
COLOR_PORT_ALT = '#1d4ed8'   # Darker Blue
COLOR_BENCHMARK = '#64748b'  # Slate Grey
COLOR_POSITIVE = '#10b981'   # Emerald
COLOR_NEGATIVE = '#ef4444'   # Rose/Red
COLOR_ACCENT = '#8b5cf6'     # Violet
COLOR_TEXT = '#1f2937'       # Slate 800
COLOR_GRID = '#f1f5f9'       # Slate 100

def fetch_fama_french_factors(start_date, end_date):
    """Fetches Fama-French 3-Factor daily data with local caching."""
    import urllib.request
    import zipfile
    import io
    import os
    import pickle
    from datetime import datetime, timedelta

    # --- DOWNLOAD DATA ---
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                filename = z.namelist()[0]
                with z.open(filename) as f:
                    content = f.read().decode('utf-8')
        
        lines = content.split('\n')
        start_idx = next(i for i, line in enumerate(lines) if line.startswith(',Mkt-RF'))
        end_idx = start_idx + 1
        for i, line in enumerate(lines[start_idx+1:]):
            if not line.strip() or len(line.split(',')[0]) != 8:
                end_idx = start_idx + 1 + i
                break
                
        csv_data = "\n".join(lines[start_idx:end_idx])
        ff_df = pd.read_csv(io.StringIO(csv_data), index_col=0)
        ff_df.index = pd.to_datetime(ff_df.index.astype(str), format='%Y%m%d')
        ff_df.columns = ff_df.columns.str.strip()
        for col in ff_df.columns:
            ff_df[col] = pd.to_numeric(ff_df[col], errors='coerce') / 100.0
            
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        return ff_df[(ff_df.index >= start) & (ff_df.index <= end)]
    except Exception as e:
        print(f"⚠️  Error fetching Fama-French factors: {e}")
        return None

class PortfolioAnalyzer:
    def __init__(self, history_df, trades_df, tracker_obj):
        self.history_df = history_df.copy()
        self.trades = trades_df.copy()
        self.tracker = tracker_obj
        
        # Benchmarks
        self.benchmarks = {}
        unique_markets = self.trades['MARKET'].unique()
        benchmark_tickers = []
        for market in unique_markets:
            if market in config.MARKET_REGISTRY:
                ticker = config.MARKET_REGISTRY[market]['benchmark']
                self.benchmarks[market] = ticker
                benchmark_tickers.append(ticker)
        
        # Also include standard plot benchmarks from config
        benchmark_tickers.extend(config.PLOT_BENCHMARK)
        benchmark_tickers = list(set(benchmark_tickers))
        
        self.benchmark_data = {}
        self._fetch_benchmark_data(benchmark_tickers)
        self._prepare_data()

    def _fetch_benchmark_data(self, tickers):
        for ticker_symbol in tickers:
            # Find which market this benchmark belongs to for storage path
            market = "US" # Default
            for m, props in config.MARKET_REGISTRY.items():
                if props['benchmark'] == ticker_symbol:
                    market = m
                    break
            
            market_dir = os.path.join(config.DAILY_DATA_DIR, market)
            file_path = os.path.join(market_dir, f"{ticker_symbol}.csv")
            
            if os.path.exists(file_path):
                # Handle possible MultiIndex header from yfinance download
                df = pd.read_csv(file_path, index_col=0, header=[0, 1] if '^' in ticker_symbol else 0)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Cleanup index if it contains 'Ticker' or 'Date' from MultiIndex artifacts
                df = df[~df.index.isin(['Ticker', 'Date'])]
                df.index = pd.to_datetime(df.index)
                self.benchmark_data[ticker_symbol] = df['Close'].reindex(self.history_df.index, method='pad').fillna(0)
            else:
                print(f"Downloading benchmark data for {ticker_symbol}...")
                data = yf.download(ticker_symbol, start=self.tracker.start_date, end=datetime.now(), progress=False)
                if not data.empty:
                    # Flatten MultiIndex if present
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)
                    
                    os.makedirs(market_dir, exist_ok=True)
                    data.to_csv(file_path)
                    self.benchmark_data[ticker_symbol] = data['Close'].reindex(self.history_df.index, method='pad').fillna(0)

    def _prepare_data(self):
        """Ensures fundamental return and PnL columns are present in history_df."""
        df = self.history_df
        df['Prev_Equity'] = df['Total_Equity'].shift(1)
        
        # Time-weighted daily return formula
        df['Daily_Return'] = (
            (df['Total_Equity'] - df['Prev_Equity'] - df['Net_Flow']) / 
            (df['Prev_Equity'] + 0.5 * df['Net_Flow'])
        ).fillna(0)
        
        df['Daily_PnL'] = df['Total_Equity'] - df['Prev_Equity'] - df['Net_Flow']
        df['Cumulative_Return'] = (1 + df['Daily_Return']).cumprod() - 1
        df['PnL'] = df['Total_Equity'] - df['Invested_Capital']
        
        # Risk-Free Rate
        try:
            irx_ticker = yf.Ticker("^IRX")
            start_date_str = df.index.min().strftime('%Y-%m-%d')
            irx_hist = irx_ticker.history(start=start_date_str)['Close']
            irx_hist.index = irx_hist.index.tz_localize(None)
            
            df['Risk_Free_Rate_Annual'] = irx_hist / 100  # Convert percentage to decimal
            df['Risk_Free_Rate_Annual'] = df['Risk_Free_Rate_Annual'].ffill().fillna(0.04)
            df['Risk_Free_Rate_Daily'] = (1 + df['Risk_Free_Rate_Annual']) ** (1/365) - 1
        except Exception as e:
            print(f"Error fetching Risk Free Rate: {e}")
            df['Risk_Free_Rate_Daily'] = (1.04 ** (1/365)) - 1
    
    def calculate_metrics(self):
        """Calculates performance and risk metrics. Returns a dictionary of results."""
        df = self.history_df
        
        # Benchmark & Beta calculation (Vectorized where possible)
        try:
            benchmark_symbol = config.METRICS_BENCHMARK
            benchmark_ticker = yf.Ticker(benchmark_symbol)
            start_date_str = df.index.min().strftime('%Y-%m-%d')
            benchmark_hist = benchmark_ticker.history(start=start_date_str)['Close']
            benchmark_hist.index = benchmark_hist.index.tz_localize(None)
            benchmark_returns = benchmark_hist.pct_change().fillna(0)
            
            # Align benchmarks with portfolio date range
            aligned_data = pd.DataFrame({
                'Portfolio': df['Daily_Return'],
                benchmark_symbol: benchmark_returns,
                'Risk_Free_Rate': df['Risk_Free_Rate_Daily']
            }, index=df.index).dropna()
            
            if len(aligned_data) > 10:
                # Use OLS for beta and alpha
                beta, alpha_ols, r_value, p_value, std_err = stats.linregress(
                    aligned_data[benchmark_symbol], aligned_data['Portfolio']
                )
                portfolio_beta = beta
                benchmark_total_return = (1 + aligned_data[benchmark_symbol]).prod() - 1
                tracking_error = (aligned_data['Portfolio'] - aligned_data[benchmark_symbol]).std() * np.sqrt(252)
                
                # Capture Ratios
                down_market = aligned_data[aligned_data[benchmark_symbol] < 0]
                if len(down_market) > 5:
                    port_down = (1 + down_market['Portfolio']).prod() - 1
                    bench_down = (1 + down_market[benchmark_symbol]).prod() - 1
                    down_capture = port_down / bench_down if bench_down != 0 else np.nan
                else:
                    down_capture = np.nan

                up_market = aligned_data[aligned_data[benchmark_symbol] > 0]
                if len(up_market) > 5:
                    port_up = (1 + up_market['Portfolio']).prod() - 1
                    bench_up = (1 + up_market[benchmark_symbol]).prod() - 1
                    up_capture = port_up / bench_up if bench_up != 0 else np.nan
                else:
                    up_capture = np.nan

                # Benchmark Sharpe & Sortino
                excess_bench = aligned_data[benchmark_symbol] - aligned_data['Risk_Free_Rate']
                benchmark_sharpe_ratio = (excess_bench.mean() * 252) / (aligned_data[benchmark_symbol].std() * np.sqrt(252)) if aligned_data[benchmark_symbol].std() > 0 else np.nan
                
                downside_bench = aligned_data[benchmark_symbol][aligned_data[benchmark_symbol] < aligned_data['Risk_Free_Rate']]
                benchmark_sortino_ratio = (excess_bench.mean() * 252) / (downside_bench.std() * np.sqrt(252)) if len(downside_bench) > 1 and downside_bench.std() > 0 else np.nan
            else:
                portfolio_beta = benchmark_total_return = tracking_error = down_capture = up_capture = benchmark_sharpe_ratio = benchmark_sortino_ratio = np.nan
                
        except Exception as e:
            print(f"Error calculating Benchmark/Beta: {e}")
            portfolio_beta = benchmark_total_return = tracking_error = down_capture = up_capture = benchmark_sharpe_ratio = benchmark_sortino_ratio = np.nan
        
        # Risk Ratios
        excess_returns = df['Daily_Return'] - df['Risk_Free_Rate_Daily']
        sharpe_ratio = (excess_returns.mean() * 252) / (df['Daily_Return'].std() * np.sqrt(252)) if len(df) > 1 and df['Daily_Return'].std() > 0 else np.nan
        
        downside_returns = df.loc[df['Daily_Return'] < df["Risk_Free_Rate_Daily"], 'Daily_Return']
        sortino_ratio = (excess_returns.mean() * 252) / (downside_returns.std() * np.sqrt(252)) if len(downside_returns) > 1 and downside_returns.std() > 0 else np.nan

        # Alpha (Annualized)
        if not np.isnan(portfolio_beta):
            port_ret_ann = (1 + ((1 + df['Daily_Return']).prod() - 1)) ** (252/len(df)) - 1
            bench_ret_ann = (1 + benchmark_total_return) ** (252/len(df)) - 1
            rf_ann = (1 + ((1 + df['Risk_Free_Rate_Daily']).prod() - 1)) ** (252/len(df)) - 1
            alpha = port_ret_ann - (rf_ann + portfolio_beta * (bench_ret_ann - rf_ann))
        else:
            alpha = np.nan
        
        volatility = df['Daily_Return'].std() * np.sqrt(252) if len(df) > 1 else 0
        var_95_percent = np.percentile(df['Daily_Return'], 5) if len(df) > 10 else np.nan
        var_95_dollar = np.percentile(df['Daily_PnL'], 5) if len(df) > 10 else np.nan
        
        total_return = (df['Total_Equity'].iloc[-1] / df['Invested_Capital'].iloc[-1]) - 1 if len(df) > 0 else 0
        
        # Calculate Max Drawdown based on time-weighted returns (consistent with plot)
        cum_returns = 1 + df['Cumulative_Return']
        running_max = cum_returns.cummax()
        drawdown_pct = (cum_returns / running_max) - 1
        max_drawdown = drawdown_pct.min() if len(df) > 0 else 0
        
        # Advanced Stats
        daily_ret = df['Daily_Return'].dropna()
        skewness = skew(daily_ret, bias=False) if len(daily_ret) > 3 else np.nan
        kurtosis_val = sp_kurtosis(daily_ret, bias=False) if len(daily_ret) > 3 else np.nan
        
        tail_returns = daily_ret[daily_ret <= np.percentile(daily_ret, 5)] if len(daily_ret) > 10 else []
        cvar_95 = tail_returns.mean() if len(tail_returns) > 0 else np.nan
        
        ulcer_index = np.sqrt(((((1 + daily_ret).cumprod() / (1 + daily_ret).cumprod().cummax()) - 1) * 100)**2).mean() if len(df) > 1 else np.nan
        
        # Recovery Analysis
        ttrs = []
        is_dd = cum_returns < running_max
        dd_start = None
        for i, val in enumerate(is_dd):
            if val:
                if dd_start is None: dd_start = i
            elif dd_start is not None:
                ttrs.append(i - dd_start)
                dd_start = None
        if dd_start is not None: ttrs.append(len(is_dd) - dd_start)
        avg_ttr = np.mean(ttrs) if ttrs else 0
        max_ttr = max(ttrs) if ttrs else 0

        # Calmar & Information Ratios
        port_ret_ann = (1 + ((1 + df['Daily_Return']).prod() - 1)) ** (252/len(df)) - 1 if len(df) > 0 else 0
        calmar_ratio = port_ret_ann / abs(max_drawdown) if max_drawdown != 0 else np.nan
        
        try:
            bench_ret_ann = (1 + benchmark_total_return) ** (252/len(df)) - 1 if len(df) > 0 else 0
            information_ratio = (port_ret_ann - bench_ret_ann) / tracking_error if tracking_error > 0 else np.nan
        except:
            information_ratio = np.nan

        # Treynor Ratio
        rf_ann = (1 + ((1 + df['Risk_Free_Rate_Daily']).prod() - 1)) ** (252/len(df)) - 1 if len(df) > 0 else 0
        treynor_ratio = (port_ret_ann - rf_ann) / portfolio_beta if not np.isnan(portfolio_beta) and portfolio_beta != 0 else np.nan

        self.metrics = {
            'first_date': df.index[0],
            'sharpe_ratio': sharpe_ratio,
            'benchmark_sharpe_ratio': benchmark_sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'benchmark_sortino_ratio': benchmark_sortino_ratio,
            'portfolio_beta': portfolio_beta,
            'alpha': alpha,
            'volatility': volatility,
            'var_95_percent_return': var_95_percent,
            'var_95_dollar': var_95_dollar,
            'total_return': total_return,
            'max_return': max(df['PnL']) if len(df) > 0 else 0,
            'total_cum_return': df['Cumulative_Return'].iloc[-1] if len(df) > 0 else 0,
            'max_drawdown': max_drawdown,
            'benchmark_return': benchmark_total_return,
            'tracking_error': tracking_error,
            'down_capture': down_capture,
            'up_capture': up_capture,
            'skewness': skewness,
            'kurtosis': kurtosis_val,
            'cvar_95': cvar_95,
            'ulcer_index': ulcer_index,
            'avg_ttr': avg_ttr,
            'max_ttr': max_ttr,
            'calmar_ratio': calmar_ratio,
            'information_ratio': information_ratio,
            'treynor_ratio': treynor_ratio,
        }
        return self.metrics

    def get_pnl_plot(self, show=False):
        df = self.history_df
        fig = go.Figure()

        fig.add_trace(go.Scatter(x=df.index, y=df['PnL'], mode='lines', name='Total PnL', line=dict(color='black', width=1), hovertemplate="<b>%{x}</b><br>PnL: " + config.BASE_CURRENCY + " %{y:,.2f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=df.index, y=df['PnL'].where(df['PnL'] >= 0, 0), mode='none', fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.3)', name='Profit', hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=df.index, y=df['PnL'].where(df['PnL'] < 0, 0), mode='none', fill='tozeroy', fillcolor='rgba(255, 0, 0, 0.3)', name='Loss', hoverinfo='skip'))

        fig.update_layout(title='Interactive Total Profit/Loss Over Time', xaxis_title='Date', yaxis_title=f'PnL ({config.BASE_CURRENCY})', hovermode='x unified', height=500)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        if show: fig.show()
        return fig

    def get_wealth_plot(self, show=False):
        df = self.history_df
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4],
                            subplot_titles=("Portfolio Value & Invested Capital", "Net Profit / Loss"))
        
        # Wealth
        fig.add_trace(go.Scatter(x=df.index, y=df['Invested_Capital'], mode='lines', name='Invested Capital', line=dict(color='#94a3b8', width=1.5, dash='dot'), hovertemplate="Invested: " + config.BASE_CURRENCY + " %{y:,.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Total_Equity'], mode='lines', name='Total Equity', line=dict(color=COLOR_PORT_MAIN, width=2.5), fill='tonexty', fillcolor='rgba(37, 99, 235, 0.08)', hovertemplate="Equity: " + config.BASE_CURRENCY + " %{y:,.2f}<extra></extra>"), row=1, col=1)
 
        # PnL
        fig.add_trace(go.Scatter(x=df.index, y=df['PnL'], mode='lines', name='Net PnL', line=dict(color=COLOR_ACCENT, width=2), fill='tozeroy', fillcolor='rgba(139, 92, 246, 0.08)', hovertemplate="PnL: " + config.BASE_CURRENCY + " %{y:,.2f}<extra></extra>"), row=2, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#cbd5e1", row=2, col=1)
        
        fig.update_layout(template="plotly_white", hovermode="x unified", height=700, showlegend=True,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          margin=dict(l=50, r=20, t=60, b=50), font=dict(family="Inter, sans-serif", size=12, color=COLOR_TEXT))
        fig.update_xaxes(title_text='Date', row=2, col=1)
        fig.update_yaxes(title_text=f'Equity ({config.BASE_CURRENCY})', row=1, col=1)
        fig.update_yaxes(title_text=f'PnL ({config.BASE_CURRENCY})', row=2, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        if show: fig.show()
        return fig

    def get_returns_plot(self, show=False):
        df = self.history_df
        benchmark_symbols = config.PLOT_BENCHMARK

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("Historical Daily Returns", "Cumulative Return Comparison"), row_heights=[0.5, 0.5])

        # Daily Returns
        daily_colors = [COLOR_POSITIVE if val >= 0 else COLOR_NEGATIVE for val in df['Daily_Return']]
        fig.add_trace(go.Bar(x=df.index, y=df['Daily_Return'] * 100, name='Daily Return %', marker_color=daily_colors, opacity=0.8, hovertemplate="Daily: %{y:.2f}%<extra></extra>"), row=1, col=1)

        # Cumulative
        fig.add_trace(go.Scatter(x=df.index, y=df['Cumulative_Return'] * 100, mode='lines', name='Portfolio', line=dict(color=COLOR_PORT_MAIN, width=3), fill='tozeroy', fillcolor='rgba(37, 99, 235, 0.05)', hovertemplate="Portfolio: %{y:.2f}%<extra></extra>"), row=2, col=1)

        # Benchmarks
        start_date, end_date = df.index.min(), df.index.max()
        bench_data = yf.download(benchmark_symbols, start=start_date, end=end_date + pd.Timedelta(days=1), progress=False, auto_adjust=True, group_by="column")["Close"]
        if isinstance(bench_data, pd.Series): bench_data = bench_data.to_frame(name=benchmark_symbols[0])
        
        bench_palette = [COLOR_BENCHMARK, COLOR_ACCENT, '#f59e0b', '#ec4899']
        for i, ticker in enumerate(benchmark_symbols):
            if ticker in bench_data.columns:
                series = bench_data[ticker].dropna()
                cum_return = (series / series.iloc[0]) - 1
                fig.add_trace(go.Scatter(x=cum_return.index, y=cum_return * 100, mode='lines', name=ticker, line=dict(color=bench_palette[i % len(bench_palette)], width=1.5), opacity=0.8, hovertemplate="%{n}: %{y:.2f}%<extra></extra>".replace('%{n}', ticker)), row=2, col=1)

        fig.update_layout(template="plotly_white", hovermode="x unified", height=650, showlegend=True,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          font=dict(family="Inter, sans-serif", size=12, color=COLOR_TEXT))
        fig.update_xaxes(title_text='Date', row=2, col=1)
        fig.update_yaxes(title_text='Daily Return (%)', row=1, col=1)
        fig.update_yaxes(title_text='Cumulative Return (%)', row=2, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#cbd5e1", row=1, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#cbd5e1", row=2, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        if show: fig.show()
        return fig

    def get_drawdown_plot(self, show=False):
        df = self.history_df
        cum_returns = (1 + df['Daily_Return']).cumprod()
        running_max = cum_returns.cummax()
        drawdown_pct = (cum_returns / running_max) - 1

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("Cumulative Return & Running Peak", "Portfolio Drawdown (Underwater)"), row_heights=[0.6, 0.4])

        fig.add_trace(go.Scatter(x=df.index, y=(running_max - 1) * 100, mode='lines', name='Peak Return', line=dict(color='#94a3b8', width=1, dash='dot'), hovertemplate="Peak: %{y:.2f}%<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=(cum_returns - 1) * 100, mode='lines', name='Portfolio', line=dict(color=COLOR_PORT_MAIN, width=2.5), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.05)', hovertemplate="Return: %{y:.2f}%<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=drawdown_pct * 100, mode='lines', name='Drawdown %', line=dict(color=COLOR_NEGATIVE, width=1.5), fill='tozeroy', fillcolor='rgba(239, 68, 68, 0.15)', hovertemplate="Drawdown: %{y:.2f}%<extra></extra>"), row=2, col=1)

        fig.update_layout(template="plotly_white", height=600, showlegend=True, hovermode="x unified",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          margin=dict(l=50, r=20, t=60, b=50), font=dict(family="Inter, sans-serif", size=12, color=COLOR_TEXT))
        fig.update_xaxes(title_text='Date', row=2, col=1)
        fig.update_yaxes(title_text='Return (%)', row=1, col=1)
        fig.update_yaxes(title_text='Drawdown (%)', row=2, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        if show: fig.show()
        return fig

    def get_allocation(self, show=False):
        """Calculates asset allocation across symbols, categories, and sectors."""
        trades_df = self.trades
        portfolio_tracker = self.tracker
        history_df = self.history_df
        
        last_holdings = {}
        for sym in portfolio_tracker.symbols:
            buys = trades_df[(trades_df['SYMBOL'] == sym) & (trades_df['ACTION'] == 'BUY')]['QTY'].sum()
            sells = trades_df[(trades_df['SYMBOL'] == sym) & (trades_df['ACTION'] == 'SELL')]['QTY'].sum()
            last_holdings[sym] = buys - sells

        current_holdings = {k: v for k, v in last_holdings.items() if v > 0}
        current_values = {}
        for sym, qty in current_holdings.items():
            if sym in portfolio_tracker.market_data and not portfolio_tracker.market_data[sym].empty:
                local_price = portfolio_tracker.market_data[sym].iloc[-1]['Close']
                
                # Normalize to BASE_CURRENCY
                market = trades_df[trades_df['SYMBOL'] == sym]['MARKET'].iloc[0]
                currency = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
                fx_rate = 1.0
                if currency != config.BASE_CURRENCY:
                    pair = f"{currency}{config.BASE_CURRENCY}=X"
                    if pair in portfolio_tracker.market_data and not portfolio_tracker.market_data[pair].empty:
                        fx_rate = portfolio_tracker.market_data[pair].iloc[-1]['Close']
                
                current_values[sym] = qty * local_price * fx_rate

        if history_df['Cash'].iloc[-1] > 0:
            current_values['Liquid Cash'] = history_df['Cash'].iloc[-1]

        asset_categories, asset_sectors = {}, {}
        for sym in current_values:
            if sym == 'Liquid Cash':
                asset_categories[sym], asset_sectors[sym] = 'Cash & Equivalents', 'Cash'
                continue
            if sym in mappings.TICKER_OVERRIDES:
                cat = mappings.TICKER_OVERRIDES[sym]
                asset_categories[sym], asset_sectors[sym] = cat, cat
                continue

            info = portfolio_tracker.asset_info.get(sym, {})
            q_type, sector, category_yf, name = info.get('quoteType'), info.get('sector', 'Unknown'), info.get('category'), info.get('longName', '').lower()
            
            if q_type == 'ETF':
                cat = mappings.ETF_CATEGORY_MAP.get(category_yf)
                if not cat:
                    if any(x in name for x in ['treasury', 'gov', 'bills', 'sovereign']): cat = 'Treasury Bonds'
                    elif any(x in name for x in ['corporate', 'credit', 'high yield']): cat = 'Corporate Bonds'
                    elif any(x in name for x in ['bond', 'fixed income']): cat = 'Other Fixed Income'
                    elif any(x in name for x in ['gold', 'silver', 'commodity', 'metal', 'uranium', 'copper']): cat = 'Commodities'
                    else: cat = 'Equity ETF (Other)'
                asset_categories[sym], asset_sectors[sym] = cat, (sector if sector != 'Unknown' else cat)
            elif q_type == 'EQUITY':
                cat = mappings.STOCK_SECTOR_MAP.get(sector, f"{sector} Stocks" if sector != 'Unknown' else 'Individual Stocks')
                asset_categories[sym], asset_sectors[sym] = cat, (sector if sector != 'Unknown' else cat)
            else:
                asset_categories[sym], asset_sectors[sym] = 'Other', (sector if sector != 'Unknown' else 'Other')

        # Formatting
        total_val = sum(current_values.values())
        data_rows = []
        for sym, val in current_values.items():
            data_rows.append({'Symbol': sym, 'Category': asset_categories.get(sym, 'Other'), 'Sector': asset_sectors.get(sym, 'Other'),
                              'Value': val, 'Allocation (%)': (val / total_val) * 100})
        df_alloc = pd.DataFrame(data_rows).sort_values(by='Value', ascending=False).reset_index(drop=True)

        # Visualization
        df_cat = df_alloc.groupby('Category')['Value'].sum().reset_index()
        fig = make_subplots(rows=1, cols=2, specs=[[{'type':'domain'}, {'type':'domain'}]], subplot_titles=['Allocation by Symbol', 'Allocation by Asset Class'])
        palette = ['#2563eb', '#10b981', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4', '#84cc16', '#a855f7']

        fig.add_trace(go.Pie(labels=df_alloc['Symbol'], values=df_alloc['Value'], hole=0.45, 
                             marker=dict(colors=palette, line=dict(color='#ffffff', width=2)),
                             hovertemplate="<b>%{label}</b><br>" + config.BASE_CURRENCY + " %{value:,.2f}<br>%{percent}<extra></extra>"), 1, 1)
        fig.add_trace(go.Pie(labels=df_cat['Category'], values=df_cat['Value'], hole=0.45, 
                             marker=dict(colors=palette, line=dict(color='#ffffff', width=2)),
                             hovertemplate="<b>%{label}</b><br>" + config.BASE_CURRENCY + " %{value:,.2f}<br>%{percent}<extra></extra>"), 1, 2)
        
        fig.update_layout(template='plotly_white', height=500, margin=dict(t=80, b=120, l=20, r=20), showlegend=True,
                          legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5),
                          font=dict(family="Inter, sans-serif", size=12, color=COLOR_TEXT),
                          annotations=[dict(text='<b>By Symbol</b>', x=0.225, y=0.5, showarrow=False, font=dict(size=12), xref="paper", yref="paper"),
                                       dict(text='<b>By Class</b>', x=0.775, y=0.5, showarrow=False, font=dict(size=12), xref="paper", yref="paper")])
        if show: fig.show()

        # Cache results for summary sheet
        self.allocation_data = {
            'fig': fig,
            'df_alloc': df_alloc,
            'category_values': df_alloc.groupby('Category')['Value'].sum().to_dict(),
            'sector_values': df_alloc.groupby('Sector')['Value'].sum().to_dict(),
            'current_values': current_values,
            'current_holdings': current_holdings
        }
        return self.allocation_data

    def get_quant_plots(self, show=False, windows=[21, 63]):
        df_hist = self.history_df
        start_date = df_hist.index.min().strftime('%Y-%m-%d')
        end_date = (df_hist.index.max() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        bench_ticker = config.METRICS_BENCHMARK
        
        bench_data = yf.download(bench_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
        bench_returns = bench_data['Close'].pct_change().fillna(0)
        if isinstance(bench_returns, pd.DataFrame): bench_returns = bench_returns.iloc[:, 0]
            
        df = pd.DataFrame({'Port_Return': df_hist['Daily_Return'], 'Bench_Return': bench_returns}).dropna()
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                            subplot_titles=("Rolling Volatility (Annualized)", f"Rolling Beta (vs {bench_ticker})", 
                                            "Rolling Alpha (Annualized)", "Rolling Sharpe Ratio"))
        
        port_colors, bench_colors = [COLOR_PORT_MAIN, COLOR_ACCENT], [COLOR_BENCHMARK, '#f59e0b']
        for i, w in enumerate(windows):
            p_color, b_color = port_colors[i % len(port_colors)], bench_colors[i % len(bench_colors)]

            rolling_vol = df['Port_Return'].rolling(window=w).std() * np.sqrt(252)
            bench_vol = df['Bench_Return'].rolling(window=w).std() * np.sqrt(252)
            rolling_beta = df['Port_Return'].rolling(window=w).cov(df['Bench_Return']) / df['Bench_Return'].rolling(window=w).var()
            rolling_alpha = (df['Port_Return'].rolling(window=w).mean() - (rolling_beta * df['Bench_Return'].rolling(window=w).mean())) * 252 
            rolling_sharpe = (df['Port_Return'].rolling(window=w).mean() / df['Port_Return'].rolling(window=w).std()) * np.sqrt(252)
            bench_sharpe = (df['Bench_Return'].rolling(window=w).mean() / df['Bench_Return'].rolling(window=w).std()) * np.sqrt(252)
            
            fig.add_trace(go.Scatter(x=df.index, y=rolling_vol*100, mode='lines', name=f'Port Vol ({w}d)', line=dict(color=p_color, width=2), hovertemplate="Port Vol: %{y:.2f}%<extra></extra>"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=bench_vol*100, mode='lines', name=f'Bench Vol ({w}d)', line=dict(color=b_color, dash='dot', width=1.5), hovertemplate="Bench Vol: %{y:.2f}%<extra></extra>"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=rolling_beta, mode='lines', name=f'Beta ({w}d)', line=dict(color=p_color, width=2), hovertemplate="Beta: %{y:.2f}<extra></extra>"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=rolling_alpha*100, mode='lines', name=f'Alpha ({w}d)', line=dict(color=p_color, width=2), hovertemplate="Alpha: %{y:.2f}%<extra></extra>"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=rolling_sharpe, mode='lines', name=f'Port Sharpe ({w}d)', line=dict(color=p_color, width=2), hovertemplate="Port Sharpe: %{y:.2f}<extra></extra>"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=bench_sharpe, mode='lines', name=f'Bench Sharpe ({w}d)', line=dict(color=b_color, dash='dot', width=1.5), hovertemplate="Bench Sharpe: %{y:.2f}<extra></extra>"), row=4, col=1)
        
        fig.add_hline(y=1, line_dash="solid", line_color="#cbd5e1", row=2, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#cbd5e1", row=3, col=1)
        fig.add_hline(y=1, line_dash="solid", line_color="#cbd5e1", row=4, col=1)
        
        fig.update_layout(height=1000, template="plotly_white", showlegend=False, hovermode="x unified",
                          margin=dict(t=60, b=50, l=50, r=20), font=dict(family="Inter, sans-serif", size=11, color=COLOR_TEXT))
        fig.update_xaxes(title_text='Date', row=4, col=1)
        fig.update_yaxes(title_text="Volatility (%)", row=1, col=1)
        fig.update_yaxes(title_text="Beta", row=2, col=1)
        fig.update_yaxes(title_text="Alpha (%)", row=3, col=1)
        fig.update_yaxes(title_text="Sharpe Ratio", row=4, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        if show: fig.show()
        return fig

    def get_distribution_plot(self, show=False):
        """Creates a histogram of daily returns overlaid with a fitted normal distribution."""
        daily_ret = self.history_df['Daily_Return'].dropna() * 100
        mean_ret, std_ret = daily_ret.mean(), daily_ret.std()

        fig = go.Figure()
        fig.add_trace(go.Histogram(x=daily_ret, nbinsx=80, name='Daily Returns', marker_color='rgba(37, 99, 235, 0.6)', histnorm='probability density', hovertemplate="Range: %{x:.2f}%<br>Density: %{y:.4f}<extra></extra>"))
        
        x_range = np.linspace(daily_ret.min(), daily_ret.max(), 300)
        fig.add_trace(go.Scatter(x=x_range, y=(1/(std_ret*np.sqrt(2*np.pi)))*np.exp(-0.5*((x_range-mean_ret)/std_ret)**2), mode='lines', name='Normal Fit', line=dict(color='#D32F2F', width=2, dash='dash'), hovertemplate="Normal Fit: %{y:.4f}<extra></extra>"))

        var_95 = np.percentile(daily_ret, 5)
        fig.add_vline(x=var_95, line_dash="dash", line_color="#EF6C00", annotation_text=f"VaR 95%: {var_95:.2f}%", annotation_position="top right")
        
        tail = daily_ret[daily_ret <= var_95]
        if len(tail) > 0:
            fig.add_vline(x=tail.mean(), line_dash="dot", line_color="#B71C1C", annotation_text=f"CVaR 95%: {tail.mean():.2f}%", annotation_position="top left")

        fig.update_layout(template='plotly_white', title='Daily Return Distribution vs. Normal Fit', xaxis_title='Daily Return (%)', yaxis_title='Density', height=450, hovermode='x unified')
        if show: fig.show()
        return fig

    def get_correlation_heatmap(self, show=False):
        """Creates an annotated heatmap of pairwise correlations for currently held assets."""
        if not self.allocation_data: self.get_allocation()
        symbols = list(self.allocation_data['current_holdings'].keys())

        if len(symbols) < 2: return go.Figure().add_annotation(text="Need at least 2 holdings for correlation.", showarrow=False)

        returns_dict = {}
        for sym in symbols:
            if sym in self.tracker.market_data and not self.tracker.market_data[sym].empty:
                close = self.tracker.market_data[sym]['Close'].copy()
                if close.index.tz: close.index = close.index.tz_localize(None)
                returns_dict[sym] = close.pct_change().fillna(0)

        if len(returns_dict) < 2: return go.Figure().add_annotation(text="Insufficient price data for correlation.", showarrow=False)
        corr_matrix = pd.DataFrame(returns_dict).dropna().corr()

        fig = go.Figure(data=go.Heatmap(z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index, 
                                       text=corr_matrix.round(2).values, texttemplate='%{text}',
                                       colorscale=[[0, '#2563eb'], [0.5, '#ffffff'], [1, '#dc2626']], zmin=-1, zmax=1,
                                       hovertemplate="Asset 1: %{x}<br>Asset 2: %{y}<br>Correlation: %{z:.2f}<extra></extra>"))
        fig.update_layout(template='plotly_white', title='Pairwise Asset Correlation Matrix', xaxis_title='Asset', yaxis_title='Asset', height=max(450, 50 + len(symbols)*35), yaxis=dict(autorange='reversed'))
        if show: fig.show()
        return fig

    def get_beta_exposure_plot(self, show=False):
        if not self.allocation_data: self.get_allocation()
        holdings, values = self.allocation_data['current_holdings'], self.allocation_data['current_values']
        benchmark_symbol = config.METRICS_BENCHMARK
        symbols = list(holdings.keys())

        if not symbols: return go.Figure(), pd.DataFrame()

        try:
            bench_data = self.tracker.market_data.get(benchmark_symbol) or yf.Ticker(benchmark_symbol).history(period="1y")
            bench_ret = bench_data['Close'].pct_change().dropna()
            if bench_ret.index.tz: bench_ret.index = bench_ret.index.tz_localize(None)
        except: return go.Figure(), pd.DataFrame()

        returns_list, valid_syms = [], []
        for sym in symbols:
            if sym in self.tracker.market_data and not self.tracker.market_data[sym].empty:
                ret = self.tracker.market_data[sym]['Close'].pct_change().dropna()
                if ret.index.tz: ret.index = ret.index.tz_localize(None)
                returns_list.append(ret); valid_syms.append(sym)
        
        if not returns_list: return go.Figure(), pd.DataFrame()
        all_ret = pd.concat(returns_list + [bench_ret], axis=1, keys=valid_syms + ['BENCHMARK']).dropna()
        if len(all_ret) < 20: betas = {s: 1.0 for s in valid_syms}
        else:
            matrix = all_ret.cov()
            betas = (matrix.loc[valid_syms, 'BENCHMARK'] / matrix.loc['BENCHMARK', 'BENCHMARK']).to_dict()

        total_val = sum(values.values())
        rows = [{'Symbol': s, 'Beta': round(betas.get(s, 1.0), 2), 'Nominal ($)': values.get(s, 0),
                 'Nominal (%)': round((values.get(s, 0)/total_val)*100, 1),
                 'Beta-Adj ($)': values.get(s, 0)*betas.get(s, 1.0),
                 'Beta-Adj (%)': round((values.get(s, 0)*betas.get(s, 1.0)/total_val)*100, 1)} for s in valid_syms]
        df_beta = pd.DataFrame(rows).sort_values('Nominal ($)', ascending=True)

        fig = go.Figure()
        fig.add_trace(go.Bar(y=df_beta['Symbol'], x=df_beta['Nominal (%)'], name='Nominal %', 
                             orientation='h', marker_color='rgba(37, 99, 235, 0.7)',
                             customdata=df_beta['Beta'],
                             hovertemplate="<b>%{y}</b><br>Nominal: %{x}%<br>Beta: %{customdata}<extra></extra>"))
        fig.add_trace(go.Bar(y=df_beta['Symbol'], x=df_beta['Beta-Adj (%)'], name='Beta-Adj %', 
                             orientation='h', marker_color='rgba(220, 38, 38, 0.7)',
                             customdata=df_beta['Beta'],
                             hovertemplate="<b>%{y}</b><br>Beta-Adj: %{x}%<br>Beta: %{customdata}<extra></extra>"))
        fig.update_layout(template='plotly_white', title=f'Nominal vs. Beta Exposure ({benchmark_symbol})', xaxis_title='Exposure (%)', yaxis_title='Symbol', barmode='group', height=max(400, 60 + len(df_beta)*40))
        if show: fig.show()
        return fig, df_beta

    def get_factor_analysis_plot(self, show=False):
        df = self.history_df
        ff_df = fetch_fama_french_factors(df.index.min().strftime('%Y-%m-%d'), df.index.max().strftime('%Y-%m-%d'))
        if ff_df is None or ff_df.empty: return go.Figure().add_annotation(text="No FF data found for this period.", showarrow=False), {}

        # Align portfolio returns with factors
        aligned = pd.DataFrame({
            'Portfolio': df['Daily_Return'],
            'Mkt-RF': ff_df['Mkt-RF'],
            'SMB': ff_df['SMB'],
            'HML': ff_df['HML'],
            'RF': ff_df['RF']
        }).dropna()
        
        if len(aligned) < 30: return go.Figure().add_annotation(text="Insufficient data for factor analysis.", showarrow=False), {}

        y = (aligned['Portfolio'] - aligned['RF']).values
        X = np.column_stack([np.ones(len(aligned)), aligned[['Mkt-RF', 'SMB', 'HML']].values])

        # OLS
        betas, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_pred = X @ betas
        residuals = y - y_pred
        r_squared = 1 - (np.sum(residuals**2) / np.sum((y - y.mean())**2))
        
        # Significance
        mse = np.sum(residuals**2) / (len(y) - X.shape[1])
        vcv = mse * np.linalg.inv(X.T @ X)
        se = np.sqrt(np.diagonal(vcv))
        t_stats = betas / se
        p_values = [2 * (1 - stats.t.cdf(np.abs(t), df=len(y)-X.shape[1])) for t in t_stats]

        def get_stars(p):
            if p < 0.01: return "***"
            if p < 0.05: return "**"
            if p < 0.1: return "*"
            return ""

        results = {
            'alpha_annual': (1 + betas[0])**252 - 1, 'alpha_p_value': p_values[0],
            'mkt_beta': betas[1], 'mkt_p_value': p_values[1],
            'smb_beta': betas[2], 'smb_p_value': p_values[2],
            'hml_beta': betas[3], 'hml_p_value': p_values[3],
            'r_squared': r_squared, 'n_obs': len(y)
        }

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.6, 0.4],
            specs=[[{"type": "bar"}, {"type": "table"}]],
            subplot_titles=["Factor Exposure (Betas)", "Regression Summary"]
        )

        factors = ['Market (Mkt-RF)', 'Small Cap (SMB)', 'Value (HML)']
        beta_vals = betas[1:]
        stars = [get_stars(p) for p in p_values[1:]]
        
        fig.add_trace(go.Bar(
            x=factors, y=beta_vals, text=[f"{b:.3f}{s}" for b, s in zip(beta_vals, stars)],
            textposition='outside', marker_color=[COLOR_PORT_MAIN if b >= 0 else COLOR_NEGATIVE for b in beta_vals],
            hovertemplate="<b>%{x}</b><br>Beta: %{y:.3f}<extra></extra>"
        ), row=1, col=1)

        # Summary Table
        metrics_list = [
            ['Annualized Alpha', f"{results['alpha_annual']:.2%}{get_stars(p_values[0])}"],
            ['Market Beta', f"{results['mkt_beta']:.3f}{get_stars(p_values[1])}"],
            ['Size Beta (SMB)', f"{results['smb_beta']:.3f}{get_stars(p_values[2])}"],
            ['Value Beta (HML)', f"{results['hml_beta']:.3f}{get_stars(p_values[3])}"],
            ['R-Squared', f"{r_squared:.4f}"],
            ['Observations', f"{len(y)}"]
        ]

        fig.add_trace(go.Table(
            header=dict(values=['Metric', 'Value'], fill_color=COLOR_GRID, align='left', font=dict(size=12, color=COLOR_TEXT, family="Inter")),
            cells=dict(values=[[m[0] for m in metrics_list], [m[1] for m in metrics_list]], fill_color='white', align='left', font=dict(size=12, color=COLOR_TEXT, family="Inter"))
        ), row=1, col=2)

        fig.update_layout(template='plotly_white', height=400, margin=dict(t=50, b=30, l=20, r=20))
        fig.update_xaxes(title_text="Factor", row=1, col=1)
        fig.update_yaxes(title_text="Beta", row=1, col=1)
        if show: fig.show()
        return fig, results

    def get_summary_data(self, factor_results=None, mc_results=None, trade_results=None):
        """Aggregates all calculated metrics and allocation data into a structured dictionary."""
        if self.metrics is None: self.calculate_metrics()
        if self.allocation_data is None: self.get_allocation()
        
        m, a = self.metrics, self.allocation_data
        df = self.history_df
        
        # Get secondary currency rate if configured
        sec_curr = getattr(config, 'SECONDARY_CURRENCY', None)
        sec_rate = 1.0
        if sec_curr and sec_curr != config.BASE_CURRENCY:
            pair = f"{sec_curr}{config.BASE_CURRENCY}=X"
            if pair in self.tracker.market_data:
                sec_rate = self.tracker.market_data[pair]['Close'].iloc[-1]
            else:
                # Fallback to inverse if base->sec exists
                rev_pair = f"{config.BASE_CURRENCY}{sec_curr}=X"
                if rev_pair in self.tracker.market_data:
                    sec_rate = 1.0 / self.tracker.market_data[rev_pair]['Close'].iloc[-1]

        # Formatting helper
        def fmt_v(v, is_pct=False, is_neutral=False):
            if is_neutral:
                bold_style = 'color: #111827; font-weight: 700;'
            else:
                color = "#10b981" if v >= 0 else "#ef4444"
                bold_style = f'color: {color}; font-weight: 700;'

            if is_pct:
                return f'<span style="{bold_style}">{v:.2%}</span>'
            
            main_val = f'<span style="{bold_style}">{config.BASE_CURRENCY} {v:,.2f}</span>'
            if sec_curr and sec_curr != config.BASE_CURRENCY and sec_rate != 1.0:
                sec_v = v / sec_rate
                sec_text = f" <span style='font-size: 0.8em; color: #6b7280; font-weight: 400;'>| {sec_curr} {sec_v:,.2f}</span>"
                return f"{main_val}{sec_text}"
            
            return main_val
        # Composition strings
        sorted_cats = sorted(a['category_values'].items(), key=lambda x: x[1], reverse=True)
        asset_alloc_str = " | ".join([f"{k} {v/df['Total_Equity'].iloc[-1]:.1%}" for k, v in sorted_cats])
        
        top_sectors = sorted(a['sector_values'].items(), key=lambda x: x[1], reverse=True)[:3]
        sector_alloc_str = " | ".join([f"{k} {v/df['Total_Equity'].iloc[-1]:.1%}" for k, v in top_sectors])
        
        # Concentration
        sorted_holdings = sorted(a['current_values'].items(), key=lambda x: x[1], reverse=True)
        top_10_val = sum([x[1] for x in sorted_holdings[:10]])
        top_10_pct = top_10_val / df['Total_Equity'].iloc[-1]

        # Trade Analytics (restoring lost realized pnl and expectancy)
        expectancy = trade_results.get('expectancy', 0) if trade_results else 0
        realized_pnl = trade_results.get('total_realized_pnl', 0) if trade_results else 0

        summary = {
            "first_date": m['first_date'].strftime('%Y-%m-%d'),
            "current_date": datetime.now().strftime('%Y-%m-%d'),
            "current_base_currency": config.BASE_CURRENCY,
            "secondary_currency": sec_curr,
            "secondary_fx_rate": f"{1.0/sec_rate:.4f}" if sec_rate != 0 else "0.0000",
            "current_equity_html": fmt_v(df['Total_Equity'].iloc[-1], is_neutral=True),
            "current_market_value_html": fmt_v(df['Market_Value'].iloc[-1], is_neutral=True),
            "current_cash_html": fmt_v(df['Cash'].iloc[-1], is_neutral=True),
            
            # KPI Row
            "total_return_abs_html": fmt_v(df['PnL'].iloc[-1]),
            "total_return_pct_html": fmt_v(m['total_return'], is_pct=True),
            "total_cum_return_html": fmt_v(m['total_cum_return'], is_pct=True),
            "alpha_html": fmt_v(m['alpha'], is_pct=True),
            "portfolio_beta": f"{m['portfolio_beta']:.2f}",
            "max_drawdown": f"{m['max_drawdown']:.2%}",
            "volatility": f"{m['volatility']:.2%}",
            "benchmark_name": config.METRICS_BENCHMARK,
            
            # Stats & Ratios
            "sharpe_ratio": f"{m['sharpe_ratio']:.2f}",
            "benchmark_sharpe_ratio": f"{m['benchmark_sharpe_ratio']:.2f}",
            "sortino_ratio": f"{m['sortino_ratio']:.2f}",
            "benchmark_sortino_ratio": f"{m['benchmark_sortino_ratio']:.2f}",
            "calmar_ratio": f"{m['calmar_ratio']:.2f}" if not np.isnan(m['calmar_ratio']) else "N/A",
            "information_ratio": f"{m['information_ratio']:.2f}" if not np.isnan(m['information_ratio']) else "N/A",
            "treynor_ratio": f"{m['treynor_ratio']:.2f}" if not np.isnan(m['treynor_ratio']) else "N/A",
            "var_95_percent_return": f"{m['var_95_percent_return']:.2%}",
            "max_return_html": fmt_v(m['max_return']),
            "benchmark_total_return": f"{m['benchmark_return']:.2%}",
            
            # Risk Profile
            "skewness": f"{m['skewness']:.3f}",
            "kurtosis": f"{m['kurtosis']:.3f}",
            "cvar_95": f"{m['cvar_95']:.2%}",
            "ulcer_index": f"{m['ulcer_index']:.3f}",
            "avg_ttr": f"{m['avg_ttr']:.1f} days",
            "max_ttr": f"{m['max_ttr']:.0f} days",
            "expected_max_dd_95": f"{mc_results.get('expected_max_dd_95', 0):.2%}" if mc_results else "N/A",
            
            # Trade Analysis
            "total_trades": trade_results.get('total_trades', 0) if trade_results else 0,
            "win_rate": f"{trade_results.get('hit_rate', 0):.1%}" if trade_results else "0.0%",
            "profit_factor": f"{trade_results.get('profit_factor', 0):.2f}" if trade_results else "0.00",
            "expectancy": f"{config.BASE_CURRENCY} {expectancy:,.2f}" if trade_results else f"{config.BASE_CURRENCY} 0.00",
            "total_realized_pnl_html": fmt_v(realized_pnl),
            
            # Fama-French
            "ff_alpha": f"{factor_results.get('alpha_annual', 0):.2%}" if factor_results else "N/A",
            "ff_alpha_pval": f"{factor_results.get('alpha_p_value', 1):.4f}" if factor_results else "N/A",
            "ff_mkt_beta": f"{factor_results.get('mkt_beta', 0):.3f}" if factor_results else "N/A",
            "ff_smb": f"{factor_results.get('smb_beta', 0):.3f}" if factor_results else "N/A",
            "ff_hml": f"{factor_results.get('hml_beta', 0):.3f}" if factor_results else "N/A",
            "ff_r_squared": f"{factor_results.get('r_squared', 0):.4f}" if factor_results else "N/A",
            "mc_p_value": f"{mc_results.get('p_value', 1):.4f}" if mc_results else "N/A",
            
            # Composition
            "asset_alloc_str": asset_alloc_str,
            "sector_alloc_str": sector_alloc_str,
            "num_holdings": len(a['current_holdings']),
            "top_10_pct": f"{top_10_pct:.1%}"
        }
        return summary
