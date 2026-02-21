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

    # Create interactive tables
    alloc_table_html = df_alloc.to_html(
        index=False, classes='display compact stripe hover order-column row-border', 
        border=0, table_id='alloc_table'
    )
    trades_table_html = df_trades.to_html(
        index=False, classes='display compact stripe hover order-column row-border', 
        border=0, table_id='trades_table'
    )
    
    templates_dir = os.path.join(config.SRC_DIR, 'templates')
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template('report_template.html')
    
    # Render template
    html_output = template.render(
        current_time=current_time,
        summary=summary_data,
        wealth_html=wealth_html,
        drawdown_html=drawdown_html,
        returns_html=returns_html,
        alloc_html=alloc_html,
        alloc_table_html=alloc_table_html,
        trades_table_html=trades_table_html
    )
    
    output_path = os.path.join(output_dir, f"portfolio_report_{current_date}.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    return output_path
