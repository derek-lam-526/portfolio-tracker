import config

import pandas as pd 
import numpy as np 
from scipy import stats
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
        'up_capture': up_capture if 'up_capture' in locals() else np.nan
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
        width=1400,  
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
            y=1.02, 
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
            y=1.02, 
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
    rolling_max = history_df['Total_Equity'].cummax()
    drawdowns = (history_df['Total_Equity'] / rolling_max) - 1

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=drawdowns.index, 
        y=drawdowns * 100,
        mode='lines',
        name='Drawdown',
        line=dict(color='#D32F2F', width=1), # Red Line
        fill='tozeroy',
        fillcolor='rgba(211, 47, 47, 0.2)', # Red Fill
        hovertemplate='%{y:.2f}%'
    ))

    # 3. Layout
    fig.update_layout(
        title_text="Underwater Plot (Drawdown from Peak)",
        template="plotly_white",
        height=400,
        showlegend=False,
        hovermode="x unified",
        yaxis=dict(title='Drawdown (%)')
    )
    
    # Add 0% Line
    fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1)

    # Clean X-Axis (Hide weekends)
    fig.update_xaxes(
        rangebreaks=[dict(bounds=["sat", "mon"])],
        showgrid=True, gridcolor='#E0E0E0'
    )
    fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0')

    if show:
        fig.show()
        
    return fig

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
        hoverinfo='label+value+percent'
    ), 1, 1)

    # Pie 2: By Asset Class
    fig_alloc.add_trace(go.Pie(
        labels=df_by_category['Category'], 
        values=df_by_category['Value'], 
        name="Asset Class",
        textinfo='label+percent',
        hoverinfo='label+value+percent'
    ), 1, 2)

    fig_alloc.update_layout(title_text=f"Portfolio Allocation (Total: ${total_portfolio_value:,.2f})", 
                    height=650,
                    showlegend=True,
                    uniformtext_minsize=10,
                    uniformtext_mode='hide')

    # Display DataFrame
    df_alloc = df_allocation.copy()
    df_alloc['Value'] = df_alloc['Value'].apply(lambda x: f"${x:,.2f}")
    df_alloc['Allocation (%)'] = df_alloc['Allocation (%)'].apply(lambda x: f"{x:.2f}%")

    if show:
        fig_alloc.show()

    return fig_alloc, df_alloc, category_values, sector_values, current_values, current_holdings

def get_summary_sheet(history_df, category_values, sector_values, current_values, current_holdings):
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
    
    try:
        total_val = current_equity  
        
        if 'category_values' in locals() and category_values:
            asset_alloc_str = " | ".join([f"{k} {v/total_val:.1%}" for k, v in category_values.items()])
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
