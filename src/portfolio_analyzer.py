import config

import pandas as pd 
import numpy as np 
from scipy import stats
from scipy.stats import skew, kurtosis as sp_kurtosis
import yfinance as yf 
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def calculate_performance_metrics(history_df):
    history_df['Prev_Equity'] = history_df['Total_Equity'].shift(1)
    
    history_df['Daily_Return'] = (
        (history_df['Total_Equity'] - history_df['Prev_Equity'] - history_df['Net_Flow']) / 
        (history_df['Prev_Equity'] + 0.5 * history_df['Net_Flow'])
    )
    history_df['Daily_Return'] = history_df['Daily_Return'].fillna(0)
    
    history_df['Daily_PnL'] = history_df['Total_Equity'] - history_df['Prev_Equity'] - history_df['Net_Flow']
    
    # Cumulative Returns
    history_df['Cumulative_Return'] = (1 + history_df['Daily_Return']).cumprod() - 1
    history_df['PnL'] = history_df['Total_Equity'] - history_df['Invested_Capital']
    total_cum_return = history_df['Cumulative_Return'].iloc[-1]
    max_return = max(history_df['PnL'])

    # Risk-Free Rate
    try:
        irx_ticker = yf.Ticker("^IRX")
        start_date_str = history_df.index.min().strftime('%Y-%m-%d')
        irx_hist = irx_ticker.history(start=start_date_str)['Close']
        irx_hist.index = irx_hist.index.tz_localize(None)
        
        history_df['Risk_Free_Rate_Annual'] = irx_hist / 100  # Convert percentage to decimal
        history_df['Risk_Free_Rate_Annual'] = history_df['Risk_Free_Rate_Annual'].ffill().fillna(0.04)
        
        history_df['Risk_Free_Rate_Daily'] = (1 + history_df['Risk_Free_Rate_Annual']) ** (1/365) - 1
        
    except Exception as e:
        print(f"Error fetching Risk Free Rate: {e}")
        history_df['Risk_Free_Rate_Daily'] = (1.04 ** (1/365)) - 1  # 4% annual, daily compounded
    
    # Benchmark & Beta
    try:
        benchmark_symbol = config.METRICS_BENCHMARK
        benchmark_ticker = yf.Ticker(benchmark_symbol)
        start_date_str = history_df.index.min().strftime('%Y-%m-%d')
        benchmark_hist = benchmark_ticker.history(start=start_date_str)['Close']
        benchmark_hist.index = benchmark_hist.index.tz_localize(None)
        benchmark_returns = benchmark_hist.pct_change().fillna(0)
        
        aligned_data = pd.DataFrame({
            'Portfolio': history_df['Daily_Return'],
            benchmark_symbol: benchmark_returns,
            'Risk_Free_Rate': history_df['Risk_Free_Rate_Daily']
        }, index=history_df.index).dropna()
        
        if len(aligned_data) > 10:
            beta, alpha, r_value, p_value, std_err = stats.linregress(
                aligned_data[benchmark_symbol], aligned_data['Portfolio']
            )
            portfolio_beta = beta
            
            benchmark_total_return = (1 + aligned_data[benchmark_symbol]).prod() - 1
            
            tracking_error = (aligned_data['Portfolio'] - aligned_data[benchmark_symbol]).std() * np.sqrt(252)
            
            down_market = aligned_data[aligned_data[benchmark_symbol] < 0]
            if len(down_market) > 5:  # Need enough down days
                portfolio_down_return = (1 + down_market['Portfolio']).prod() - 1
                benchmark_down_return = (1 + down_market[benchmark_symbol]).prod() - 1
                down_capture = portfolio_down_return / benchmark_down_return if benchmark_down_return != 0 else np.nan
            else:
                down_capture = np.nan

            up_market = aligned_data[aligned_data[benchmark_symbol] > 0]
            if len(up_market) > 5:
                portfolio_up_return = (1 + up_market['Portfolio']).prod() - 1
                benchmark_up_return = (1 + up_market[benchmark_symbol]).prod() - 1
                up_capture = portfolio_up_return / benchmark_up_return if benchmark_up_return != 0 else np.nan
            else:
                up_capture = np.nan

            excess_benchmark_returns = aligned_data[benchmark_symbol] - aligned_data['Risk_Free_Rate']
            if len(history_df) > 1 and aligned_data[benchmark_symbol].std() > 0:
                benchmark_sharpe_ratio = (excess_benchmark_returns.mean() * 252) / (aligned_data[benchmark_symbol].std() * np.sqrt(252))
            else:
                benchmark_sharpe_ratio = np.nan

            downside_benchmark_returns = aligned_data[benchmark_symbol][aligned_data[benchmark_symbol] < aligned_data['Risk_Free_Rate']]
            if len(downside_benchmark_returns) > 1 and downside_benchmark_returns.std() > 0:
                benchmark_sortino_ratio = (excess_benchmark_returns.mean() * 252) / (downside_benchmark_returns.std() * np.sqrt(252))
            else:
                benchmark_sortino_ratio = np.nan
                
        else:
            portfolio_beta = np.nan
            benchmark_total_return = np.nan
            tracking_error = np.nan
            down_capture = np.nan
            up_capture = np.nan
            
    except Exception as e:
        print(f"Error calculating Benchmark/Beta: {e}")
        portfolio_beta = np.nan
        benchmark_total_return = np.nan
        tracking_error = np.nan
        down_capture = np.nan
        up_capture = np.nan
    
    # Sharpe, Sortino, Alpha, Volatility, VaR
    
    # Sharpe Ratio
    excess_returns = history_df['Daily_Return'] - history_df['Risk_Free_Rate_Daily']
    if len(history_df) > 1 and history_df['Daily_Return'].std() > 0:
        sharpe_ratio = (excess_returns.mean() * 252) / (history_df['Daily_Return'].std() * np.sqrt(252))
    else:
        sharpe_ratio = np.nan

    # Sortino Ratio
    downside_returns = history_df['Daily_Return'][history_df['Daily_Return'] < history_df["Risk_Free_Rate_Daily"]] # Use risk free rate as minimum acceptable return (MAR)
    if len(downside_returns) > 1 and downside_returns.std() > 0:
        sortino_ratio = (excess_returns.mean() * 252) / (downside_returns.std() * np.sqrt(252))
    else:
        sortino_ratio = np.nan

    # Alpha
    if not np.isnan(portfolio_beta) and 'aligned_data' in locals() and len(aligned_data) > 10:
        # Geometric returns
        port_total_return = (1 + history_df['Daily_Return']).prod() - 1
        benchmark_total_return = (1 + aligned_data[benchmark_symbol]).prod() - 1
        rf_total_return = (1 + history_df['Risk_Free_Rate_Daily']).prod() - 1
        
        # Annualize
        n_days = len(history_df)
        port_return_annual = (1 + port_total_return) ** (252/n_days) - 1
        benchmark_return_annual = (1 + benchmark_total_return) ** (252/n_days) - 1
        rf_annual = (1 + rf_total_return) ** (252/n_days) - 1
        
        alpha = port_return_annual - (rf_annual + portfolio_beta * (benchmark_return_annual - rf_annual))
    else:
        alpha = np.nan
    
    # Volatility 
    volatility = history_df['Daily_Return'].std() * np.sqrt(252) if len(history_df) > 1 else 0
    
    # VaR (95%, 1-day) 
    if len(history_df) > 10:
        var_95_percent_return = np.percentile(history_df['Daily_Return'], 5)
        var_95_dollar = np.percentile(history_df['Daily_PnL'], 5)
        current_equity = history_df['Total_Equity'].iloc[-1]
    
    # Total Return and Max Drawdown
    if len(history_df) > 0:
        total_return = (history_df['Total_Equity'].iloc[-1] / history_df['Invested_Capital'].iloc[-1]) - 1
        rolling_max = history_df['Total_Equity'].cummax()
        drawdowns = (history_df['Total_Equity'] / rolling_max) - 1
        max_drawdown = drawdowns.min()
    else:
        total_return = 0
        max_drawdown = 0
    
    first_date = history_df.index[0]

    # --- Advanced Risk & Distribution Metrics ---
    daily_returns = history_df['Daily_Return'].dropna()

    # Skewness & Excess Kurtosis
    if len(daily_returns) > 3:
        return_skewness = skew(daily_returns, bias=False)
        return_kurtosis = sp_kurtosis(daily_returns, bias=False)  # Excess kurtosis (normal = 0)
    else:
        return_skewness = np.nan
        return_kurtosis = np.nan

    # Conditional VaR / Expected Shortfall (95%)
    if len(daily_returns) > 10:
        var_threshold = np.percentile(daily_returns, 5)
        tail_returns = daily_returns[daily_returns <= var_threshold]
        cvar_95 = tail_returns.mean() if len(tail_returns) > 0 else np.nan
    else:
        cvar_95 = np.nan
    
    # Ulcer Index
    if len(history_df) > 1:
        cum_returns = (1 + daily_returns).cumprod()
        running_peak = cum_returns.cummax()
        pct_drawdowns = ((cum_returns - running_peak) / running_peak) * 100  # in percent
        ulcer_index = np.sqrt((pct_drawdowns ** 2).mean())
    else:
        ulcer_index = np.nan
    
    # Time to Recovery (TTR)
    if len(history_df) > 1:
        equity = history_df['Total_Equity']
        eq_running_max = equity.cummax()
        is_in_drawdown = equity < eq_running_max
        
        recovery_days = []
        current_dd_start = None
        for i in range(len(is_in_drawdown)):
            if is_in_drawdown.iloc[i]:
                if current_dd_start is None:
                    current_dd_start = i
            else:
                if current_dd_start is not None:
                    recovery_days.append(i - current_dd_start)
                    current_dd_start = None
        # If still in drawdown at the end, record that too
        if current_dd_start is not None:
            recovery_days.append(len(is_in_drawdown) - current_dd_start)
        
        avg_ttr = np.mean(recovery_days) if recovery_days else 0
        max_ttr = max(recovery_days) if recovery_days else 0
    else:
        avg_ttr = 0
        max_ttr = 0

    return {
        'first_date': first_date,
        'sharpe_ratio': sharpe_ratio,
        'benchmark_sharpe_ratio': benchmark_sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'benchmark_sortino_ratio': benchmark_sortino_ratio,
        'portfolio_beta': portfolio_beta,
        'alpha': alpha,
        'volatility': volatility,
        'var_95_percent_return': var_95_percent_return,
        'var_95_dollar': var_95_dollar,
        'total_return': total_return,
        'max_return': max_return,
        'total_cum_return': total_cum_return,
        'max_drawdown': max_drawdown,
        'benchmark_return': benchmark_total_return if 'benchmark_total_return' in locals() else np.nan,
        'tracking_error': tracking_error if 'tracking_error' in locals() else np.nan,
        'down_capture': down_capture if 'down_capture' in locals() else np.nan,
        'up_capture': up_capture if 'up_capture' in locals() else np.nan,
        # Advanced Risk Metrics
        'skewness': return_skewness,
        'kurtosis': return_kurtosis,
        'cvar_95': cvar_95,
        'ulcer_index': ulcer_index,
        'avg_ttr': avg_ttr,
        'max_ttr': max_ttr,
    }

def get_pnl_plot(history_df, show = False):
    fig_pnl = go.Figure()

    # Add PnL line
    fig_pnl.add_trace(go.Scatter(
        x=history_df.index,
        y=history_df['PnL'],
        mode='lines',
        name='Total PnL',
        line=dict(color='black', width=1)
    ))

    # Add Green fill for Profit
    fig_pnl.add_trace(go.Scatter(
        x=history_df.index,
        y=history_df['PnL'].where(history_df['PnL'] >= 0, 0),
        mode='none',
        fill='tozeroy',
        fillcolor='rgba(0, 255, 0, 0.3)',
        name='Profit'
    ))

    # Add Red fill for Loss
    fig_pnl.add_trace(go.Scatter(
        x=history_df.index,
        y=history_df['PnL'].where(history_df['PnL'] < 0, 0),
        mode='none',
        fill='tozeroy',
        fillcolor='rgba(255, 0, 0, 0.3)',
        name='Loss'
    ))

    fig_pnl.update_layout(
        title='Interactive Total Profit/Loss Over Time',
        xaxis_title='Date',
        yaxis_title='PnL (USD)',
        hovermode='x unified',
        height=500
    )

    # Hide weekends on x-axis
    fig_pnl.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]) # hide weekends
        ]
    )
    
    if show:
        fig_pnl.show()
    
    return fig_pnl

def get_wealth_plot(history_df, show = False):
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08,
        row_heights=[0.6, 0.4], # Give more space to the main wealth chart
        subplot_titles=("Equity and Invested Capital Curve", "Total PnL")
    )
    
    # --- Graph 1 ---
    # Invested Capital 
    fig.add_trace(go.Scatter(
        x=history_df.index, 
        y=history_df['Invested_Capital'],
        mode='lines',
        name='Invested Capital',
        line=dict(color='#555555', width=1.5, dash='dash'), 
        legendgroup='group1'
    ), row=1, col=1)

    # Total Equity
    fig.add_trace(go.Scatter(
        x=history_df.index, 
        y=history_df['Total_Equity'],
        mode='lines',
        name='Total Equity',
        line=dict(color='#2E7D32', width=2), # Darker Green
        fill='tonexty', 
        fillcolor='rgba(46, 125, 50, 0.1)', # Matching transparent green
        legendgroup='group1'
    ), row=1, col=1)

    # --- Graph 2 ---
    fig.add_trace(go.Scatter(
        x=history_df.index, 
        y=history_df['PnL'],
        mode='lines',
        name='Net PnL',
        line=dict(color='#1976D2', width=2), # Strong Blue
        fill='tozeroy', 
        fillcolor='rgba(25, 118, 210, 0.1)', # Matching transparent blue
        legendgroup='group2'
    ), row=2, col=1)

    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
    
    # Layout
    fig.update_layout(
        template="plotly_white", # <--- SWITCHED TO LIGHT MODE
        hovermode="x unified",
        height=700,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05, 
            xanchor="right",
            x=1
        ),
    )

    fig.update_yaxes(title_text="Value ($)", showgrid=True, gridcolor='#E0E0E0', row=1, col=1)
    fig.update_yaxes(title_text="PnL ($)", showgrid=True, gridcolor='#E0E0E0', row=2, col=1)
    fig.update_xaxes(showgrid=True, gridcolor='#E0E0E0')
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]) # hide weekends
        ]
    )

    if show:
        fig.show()
        
    return fig

def get_returns_plot(history_df, show=False):
    benchmark_symbols = config.PLOT_BENCHMARK

    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08,
        subplot_titles=("Daily Return %", "Total Cumulative Return %"),
        row_heights=[0.5, 0.5]
    )

    # --- GRAPH 1: Daily Returns ---
    daily_colors = ['#00897B' if val >= 0 else '#D32F2F' for val in history_df['Daily_Return']]
    
    fig.add_trace(go.Bar(
        x=history_df.index, 
        y=history_df['Daily_Return'] * 100,
        name='Daily Return %',
        marker_color=daily_colors,
        hovertemplate='%{y:.2f}%',
        marker_line_width=0 
    ), row=1, col=1)

    # --- GRAPH 2: Cumulative Returns ---
    # Portfolio returns
    fig.add_trace(go.Scatter(
        x=history_df.index, 
        y=history_df['Cumulative_Return'] * 100,
        mode='lines',
        name='Total Portfolio Return %',
        line=dict(color='#0277BD', width=2), 
        fill='tozeroy', 
        fillcolor='rgba(2, 119, 189, 0.1)', 
        hovertemplate='%{y:.2f}%'
    ), row=2, col=1)

    # Benchmark returns
    start_date = history_df.index.min()
    end_date = history_df.index.max()

    benchmark_data = yf.download(benchmark_symbols, start=start_date, end=end_date + pd.Timedelta(days=1), progress=False, auto_adjust=True, group_by="column")["Close"]

    if isinstance(benchmark_data, pd.Series):
        benchmark_data = benchmark_data.to_frame(name=benchmark_symbols[0])

    colors = ["#B73352", '#EF6C00', '#8E24AA', '#558B2F']

    for i, ticker in enumerate(benchmark_symbols):
        if ticker in benchmark_data.columns:
            series = benchmark_data[ticker].dropna(axis=0)

            cum_return = (series / series.iloc[0]) - 1

            line_color = colors[i % len(colors)]

            fig.add_trace(go.Scatter(
                x=cum_return.index,
                y=cum_return * 100,
                mode='lines',
                name=f'{ticker} Return',
                line=dict(color=line_color, width=1.5, dash='solid'),
                hovertemplate=f'{ticker}: %{{y:.2f}}%'
            ), row=2, col=1)

    # --- Layout ---
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        height=650, 
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05, 
            xanchor="right",
            x=1
        ),
        bargap=0.05 
    )

    # Zero Lines & Grids
    fig.add_hline(y=0, line_dash="solid", line_color="#333", line_width=1, row=1, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="#333", line_width=1, row=2, col=1)

    fig.update_xaxes(showgrid=True, gridcolor='#E0E0E0')
    fig.update_yaxes(title_text="Daily %", showgrid=True, gridcolor='#E0E0E0', row=1, col=1)
    fig.update_yaxes(title_text="Total %", showgrid=True, gridcolor='#E0E0E0', row=2, col=1)
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]) # hide weekends
        ]
    )

    if show:
        fig.show()
        
    return fig

def get_drawdown_plot(history_df, show=False):
    # Calculate Cumulative Return peak (Running Max)
    # We use (1 + Daily_Return).cumprod() to ensure it's time-weighted/percentage-based
    cum_returns = (1 + history_df['Daily_Return']).cumprod()
    running_max = cum_returns.cummax()
    
    # Calculate Drawdown as a percentage: (Current / Peak) - 1
    drawdown_pct = (cum_returns / running_max) - 1

    fig_drawdown = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.1,
        subplot_titles=("Cumulative Return vs. Running High", "Drawdown (%)"),
        row_heights=[0.6, 0.4]
    )

    # --- PLOT 1: Cumulative vs Running Max ---
    # Running Max Line
    fig_drawdown.add_trace(go.Scatter(
        x=history_df.index, 
        y=(running_max - 1) * 100,  # <-- Adjusted here
        mode='lines',
        name='Peak Return',
        line=dict(color='rgba(0, 0, 0, 0.3)', width=1, dash='dot'),
        hovertemplate='Peak: %{y:.2f}%'
    ), row=1, col=1)

    # Cumulative Return Line
    fig_drawdown.add_trace(go.Scatter(
        x=history_df.index, 
        y=(cum_returns - 1) * 100,  # <-- Adjusted here
        mode='lines',
        name='Cumulative Return',
        line=dict(color='#0277BD', width=2),
        fill='tonexty',
        fillcolor='rgba(211, 47, 47, 0.2)',
        hovertemplate='Return: %{y:.2f}%'
    ), row=1, col=1)

    # --- PLOT 2: Percentage Drawdown (Underwater) ---
    fig_drawdown.add_trace(go.Scatter(
        x=history_df.index, 
        y=drawdown_pct * 100,
        mode='lines',
        name='Drawdown %',
        line=dict(color='#D32F2F', width=1.5),
        fill='tozeroy',
        fillcolor='rgba(211, 47, 47, 0.3)',
        hovertemplate='Drawdown: %{y:.2f}%'
    ), row=2, col=1)

    # Layout Adjustments
    fig_drawdown.update_layout(
        template="plotly_white",
        height=600,
        showlegend=True,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    fig_drawdown.update_yaxes(title_text="Return %", row=1, col=1)
    fig_drawdown.update_yaxes(title_text="Drawdown %", row=2, col=1)
    
    # Hide weekends
    fig_drawdown.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    if show:
        fig_drawdown.show()
        
    return fig_drawdown

def get_allocation(history_df, trades_df, portfolio_tracker, show=False):
    last_holdings = {}

    for sym in portfolio_tracker.symbols:
        buys = trades_df[(trades_df['SYMBOL'] == sym) & (trades_df['BUY/SELL'] == 'BUY')]['QTY'].sum()
        sells = trades_df[(trades_df['SYMBOL'] == sym) & (trades_df['BUY/SELL'] == 'SELL')]['QTY'].sum()
        last_holdings[sym] = buys - sells

    current_holdings = {k: v for k, v in last_holdings.items() if v > 0}
    current_values = {}

    for sym, qty in current_holdings.items():
        if sym in portfolio_tracker.market_data and not portfolio_tracker.market_data[sym].empty:
            price = portfolio_tracker.market_data[sym].iloc[-1]['Close']
            current_values[sym] = qty * price

    # Add Cash
    current_cash = history_df['Cash'].iloc[-1]
    if current_cash > 0:
        current_values['CASH'] = current_cash

    # Categorize Assets
    asset_categories = {}
    asset_sectors = {}

    # Split Broad Market into US and International
    US_BROAD_MARKET = ['VOO', 'VTI', 'SPY', 'IVV', 'QQQ', 'IWM', 'QQQM', 'SPYM']
    INTL_EQUITY = ['VEU', 'VXUS', 'EFA']

    for sym in current_values.keys():
        if sym == 'CASH':
            asset_categories[sym] = 'Cash & Equivalents'
            asset_sectors[sym] = 'Cash'
            continue

        # Manual fix wrong category and sector
        if sym == 'SPYM':
            asset_categories[sym] = 'US Broad Market'
            asset_sectors[sym] = 'US Broad Market'
            continue

        info = portfolio_tracker.asset_info.get(sym, {})
        quote_type = info.get('quoteType', 'UNKNOWN')
        sector = info.get('sector', 'Unknown')
        long_name = info.get('longName', '').lower()
        
        if quote_type == 'ETF':
            if sym in US_BROAD_MARKET:
                category = 'US Broad Market'
            elif sym in INTL_EQUITY:
                category = 'International Equity'
            elif any(x in long_name for x in ['treasury', 'gov', 'bills', 'sovereign']):
                category = 'Treasury Bonds'
            elif any(x in long_name for x in ['corporate', 'credit', 'high yield']):
                category = 'Corporate Bonds'
            elif any(x in long_name for x in ['bond', 'fixed income']):
                category = 'Other Fixed Income'
            elif any(x in long_name for x in ['gold', 'silver', 'commodity', 'metal']):
                category = 'Commodities'
            else:
                category = 'Equity ETF (Other)'
        elif quote_type == 'EQUITY':
            if sector != 'Unknown':
                category = f"{sector} Stocks"
            else:
                category = 'Individual Stocks'
        else:
            category = 'Other'
            
        asset_categories[sym] = category
        asset_sectors[sym] = sector if sector != 'Unknown' else category

    # Group by Category
    category_values = {}
    for sym, val in current_values.items():
        cat = asset_categories.get(sym, 'Other')
        category_values[cat] = category_values.get(cat, 0) + val

    # Group by Sector 
    sector_values = {}
    for sym, val in current_values.items():
        sec = asset_sectors.get(sym, 'Other')
        sector_values[sec] = sector_values.get(sec, 0) + val
        

    # Create & Format Allocation DataFrame
    data_rows = []
    total_portfolio_value = sum(current_values.values())

    for sym, val in current_values.items():
        data_rows.append({
            'Symbol': sym,
            'Category': asset_categories.get(sym, 'Other'),
            'Sector': asset_sectors.get(sym, 'Other'),
            'Value': val,
            'Allocation (%)': (val / total_portfolio_value) * 100
        })

    df_allocation = pd.DataFrame(data_rows)
    df_allocation = df_allocation.sort_values(by='Value', ascending=False).reset_index(drop=True)

    # Visualization (Pie Charts)
    df_by_category = df_allocation.groupby('Category')['Value'].sum().reset_index()

    fig_alloc = make_subplots(
        rows=1, cols=2, 
        specs=[[{'type':'domain'}, {'type':'domain'}]],
        subplot_titles=['Allocation by Symbol', 'Allocation by Asset Class'],
    )

    # Pie 1: By Symbol
    fig_alloc.add_trace(go.Pie(
        labels=df_allocation['Symbol'], 
        values=df_allocation['Value'], 
        name="Symbol",
        textinfo='label+percent',
        hoverinfo='label+value+percent',
        insidetextorientation='radial',
        textposition='inside', 
    ), 1, 1)

    # Pie 2: By Asset Class
    fig_alloc.add_trace(go.Pie(
        labels=df_by_category['Category'], 
        values=df_by_category['Value'], 
        name="Asset Class",
        textinfo='label+percent',
        hoverinfo='label+value+percent',
        insidetextorientation='radial',
        textposition='inside', 
    ), 1, 2)
    
    fig_alloc.update_layout(
        title_text=f"Portfolio Allocation (Total: ${total_portfolio_value:,.2f})",
        uniformtext_minsize=10, 
        uniformtext_mode='hide', # Hides labels on tiny slices so they don't overlap
        margin=dict(t=50, b=40, l=20, r=20), # Reduce margins so the pie is larger
        showlegend=False,
        legend=dict(
            orientation="h",     # Horizontal legend
            yanchor="bottom",
            y=-0.2,              # Push legend below the chart
            xanchor="center",
            x=0.5
        )
    )

    # Display DataFrame
    df_alloc = df_allocation.copy()
    df_alloc['Value'] = df_alloc['Value'].apply(lambda x: f"${x:,.2f}")
    df_alloc['Allocation (%)'] = df_alloc['Allocation (%)'].apply(lambda x: f"{x:.2f}%")

    if show:
        fig_alloc.show()

    return fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings

def get_quant_plots(history_df, show=False, windows=[21, 63]):
    # Fetch benchmark data to align with portfolio history
    start_date = history_df.index.min().strftime('%Y-%m-%d')
    end_date = (history_df.index.max() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    bench_ticker = config.METRICS_BENCHMARK
    
    # Download benchmark data
    bench_data = yf.download(bench_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
    bench_returns = bench_data['Close'].pct_change().fillna(0)
    
    # Handle multi-index columns if yfinance returns them
    if isinstance(bench_returns, pd.DataFrame):
        bench_returns = bench_returns.iloc[:, 0]
        
    # Align dates between portfolio and benchmark
    df = pd.DataFrame({
        'Port_Return': history_df['Daily_Return'],
        'Bench_Return': bench_returns
    }).dropna()
    
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("Rolling Volatility (Annualized)", 
                        f"Rolling Beta (vs {bench_ticker})", 
                        "Rolling Alpha (Annualized)",
                        "Rolling Sharpe Ratio")
    )
    
    # Define 8 colors in total (4 for Portfolio, 4 for Benchmark)
    # Using distinct complementary/contrasting palettes
    port_colors = ['#0277BD', '#2E7D32', '#8E24AA', '#F9A825'] # Blue, Green, Purple, Yellow
    bench_colors = ['#D32F2F', "#E619C0", '#795548', '#546E7A'] # Red, Orange, Brown, Blue-Grey
    
    for i, w in enumerate(windows):
        # Determine colors for this window using modulo 4
        p_color = port_colors[i % 4]
        b_color = bench_colors[i % 4]

        # 1. Rolling Volatility (Annualized)
        rolling_vol = df['Port_Return'].rolling(window=w).std() * np.sqrt(252)
        bench_vol = df['Bench_Return'].rolling(window=w).std() * np.sqrt(252)
        
        # 2. Rolling Beta
        rolling_cov = df['Port_Return'].rolling(window=w).cov(df['Bench_Return'])
        rolling_var = df['Bench_Return'].rolling(window=w).var()
        rolling_beta = rolling_cov / rolling_var
        
        # 3. Rolling Alpha (Annualized approximation)
        rolling_alpha_daily = df['Port_Return'].rolling(window=w).mean() - (rolling_beta * df['Bench_Return'].rolling(window=w).mean())
        rolling_alpha = rolling_alpha_daily * 252 
        
        # 4. Rolling Sharpe Ratio (Annualized, assuming Rf = 0)
        rolling_sharpe = (df['Port_Return'].rolling(window=w).mean() / df['Port_Return'].rolling(window=w).std()) * np.sqrt(252)
        bench_sharpe = (df['Bench_Return'].rolling(window=w).mean() / df['Bench_Return'].rolling(window=w).std()) * np.sqrt(252)
        
        # --- Add Traces ---
        
        # Plot Volatility
        fig.add_trace(go.Scatter(x=df.index, y=rolling_vol*100, mode='lines', name=f'Port Vol ({w}d)', line=dict(color=p_color)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bench_vol*100, mode='lines', name=f'{bench_ticker} Vol ({w}d)', line=dict(color=b_color, dash='dot', width=1)), row=1, col=1)
        
        # Plot Beta (Uses Portfolio Color)
        fig.add_trace(go.Scatter(x=df.index, y=rolling_beta, mode='lines', name=f'Beta ({w}d)', line=dict(color=p_color)), row=2, col=1)
        
        # Plot Alpha (Uses Portfolio Color)
        fig.add_trace(go.Scatter(x=df.index, y=rolling_alpha*100, mode='lines', name=f'Alpha ({w}d)', line=dict(color=p_color)), row=3, col=1)
        
        # Plot Sharpe
        fig.add_trace(go.Scatter(x=df.index, y=rolling_sharpe, mode='lines', name=f'Port Sharpe ({w}d)', line=dict(color=p_color)), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bench_sharpe, mode='lines', name=f'{bench_ticker} Sharpe ({w}d)', line=dict(color=b_color, dash='dot', width=1)), row=4, col=1)
    
    # Reference Lines 
    fig.add_hline(y=1, line_dash="dash", line_color="black", opacity=0.5, row=2, col=1) # Beta of 1
    fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=3, col=1) # Zero Alpha
    fig.add_hline(y=1, line_dash="dash", line_color="black", opacity=0.5, row=4, col=1) # Sharpe of 1.0
    
    fig.update_layout(
        height=1000, 
        template="plotly_white", 
        showlegend=False, 
        hovermode="x unified",
        margin=dict(t=50, b=50, l=50, r=50)
    )
    
    fig.update_yaxes(title_text="Volatility (%)", row=1, col=1)
    fig.update_yaxes(title_text="Beta", row=2, col=1)
    fig.update_yaxes(title_text="Alpha (%)", row=3, col=1)
    fig.update_yaxes(title_text="Sharpe", row=4, col=1)
    
    # Hide weekends
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    if show:
        fig.show()
        
    return fig

def get_distribution_plot(history_df, show=False):
    """Creates a histogram of daily returns overlaid with a fitted normal distribution,
    annotated with VaR and CVaR thresholds."""
    daily_returns = history_df['Daily_Return'].dropna() * 100  # Convert to percent

    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std()

    fig = go.Figure()

    # Histogram of actual returns
    fig.add_trace(go.Histogram(
        x=daily_returns,
        nbinsx=80,
        name='Daily Returns',
        marker_color='rgba(37, 99, 235, 0.6)',
        marker_line=dict(color='rgba(37, 99, 235, 0.9)', width=0.5),
        histnorm='probability density',
        hovertemplate='Return: %{x:.2f}%<br>Density: %{y:.4f}'
    ))

    # Fitted Normal Distribution curve
    x_range = np.linspace(daily_returns.min(), daily_returns.max(), 300)
    normal_pdf = (1 / (std_ret * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_range - mean_ret) / std_ret) ** 2)

    fig.add_trace(go.Scatter(
        x=x_range,
        y=normal_pdf,
        mode='lines',
        name=f'Normal (μ={mean_ret:.3f}%, σ={std_ret:.3f}%)',
        line=dict(color='#D32F2F', width=2, dash='dash')
    ))

    # VaR (95%) vertical line
    var_95 = np.percentile(daily_returns, 5)
    fig.add_vline(
        x=var_95, line_dash="dash", line_color="#EF6C00", line_width=2,
        annotation_text=f"VaR 95%: {var_95:.2f}%",
        annotation_position="top right",
        annotation_font=dict(color="#EF6C00", size=11)
    )

    # CVaR (Expected Shortfall) vertical line
    tail = daily_returns[daily_returns <= var_95]
    if len(tail) > 0:
        cvar = tail.mean()
        fig.add_vline(
            x=cvar, line_dash="dot", line_color="#B71C1C", line_width=2,
            annotation_text=f"CVaR 95%: {cvar:.2f}%",
            annotation_position="top left",
            annotation_font=dict(color="#B71C1C", size=11)
        )

    fig.update_layout(
        template='plotly_white',
        title='Daily Return Distribution vs. Normal Fit',
        xaxis_title='Daily Return (%)',
        yaxis_title='Probability Density',
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=450,
        hovermode='x unified',
        margin=dict(t=80, b=50, l=50, r=30)
    )

    if show:
        fig.show()

    return fig

def get_correlation_heatmap(portfolio_tracker, current_holdings, show=False):
    """Creates an annotated heatmap of pairwise correlations for all currently held assets."""
    symbols = [s for s in current_holdings.keys() if s != 'CASH']

    if len(symbols) < 2:
        # Need at least 2 assets for a correlation matrix
        fig = go.Figure()
        fig.add_annotation(text="Need at least 2 holdings for correlation analysis.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig

    # Build a DataFrame of daily returns for each held asset
    returns_dict = {}
    for sym in symbols:
        if sym in portfolio_tracker.market_data and not portfolio_tracker.market_data[sym].empty:
            close = portfolio_tracker.market_data[sym]['Close'].copy()
            if close.index.tz is not None:
                close.index = close.index.tz_localize(None)
            returns_dict[sym] = close.pct_change().fillna(0)

    if len(returns_dict) < 2:
        fig = go.Figure()
        fig.add_annotation(text="Insufficient price data for correlation analysis.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig

    df_returns = pd.DataFrame(returns_dict).dropna()
    corr_matrix = df_returns.corr()

    # Round for display
    corr_text = corr_matrix.round(2).values.tolist()

    # Color scale: blue (negative) -> white (zero) -> red (positive)
    colorscale = [
        [0.0, '#2563eb'],   # Strong negative = blue
        [0.5, '#ffffff'],   # Zero = white
        [1.0, '#dc2626'],   # Strong positive = red
    ]

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        text=corr_text,
        texttemplate='%{text}',
        textfont=dict(size=11),
        colorscale=colorscale,
        zmin=-1, zmax=1,
        colorbar=dict(title='Correlation', thickness=15, len=0.75),
        hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>'
    ))

    fig.update_layout(
        template='plotly_white',
        title='Pairwise Asset Correlation Matrix',
        height=max(450, 50 + len(symbols) * 35),
        margin=dict(t=60, b=60, l=80, r=40),
        xaxis=dict(side='bottom', tickangle=-45),
        yaxis=dict(autorange='reversed'),
    )

    if show:
        fig.show()

    return fig

def get_beta_exposure_plot(portfolio_tracker, current_holdings, current_values, show=False):
    """Calculates individual asset betas and shows a side-by-side comparison of
    nominal (dollar) allocation vs. beta-adjusted exposure."""
    benchmark_symbol = config.METRICS_BENCHMARK
    symbols = [s for s in current_holdings.keys() if s != 'CASH']

    if not symbols:
        fig = go.Figure()
        fig.add_annotation(text="No equity holdings for beta analysis.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig

    # Get benchmark returns
    try:
        bench_data = portfolio_tracker.market_data.get(benchmark_symbol)
        if bench_data is None or bench_data.empty:
            bench_ticker = yf.Ticker(benchmark_symbol)
            bench_data = bench_ticker.history(period="1y")
        bench_returns = bench_data['Close'].pct_change().dropna()
        if bench_returns.index.tz is not None:
            bench_returns.index = bench_returns.index.tz_localize(None)
    except Exception:
        fig = go.Figure()
        fig.add_annotation(text=f"Could not fetch {benchmark_symbol} data for beta calculation.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig

    rows = []
    total_portfolio_value = sum(current_values.values())

    for sym in symbols:
        if sym not in portfolio_tracker.market_data or portfolio_tracker.market_data[sym].empty:
            continue

        asset_returns = portfolio_tracker.market_data[sym]['Close'].pct_change().dropna()
        if asset_returns.index.tz is not None:
            asset_returns.index = asset_returns.index.tz_localize(None)

        # Align dates
        aligned = pd.DataFrame({
            'asset': asset_returns,
            'bench': bench_returns
        }).dropna()

        if len(aligned) < 20:
            beta = 1.0  # Default to market beta if insufficient data
        else:
            beta_val, _, _, _, _ = stats.linregress(aligned['bench'], aligned['asset'])
            beta = beta_val

        nominal_val = current_values.get(sym, 0)
        beta_adj_val = nominal_val * beta
        nominal_pct = (nominal_val / total_portfolio_value) * 100
        beta_adj_pct = (beta_adj_val / total_portfolio_value) * 100

        rows.append({
            'Symbol': sym,
            'Beta': round(beta, 2),
            'Nominal ($)': nominal_val,
            'Nominal (%)': round(nominal_pct, 1),
            'Beta-Adj ($)': beta_adj_val,
            'Beta-Adj (%)': round(beta_adj_pct, 1),
        })

    if not rows:
        fig = go.Figure()
        fig.update_layout(template='plotly_white', height=400)
        return fig

    df_beta = pd.DataFrame(rows).sort_values('Nominal ($)', ascending=True)

    fig = go.Figure()

    # Nominal allocation bars
    fig.add_trace(go.Bar(
        y=df_beta['Symbol'],
        x=df_beta['Nominal (%)'],
        name='Nominal Allocation (%)',
        orientation='h',
        marker_color='rgba(37, 99, 235, 0.7)',
        text=df_beta['Nominal (%)'].apply(lambda x: f'{x:.1f}%'),
        textposition='outside',
        hovertemplate='%{y}<br>Nominal: %{x:.1f}%<extra></extra>'
    ))

    # Beta-adjusted exposure bars
    fig.add_trace(go.Bar(
        y=df_beta['Symbol'],
        x=df_beta['Beta-Adj (%)'],
        name='Beta-Adjusted Exposure (%)',
        orientation='h',
        marker_color='rgba(220, 38, 38, 0.7)',
        text=df_beta.apply(lambda r: f'{r["Beta-Adj (%)"]:.1f}% (β={r["Beta"]:.2f})', axis=1),
        textposition='outside',
        hovertemplate='%{y}<br>Beta-Adj: %{x:.1f}%<extra></extra>'
    ))

    fig.update_layout(
        template='plotly_white',
        title=f'Nominal vs. Beta-Adjusted Exposure (Benchmark: {benchmark_symbol})',
        xaxis_title='Portfolio Weight (%)',
        barmode='group',
        height=max(400, 60 + len(df_beta) * 40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(t=80, b=50, l=80, r=100),
        bargap=0.25,
    )

    if show:
        fig.show()

    return fig, df_beta

def fetch_fama_french_factors(start_date, end_date):
    """Fetches Fama-French 3-Factor daily data directly from Kenneth French's Data Library."""
    import urllib.request
    import zipfile
    import io

    # URL to the daily 3-factor dataset
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
    
    try:
        # Download and read zip file in memory
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                # Get the first (and usually only) CSV file
                filename = z.namelist()[0]
                with z.open(filename) as f:
                    content = f.read().decode('utf-8')
        
        # Parse the CSV text
        lines = content.split('\n')
        
        # Find start of data (skip header info)
        start_idx = 0
        for i, line in enumerate(lines):
            if line.startswith(',Mkt-RF'):
                start_idx = i
                break
                
        # Find end of data (stop before annual data or empty lines)
        end_idx = start_idx + 1
        for i, line in enumerate(lines[start_idx+1:]):
            if not line.strip() or len(line.split(',')[0]) != 8:  # 8 digits for YYYYMMDD
                end_idx = start_idx + 1 + i
                break
                
        # Reconstruct valid CSV data
        csv_data = "\n".join(lines[start_idx:end_idx])
        
        # Load into DataFrame
        ff_df = pd.read_csv(io.StringIO(csv_data), index_col=0)
        
        # Clean index (YYYYMMDD string -> Datetime)
        ff_df.index = pd.to_datetime(ff_df.index.astype(str), format='%Y%m%d')
        
        # Clean column names (strip whitespace)
        ff_df.columns = ff_df.columns.str.strip()
        
        # Convert values to float and from percentage to decimal
        for col in ff_df.columns:
            ff_df[col] = pd.to_numeric(ff_df[col], errors='coerce') / 100.0
            
        # Filter to requested date range
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        ff_df = ff_df[(ff_df.index >= start) & (ff_df.index <= end)]
        
        return ff_df
    except Exception as e:
        print(f"⚠️  Error fetching Fama-French factors: {e}")
        return None

def get_factor_analysis_plot(history_df, show=False):
    """Runs a Fama-French 3-factor OLS regression and produces a combined visualization
    with a factor loadings bar chart and a regression summary table."""

    start_date = history_df.index.min().strftime('%Y-%m-%d')
    end_date = history_df.index.max().strftime('%Y-%m-%d')

    ff_df = fetch_fama_french_factors(start_date, end_date)
    if ff_df is None or ff_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Could not retrieve Fama-French factor data.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig, {}

    # Align portfolio returns with factor data
    port_returns = history_df['Daily_Return'].copy()
    port_returns.index = pd.to_datetime(port_returns.index)

    aligned = pd.DataFrame({
        'Portfolio': port_returns,
        'Mkt-RF': ff_df['Mkt-RF'],
        'SMB': ff_df['SMB'],
        'HML': ff_df['HML'],
        'RF': ff_df['RF']
    }).dropna()

    if len(aligned) < 30:
        fig = go.Figure()
        fig.add_annotation(text="Insufficient overlapping data for factor regression (need 30+ days).",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig, {}

    # Dependent variable: Portfolio excess returns
    y = (aligned['Portfolio'] - aligned['RF']).values
    # Independent variables: Mkt-RF, SMB, HML (with intercept)
    X = aligned[['Mkt-RF', 'SMB', 'HML']].values
    X_with_const = np.column_stack([np.ones(len(X)), X])  # Add intercept column

    # OLS via numpy: beta = (X'X)^-1 X'y
    try:
        betas, residuals, rank, sv = np.linalg.lstsq(X_with_const, y, rcond=None)
    except np.linalg.LinAlgError:
        fig = go.Figure()
        fig.add_annotation(text="Factor regression failed (singular matrix).",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig, {}

    alpha_daily = betas[0]
    mkt_beta = betas[1]
    smb_beta = betas[2]
    hml_beta = betas[3]

    # Calculate R-squared
    y_pred = X_with_const @ betas
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Calculate standard errors and t-statistics
    n = len(y)
    k = X_with_const.shape[1]
    mse = ss_res / (n - k) if n > k else ss_res
    var_beta = mse * np.linalg.inv(X_with_const.T @ X_with_const).diagonal()
    se = np.sqrt(np.abs(var_beta))
    t_stats = betas / se
    # p-values (two-tailed) using scipy.stats.t distribution
    from scipy.stats import t as t_dist
    p_values = 2 * (1 - t_dist.cdf(np.abs(t_stats), df=n - k))

    # Annualize alpha
    alpha_annual = (1 + alpha_daily) ** 252 - 1

    factor_results = {
        'alpha_daily': alpha_daily,
        'alpha_annual': alpha_annual,
        'alpha_p_value': p_values[0],
        'mkt_beta': mkt_beta,
        'mkt_p_value': p_values[1],
        'smb_beta': smb_beta,
        'smb_p_value': p_values[2],
        'hml_beta': hml_beta,
        'hml_p_value': p_values[3],
        'r_squared': r_squared,
        'n_obs': n,
    }

    # --- Visualization ---
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.55, 0.45],
        specs=[[{"type": "bar"}, {"type": "table"}]],
        subplot_titles=["Factor Loadings (Betas)", "Regression Summary"]
    )

    # Bar chart of factor loadings
    factor_names = ['Mkt-RF (β₁)', 'SMB (β₂)', 'HML (β₃)']
    factor_betas = [mkt_beta, smb_beta, hml_beta]
    factor_pvals = [p_values[1], p_values[2], p_values[3]]
    bar_colors = ['#2563eb' if b >= 0 else '#dc2626' for b in factor_betas]

    # Add significance stars
    def sig_stars(p):
        if p < 0.001: return '***'
        if p < 0.01: return '**'
        if p < 0.05: return '*'
        return ''

    bar_text = [f'{b:.3f}{sig_stars(p)}' for b, p in zip(factor_betas, factor_pvals)]

    fig.add_trace(go.Bar(
        x=factor_names,
        y=factor_betas,
        marker_color=bar_colors,
        text=bar_text,
        textposition='outside',
        textfont=dict(size=13, weight='bold' ),
        hovertemplate='%{x}<br>Beta: %{y:.4f}<extra></extra>',
        showlegend=False,
    ), row=1, col=1)

    fig.add_hline(y=0, line_dash="solid", line_color="#333", line_width=1, row=1, col=1)
    fig.add_hline(y=1, line_dash="dash", line_color="#999", line_width=1, row=1, col=1)

    # Summary table
    def fmt_p(p):
        stars = sig_stars(p)
        return f'{p:.4f} {stars}'

    table_header = ['Metric', 'Value']
    table_cells = [
        ['FF Alpha (Ann.)', f'{alpha_annual:.2%}'],
        ['Alpha p-value', fmt_p(p_values[0])],
        ['Mkt-RF (β₁)', f'{mkt_beta:.4f}'],
        ['SMB (β₂)', f'{smb_beta:.4f}'],
        ['HML (β₃)', f'{hml_beta:.4f}'],
        ['R²', f'{r_squared:.4f}'],
        ['Observations', f'{n}'],
    ]

    fig.add_trace(go.Table(
        header=dict(
            values=table_header,
            fill_color='#f9fafb',
            align='left',
            font=dict(size=13, color='#374151', weight='bold'),
            line_color='#e5e7eb',
            height=32
        ),
        cells=dict(
            values=[[r[0] for r in table_cells], [r[1] for r in table_cells]],
            fill_color=[['white'] * len(table_cells)],
            align='left',
            font=dict(size=13, color='#111827'),
            line_color='#e5e7eb',
            height=30
        )
    ), row=1, col=2)

    fig.update_layout(
        template='plotly_white',
        height=420,
        margin=dict(t=50, b=40, l=50, r=30),
        showlegend=False,
    )

    fig.update_yaxes(title_text='Factor Loading', row=1, col=1)

    if show:
        fig.show()

    return fig, factor_results

def get_summary_sheet(history_df, category_values, sector_values, current_values, current_holdings, factor_results=None):
    # Fetch HKD Rate
    try:
        hkd_ticker = yf.Ticker("HKD=X")
        hkd_rate = hkd_ticker.history(period="1d")['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching HKD rate: {e}")
        hkd_rate = 7.78  

    current_equity = history_df['Total_Equity'].iloc[-1]
    current_market_value = history_df['Market_Value'].iloc[-1]
    current_cash = history_df['Cash'].iloc[-1]
    total_return_abs = history_df['PnL'].iloc[-1]

    if 'metrics' not in locals():
        metrics = calculate_performance_metrics(history_df)

    first_date = metrics.get('first_date', 0)
    total_return = metrics.get('total_return', 0)
    total_cum_return = metrics.get('total_cum_return', 0)
    max_return = metrics.get('max_return', 0)
    benchmark_total_return = metrics.get('benchmark_return', 0)
    alpha = metrics.get('alpha', 0)
    volatility = metrics.get('volatility', 0)
    sharpe_ratio = metrics.get('sharpe_ratio', 0)
    benchmark_sharpe_ratio = metrics.get('benchmark_sharpe_ratio', 0)
    sortino_ratio = metrics.get('sortino_ratio', 0)
    benchmark_sortino_ratio = metrics.get('benchmark_sortino_ratio', 0)
    portfolio_beta = metrics.get('portfolio_beta', 0)
    tracking_error = metrics.get('tracking_error', 0)
    max_drawdown = metrics.get('max_drawdown', 0)
    var_95_dollar = metrics.get('var_95_dollar', 0)
    var_95_percent_return = metrics.get('var_95_percent_return',0)
    down_capture = metrics.get('down_capture', 0)
    up_capture = metrics.get('up_capture', 0)
    skewness = metrics.get('skewness', np.nan)
    kurtosis_val = metrics.get('kurtosis', np.nan)
    cvar_95 = metrics.get('cvar_95', np.nan)
    ulcer_index = metrics.get('ulcer_index', np.nan)
    avg_ttr = metrics.get('avg_ttr', 0)
    max_ttr = metrics.get('max_ttr', 0)
    
    try:
        total_val = current_equity  
        
        if 'category_values' in locals() and category_values:
            # Sort categories by value (x[1]) in descending order
            sorted_categories = sorted(category_values.items(), key=lambda x: x[1], reverse=True)
            asset_alloc_str = " | ".join([f"{k} {v/total_val:.1%}" for k, v in sorted_categories])
        else:
            asset_alloc_str = "Not Available"
        
        if 'sector_values' in locals() and sector_values:
            sorted_sectors = sorted(sector_values.items(), key=lambda x: x[1], reverse=True)[:3]
            sector_alloc_str = " | ".join([f"{k} {v/total_val:.1%}" for k, v in sorted_sectors])
        else:
            sector_alloc_str = "Not Available"
        
        if 'current_values' in locals() and current_values:
            sorted_holdings = sorted(current_values.items(), key=lambda x: x[1], reverse=True)
            top_10_val = sum([x[1] for x in sorted_holdings[:10]])
            top_10_pct = top_10_val / total_val
            num_holdings = len(current_holdings) if 'current_holdings' in locals() else len(current_values)
        else:
            top_10_pct = 0
            num_holdings = 0
        
    except Exception as e:
        print(f"Error in composition metrics: {e}")
        asset_alloc_str = "Error"
        sector_alloc_str = "Error"
        top_10_pct = 0
        num_holdings = 0

    # Styling 
    def color_val(val, is_pct=False, reverse=False, show_hkd=True):
        try:
            if is_pct:
                color = "green" if val >= 0 else "red"
                if reverse:
                    color = "red" if val >= 0 else "green"
                fmt = f"{val:.2%}"
                return f'<span style="color: {color}; font-weight: bold;">{fmt}</span>'
            else:
                color = "green" if val >= 0 else "red"
                if reverse:
                    color = "red" if val >= 0 else "green"
                
                if show_hkd:
                    hkd_val = val * hkd_rate
                    fmt = f"US$ {val:,.2f} <span style='font-size: 0.8em; color: #666; font-weight: normal;'>| HK$ {hkd_val:,.2f}</span>"
                else:
                    fmt = f"US$ {val:,.2f}"
                    
                return f'<span style="color: {color}; font-weight: bold;">{fmt}</span>'
        except:
            return f'<span style="color: #666; font-weight: bold;">N/A</span>'

    def format_val(val, is_pct=False, show_hkd=True):
        try:
            color = "green" if val >= 0 else "red"
            if is_pct:
                fmt = f"{val:.2%}"
                return f'<span style="color: {color}; font-weight: bold;">{fmt}</span>'
            else:
                hkd_text = f" <span style='font-size: 0.8em; color: #666; font-weight: normal;'>| HK$ {val * hkd_rate:,.2f}</span>" if show_hkd else ""
                fmt = f"US$ {val:,.2f}{hkd_text}"
                return f'<span style="color: {color}; font-weight: bold;">{fmt}</span>'
        except:
            return '<span style="color: #666; font-weight: bold;">N/A</span>'

    # Return a dictionary of data instead of an HTML string
    summary_data = {
        "first_date": first_date.strftime('%Y-%m-%d'),
        "current_date": datetime.now().strftime('%Y-%m-%d'),
        "hkd_rate": f"{hkd_rate:.4f}",
        "current_equity_usd": f"{current_equity:,.2f}",
        "current_equity_hkd": f"{current_equity * hkd_rate:,.2f}",
        "current_market_value_usd": f"{current_market_value:,.2f}",
        "current_market_value_hkd": f"{current_market_value * hkd_rate:,.2f}",
        "current_cash_usd": f"{current_cash:,.2f}",
        "current_cash_hkd": f"{current_cash * hkd_rate:,.2f}",
        "total_return_abs_html": format_val(total_return_abs, show_hkd=True),
        "total_return_pct_html": format_val(total_return, is_pct=True),
        "max_return_html": format_val(max_return, show_hkd=True),
        "total_cum_return_html": format_val(total_cum_return, is_pct=True),
        "benchmark_total_return": f"{benchmark_total_return:.2%}",
        "alpha_html": format_val(alpha, is_pct=True),
        "volatility": f"{volatility:.2%}",
        "sharpe_ratio": f"{sharpe_ratio:.2f}",
        "benchmark_sharpe_ratio": f"{benchmark_sharpe_ratio:.2f}",
        "sortino_ratio": f"{sortino_ratio:.2f}",
        "benchmark_sortino_ratio": f"{benchmark_sortino_ratio:.2f}",
        "portfolio_beta": f"{portfolio_beta:.2f}",
        "tracking_error": f"{tracking_error:.2%}",
        "max_drawdown": f"{max_drawdown:.2%}",
        "var_95_percent_return": f"{var_95_percent_return:.2%}",
        "down_capture": f"{down_capture:.2f}",
        "up_capture": f"{up_capture:.2f}",
        "asset_alloc_str": asset_alloc_str,
        "sector_alloc_str": sector_alloc_str,
        "top_10_pct": f"{top_10_pct:.1%}",
        "num_holdings": num_holdings,
        "benchmark_name": config.METRICS_BENCHMARK,
        # Advanced Risk Metrics
        "skewness": f"{skewness:.3f}" if not np.isnan(skewness) else "N/A",
        "kurtosis": f"{kurtosis_val:.3f}" if not np.isnan(kurtosis_val) else "N/A",
        "cvar_95": f"{cvar_95:.2%}" if not np.isnan(cvar_95) else "N/A",
        "ulcer_index": f"{ulcer_index:.3f}" if not np.isnan(ulcer_index) else "N/A",
        "avg_ttr": f"{avg_ttr:.0f} days",
        "max_ttr": f"{max_ttr:.0f} days",
        # Fama-French Factor Results
        "ff_alpha": f"{factor_results.get('alpha_annual', 0):.2%}" if factor_results else "N/A",
        "ff_alpha_pval": f"{factor_results.get('alpha_p_value', 1):.4f}" if factor_results else "N/A",
        "ff_mkt_beta": f"{factor_results.get('mkt_beta', 0):.4f}" if factor_results else "N/A",
        "ff_smb": f"{factor_results.get('smb_beta', 0):.4f}" if factor_results else "N/A",
        "ff_hml": f"{factor_results.get('hml_beta', 0):.4f}" if factor_results else "N/A",
        "ff_r_squared": f"{factor_results.get('r_squared', 0):.4f}" if factor_results else "N/A",
    }

    return summary_data

    summary_sheet = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 1000px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background-color: #ffffff;">
        <div style="padding: 20px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; background-color: #ffffff;">
            <h2 style="margin: 0; color: #222;">PORTFOLIO SUMMARY</h2>
            <div style="text-align: right; color: #444; font-size: 0.9em;">
                <div>From {first_date.strftime('%Y-%m-%d')}</div>
                <div>As of {datetime.now().strftime('%Y-%m-%d')}</div>
                <div>USD/HKD: {hkd_rate:.4f}</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-bottom: 1px solid #e0e0e0; background-color: #ffffff;">
            <!-- VALUE & RETURN -->
            <div style="padding: 20px; border-right: 1px solid #e0e0e0; background-color: #ffffff;">
                <h3 style="margin-top: 0; color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; display: inline-block;">VALUE & RETURN</h3>
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.9em; color: #444; font-weight: 600;">Total Portfolio Value</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #000;">US$ {current_equity:,.2f} <span style="font-size: 0.7em; color: #555; font-weight: normal;">| HK$ {current_equity*hkd_rate:,.2f}</span></div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Market Value</div>
                        <div style="font-weight: 500; color: #222;">US$ {current_market_value:,.2f} <span style="font-size: 0.8em; color: #666;">| HK$ {current_market_value*hkd_rate:,.2f}</span></div>

                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Cash</div>
                        <div style="font-weight: 500; color: #222;">US$ {current_cash:,.2f} <span style="font-size: 0.8em; color: #666;">| HK$ {current_cash*hkd_rate:,.2f}</span></div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Total Return ($)</div>
                        <div>{color_val(total_return_abs, show_hkd=True)}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Total Return (%)</div>
                        <div>{color_val(total_return, is_pct=True, show_hkd=True)}</div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Max. Hist. Return ($)</div>
                        <div>{color_val(max_return, show_hkd=True)}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Total Cum. Return (%)</div>
                        <div>{color_val(total_cum_return, is_pct=True)}</div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Benchmark {config.METRICS_BENCHMARK}</div>
                        <div style="color: #222;">{benchmark_total_return:.2%}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Alpha (ann.)</div>
                        <div>{color_val(alpha, is_pct=True)}</div>
                    </div>
                </div>
            </div>

            <!-- RISK METRICS -->
            <div style="padding: 20px; background-color: #ffffff;">
                <h3 style="margin-top: 0; color: #333; border-bottom: 2px solid #dc3545; padding-bottom: 5px; display: inline-block;">RISK METRICS</h3>
                <div style="margin-bottom: 15px;">
                    <div style="font-size: 0.9em; color: #444; font-weight: 600;">Annualized Volatility</div>
                    <div style="font-size: 1.2em; font-weight: bold; color: #000;">{volatility:.2%}</div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 10px;">
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Sharpe Ratio</div>
                        <div style="font-weight: 500; color: #222;">{sharpe_ratio:.2f} <span style="font-size: 0.8em; color: #666;">| {benchmark_sharpe_ratio:.2f}</span></div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Sortino Ratio</div>
                        <div style="font-weight: 500; color: #222;">{sortino_ratio:.2f} <span style="font-size: 0.8em; color: #666;">| {benchmark_sortino_ratio:.2f}</span></div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Beta (vs {config.METRICS_BENCHMARK})</div>
                        <div style="color: #222;">{portfolio_beta:.2f}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Tracking Error</div>
                        <div style="color: #222;">{tracking_error:.2%}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Max Drawdown</div>
                        <div style="color: red;">{max_drawdown:.2%}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">VaR (95% 1-day)</div>
                        <div style="color: red;">{var_95_percent_return:.2%}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Down Capture Ratio</div>
                        <div style="color: #222;">{down_capture:.2f}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85em; color: #444; font-weight: 600;">Up Capture Ratio</div>
                        <div style="color: #222;">{up_capture:.2f}</div>
                    </div>
                </div>

            </div>
        </div>

        <!-- COMPOSITION -->
        <div style="padding: 20px; border-bottom: 1px solid #e0e0e0; background-color: #ffffff;">
            <h3 style="margin-top: 0; color: #333; border-bottom: 2px solid #28a745; padding-bottom: 5px; display: inline-block;">PORTFOLIO COMPOSITION</h3>
            <div style="margin-bottom: 10px;">
                <span style="font-weight: bold; color: #444;">Asset Allocation:</span> 
                <span style="color: #222;">{asset_alloc_str}</span>
            </div>
            <div style="margin-bottom: 10px;">
                <span style="font-weight: bold; color: #444;">Top 3 Sectors:</span> 
                <span style="color: #222;">{sector_alloc_str}</span>
            </div>
            <div style="display: flex; gap: 30px;">
                <div>
                    <span style="font-weight: bold; color: #444;">Top 10 Concentration:</span> 
                    <span style="color: #222;">{top_10_pct:.1%}</span>
                </div>
                <div>
                    <span style="font-weight: bold; color: #444;">Total Holdings:</span> 
                    <span style="color: #222;">{num_holdings}</span>
                </div>
            </div>
        </div>
        
        <!-- METRIC DEFINITIONS FOOTER -->
        <div style="padding: 15px 20px; background-color: #f9f9f9; color: #555; font-size: 0.8em; border-top: 1px solid #eee;">
            <div style="font-weight: bold; margin-bottom: 5px; color: #333;">Metric Definitions:</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px;">
                <div><strong>Sharpe:</strong> Excess return per unit of total risk (volatility).</div>
                <div><strong>Sortino:</strong> Excess return per unit of downside risk.</div>
                <div><strong>Beta:</strong> Portfolio volatility relative to the market ({config.METRICS_BENCHMARK}).</div>
                <div><strong>Alpha:</strong> Excess return over expected return given risk.</div>
                <div><strong>VaR (95%):</strong> Max expected loss in 1 day with 95% confidence.</div>
                <div><strong>Tracking Error:</strong> Deviation of portfolio returns from benchmark.</div>
            </div>
        </div>
    </div>
    """

    return summary_sheet
