import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from collections import deque
import config
def match_trades(trades_df, portfolio_tracker=None):
    """
    Matches buy and sell orders using FIFO logic to calculate realized PnL for completed trades.
    If portfolio_tracker is provided, PnL is normalized to config.BASE_CURRENCY using historical FX.
    """
    import config
    
    # Filter for BUY and SELL only
    df = trades_df[trades_df['BUY/SELL'].isin(['BUY', 'SELL'])].copy()
    df = df.sort_values(['DATE', 'BUY/SELL']) # Ensure chronological order

    completed_trades = []
    open_lots = {}

    # Define a helper for FX normalization
    def get_fx_rate(currency, date):
        if not portfolio_tracker or currency == config.BASE_CURRENCY:
            return 1.0
        
        pair = f"{currency}{config.BASE_CURRENCY}=X"
        if pair in portfolio_tracker.market_data:
            fx_data = portfolio_tracker.market_data[pair]
            if not fx_data.empty:
                # Find closest rate
                idx = fx_data.index.get_indexer([pd.to_datetime(date)], method='pad')[0]
                if idx == -1: idx = 0 # Fallback to first available
                return fx_data.iloc[idx]['Close']
        return 1.0

    for _, row in df.iterrows():
        symbol = row['SYMBOL']
        date = row['DATE']
        qty = row['QTY']
        price = row['PRICE']
        buy_sell = row['BUY/SELL']
        market = row['MARKET']
        total_fee = row.get('FEE', 0)
        
        currency = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
        fee_per_unit = total_fee / qty if qty > 0 else 0

        if buy_sell == 'BUY':
            if symbol not in open_lots:
                open_lots[symbol] = deque()
            
            # Record entry FX rate
            entry_fx = get_fx_rate(currency, date)
            
            open_lots[symbol].append({
                'date': date,
                'qty': qty,
                'price': price,
                'fee_per_unit': fee_per_unit,
                'currency': currency,
                'entry_fx': entry_fx,
                'market': market
            })
        
        elif buy_sell == 'SELL':
            if symbol not in open_lots or not open_lots[symbol]:
                continue
            
            remaining_sell_qty = qty
            exit_fx = get_fx_rate(currency, date)
            
            while remaining_sell_qty > 0 and open_lots[symbol]:
                lot = open_lots[symbol][0]
                match_qty = min(remaining_sell_qty, lot['qty'])
                
                entry_price = lot['price']
                exit_price = price
                
                # Attributed fees (local currency)
                exit_fee_share = fee_per_unit * match_qty
                entry_fee_share = lot['fee_per_unit'] * match_qty
                
                # Local PnL
                gross_pnl_local = (exit_price - entry_price) * match_qty
                net_pnl_local = gross_pnl_local - exit_fee_share - entry_fee_share
                
                # Normalized PnL (to BASE_CURRENCY)
                # Logic: (Exit Value * Exit FX) - (Entry Value * Entry FX) - (Total Fees * Exit FX)
                exit_val_normalized = (exit_price * match_qty) * exit_fx
                entry_val_normalized = (entry_price * match_qty) * lot['entry_fx']
                total_fees_normalized = (exit_fee_share + entry_fee_share) * exit_fx # Using exit FX for fees is common simplification
                
                net_pnl_normalized = exit_val_normalized - entry_val_normalized - total_fees_normalized
                
                duration = (pd.to_datetime(date) - pd.to_datetime(lot['date'])).days
                
                completed_trades.append({
                    'SYMBOL': symbol,
                    'MARKET': market,
                    'CURRENCY': currency,
                    'ENTRY_DATE': lot['date'],
                    'EXIT_DATE': date,
                    'QTY': match_qty,
                    'ENTRY_PRICE': entry_price,
                    'EXIT_PRICE': exit_price,
                    'LOCAL_PNL': net_pnl_local,
                    'NET_PNL': net_pnl_normalized, # This is the primary PnL used in metrics (USD)
                    'DURATION': duration,
                    'ROI': (net_pnl_normalized / entry_val_normalized) if entry_val_normalized > 0 else 0
                })
                
                remaining_sell_qty -= match_qty
                lot['qty'] -= match_qty
                if lot['qty'] == 0:
                    open_lots[symbol].popleft()
                    
    return pd.DataFrame(completed_trades)

def calculate_trade_metrics(completed_trades_df):
    """
    Calculates performance metrics from completed (closed) trades.
    """
    if completed_trades_df.empty:
        return {}
    
    df = completed_trades_df
    
    total_trades = len(df)
    winning_trades = df[df['NET_PNL'] > 0]
    losing_trades = df[df['NET_PNL'] < 0]
    
    num_wins = len(winning_trades)
    num_losses = len(losing_trades)
    
    hit_rate = num_wins / total_trades if total_trades > 0 else 0
    
    avg_win = winning_trades['NET_PNL'].mean() if num_wins > 0 else 0
    avg_loss = losing_trades['NET_PNL'].mean() if num_losses > 0 else 0
    
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    gross_profits = winning_trades['NET_PNL'].sum()
    gross_losses = abs(losing_trades['NET_PNL'].sum())
    
    profit_factor = gross_profits / gross_losses if gross_losses != 0 else float('inf')
    
    # Expectancy = (Win% * AvgWin) + (Loss% * AvgLoss)
    expectancy = (hit_rate * avg_win) + ((1 - hit_rate) * avg_loss)
    
    metrics = {
        'total_trades': total_trades,
        'num_wins': num_wins,
        'num_losses': num_losses,
        'hit_rate': hit_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'payoff_ratio': payoff_ratio,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'max_win': df['NET_PNL'].max(),
        'max_loss': df['NET_PNL'].min(),
        'avg_duration': df['DURATION'].mean(),
        'total_realized_pnl': df['NET_PNL'].sum()
    }
    
    return metrics

def get_trade_analysis_plots(completed_trades_df):
    """
    Generates visualizations for trade analysis.
    """
    if completed_trades_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No completed trades found to analyze.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    df = completed_trades_df.sort_values('EXIT_DATE')
    df['CUM_PNL'] = df['NET_PNL'].cumsum()
    
    # Subplots: 1. Cumulative PnL, 2. Trade PnL Distribution, 3. Win/Loss Count
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"colspan": 2}, None],
               [{}, {}]],
        subplot_titles=("Cumulative Realized PnL", "Trade Return Distribution (%)", "Win vs Loss Count"),
        vertical_spacing=0.12,
        horizontal_spacing=0.1
    )

    # 1. Cumulative PnL Curve
    fig.add_trace(
        go.Scatter(x=df['EXIT_DATE'], y=df['CUM_PNL'], mode='lines+markers', 
                   name='Cum. PnL', line=dict(color='#2563eb', width=2),
                   marker=dict(size=4),
                   hovertemplate="<b>%{x}</b><br>Cum. PnL: " + config.BASE_CURRENCY + " %{y:,.2f}<extra></extra>"),
        row=1, col=1
    )

    # 2. ROI Distribution
    fig.add_trace(
        go.Histogram(x=df['ROI'] * 100, nbinsx=30, name='Trade ROI %',
                     marker_color='#10b981', opacity=0.7,
                     hovertemplate="ROI Range: %{x}%<br>Count: %{y}<extra></extra>"),
        row=2, col=1
    )
    
    # 3. Win/Loss Count
    num_wins = len(df[df['NET_PNL'] > 0])
    num_losses = len(df[df['NET_PNL'] <= 0])
    
    fig.add_trace(
        go.Bar(x=['Wins', 'Losses'], y=[num_wins, num_losses],
               marker_color=['#10b981', '#ef4444'], name='Counts',
               hovertemplate="Outcome: %{x}<br>Total: %{y}<extra></extra>"),
        row=2, col=2
    )

    fig.update_layout(
        height=700,
        showlegend=False,
        template='plotly_white',
        margin=dict(t=50, b=50, l=50, r=50)
    )
    
    fig.update_xaxes(title_text="Exit Date", row=1, col=1)
    fig.update_xaxes(title_text="Trade ROI (%)", row=2, col=1)
    fig.update_xaxes(title_text="Outcome", row=2, col=2)
    fig.update_yaxes(title_text=f"Net PnL ({config.BASE_CURRENCY})", row=1, col=1)
    fig.update_yaxes(title_text="Frequency", row=2, col=1)
    fig.update_yaxes(title_text="Total Count", row=2, col=2)

    return fig
