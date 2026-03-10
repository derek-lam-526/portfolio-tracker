import config
import os
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

def create_report(figs, df_alloc, df_trades, output_dir=config.OUTPUT_DIR):
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    summary_data = figs["summary"] 
    plotly_config = {'responsive': True, 'displayModeBar': True}   
    
    wealth_html = figs["wealth"].to_html(
        full_html=False, include_plotlyjs='cdn',
        default_width='100%', default_height='500px', config=plotly_config
    )
    drawdown_html = figs["drawdown"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='300px', config=plotly_config
    )
    returns_html = figs["returns"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='500px', config=plotly_config
    )
    alloc_html = figs["alloc"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='500px', config=plotly_config
    )
    quant_html = figs["quant"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='800px', config=plotly_config
    )
    distribution_html = figs["distribution"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='450px', config=plotly_config
    )
    correlation_html = figs["correlation"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='500px', config=plotly_config
    )
    beta_exposure_html = figs["beta_exposure"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='500px', config=plotly_config
    )
    factor_analysis_html = figs["factor_analysis"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='420px', config=plotly_config
    )
    monte_carlo_html = figs["monte_carlo"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='750px', config=plotly_config
    )
    trade_analysis_html = figs["trade_analysis"].to_html(
        full_html=False, include_plotlyjs=False,
        default_width='100%', default_height='700px', config=plotly_config
    )

    # Prettify Trade History for display
    display_trades = df_trades.copy()
    
    # Format EXCHANGE actions to be more descriptive
    exchange_mask = display_trades['BUY/SELL'] == 'EXCHANGE'
    if exchange_mask.any():
        # MARKET is source, SYMBOL is target market code
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
    # Or fetch from tracker if needed? summary_data already has hkd_rate, let's genericize
    fx_rates = {}
    
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
