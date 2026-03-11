import config
import os
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

def create_report(figs, df_alloc, df_trades, tracker_obj, output_dir=config.OUTPUT_DIR):
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    summary_data = figs["summary"] 
    plotly_config = {'responsive': True, 'displayModeBar': True}   
    
    # ... [Plotly HTML generations omitted for brevity] ...
    wealth_html = figs["wealth"].to_html(full_html=False, include_plotlyjs='cdn', default_width='100%', default_height='500px', config=plotly_config)
    drawdown_html = figs["drawdown"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='300px', config=plotly_config)
    returns_html = figs["returns"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='500px', config=plotly_config)
    alloc_html = figs["alloc"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='500px', config=plotly_config)
    quant_html = figs["quant"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='800px', config=plotly_config)
    distribution_html = figs["distribution"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='450px', config=plotly_config)
    correlation_html = figs["correlation"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='500px', config=plotly_config)
    beta_exposure_html = figs["beta_exposure"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='500px', config=plotly_config)
    factor_analysis_html = figs["factor_analysis"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='420px', config=plotly_config)
    monte_carlo_html = figs["monte_carlo"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='750px', config=plotly_config)
    trade_analysis_html = figs["trade_analysis"].to_html(full_html=False, include_plotlyjs=False, default_width='100%', default_height='700px', config=plotly_config)

    # Prettify Trade History for display
    display_trades = df_trades.copy()
    
    # 1. Convert all amounts to Base Currency
    def convert_to_base(row):
        trade_date = pd.to_datetime(row['DATE'])
        # Handle cases where trade_date might be slightly outside our history range
        market = row['MARKET']
        currency = config.MARKET_REGISTRY.get(market, {}).get('currency', config.BASE_CURRENCY)
        
        if currency == config.BASE_CURRENCY:
            return row['AMT'], row['FEE']
            
        pair = f"{currency}{config.BASE_CURRENCY}=X"
        fx_rate = 1.0
        if pair in tracker_obj.market_data and not tracker_obj.market_data[pair].empty:
            # Try to get rate for exact date, if not, ffill from available history
            fx_series = tracker_obj.market_data[pair]['Close']
            if trade_date in fx_series.index:
                fx_rate = fx_series.loc[trade_date]
            else:
                # Find nearest previous rate
                past_rates = fx_series[fx_series.index <= trade_date]
                if not past_rates.empty:
                    fx_rate = past_rates.iloc[-1]
                else:
                    fx_rate = fx_series.iloc[0] # Fallback to earliest
                    
        return round(row['AMT'] * fx_rate, 2), round(row['FEE'] * fx_rate, 2)

    # Apply conversion
    import pandas as pd
    converted_values = display_trades.apply(convert_to_base, axis=1)
    display_trades['AMT'] = [v[0] for v in converted_values]
    display_trades['FEE'] = [v[1] for v in converted_values]
    
    # Rename column to indicate Base Currency
    display_trades = display_trades.rename(columns={'AMT': f'AMT ({config.BASE_CURRENCY})', 'FEE': f'FEE ({config.BASE_CURRENCY})'})

    # 2. Format EXCHANGE actions to be more descriptive
    exchange_mask = display_trades['ACTION'] == 'EXCHANGE'
    if exchange_mask.any():
        display_trades.loc[exchange_mask, 'SYMBOL'] = display_trades.loc[exchange_mask].apply(
            lambda x: f"FX: {x['MARKET']} → {x['SYMBOL']}", axis=1
        )
    
    # Create interactive tables
    alloc_table_html = df_alloc.to_html(
        index=False, classes='display compact stripe hover order-column row-border', 
        border=0, table_id='alloc_table'
    )
    
    trades_table_html = display_trades.to_html(
        index=False, classes='display compact stripe hover order-column row-border', 
        border=0, table_id='trades_table'
    )
    
    # Extract dynamic FX rates from summary if available
    fx_rates = {}
    if summary_data.get("secondary_currency") and summary_data.get("secondary_fx_rate"):
        base = summary_data['current_base_currency']
        secondary = summary_data['secondary_currency']
        rate_val = float(summary_data["secondary_fx_rate"])
        
        # Base -> Secondary
        fx_rates[f"{base}/{secondary}"] = f"{rate_val:.4f}"
        # Secondary -> Base (Inverse)
        if rate_val != 0:
            fx_rates[f"{secondary}/{base}"] = f"{(1.0/rate_val):.4f}"

    templates_dir = os.path.join(config.SRC_DIR, 'templates')
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template('report_template.html')
    
    # Render template
    html_output = template.render(
        current_time=current_time,
        summary=summary_data,
        fx_rates=fx_rates,
        wealth_html=wealth_html,
        drawdown_html=drawdown_html,
        returns_html=returns_html,
        alloc_html=alloc_html,
        alloc_table_html=alloc_table_html,
        quant_html=quant_html,
        distribution_html=distribution_html,
        correlation_html=correlation_html,
        beta_exposure_html=beta_exposure_html,
        factor_analysis_html=factor_analysis_html,
        monte_carlo_html=monte_carlo_html,
        trade_analysis_html=trade_analysis_html,
        trades_table_html=trades_table_html
    )
    
    output_path = os.path.join(output_dir, f"portfolio_report_{current_date}.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    return output_path
