import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def run_monte_carlo_permutation(daily_returns, n_iterations=10000, risk_free_rate=0.0):
    """
    Runs a non-parametric Monte Carlo permutation test (sign-flipping) to determine 
    the statistical significance of the portfolio's Sharpe ratio against a null hypothesis.
    """
    rets = daily_returns.dropna().values
    if len(rets) < 30:
        return np.nan, np.array([]), np.nan
        
    excess_rets = rets - risk_free_rate
    mean_ret = np.mean(excess_rets)
    std_ret = np.std(excess_rets)
    
    if std_ret == 0:
        return 0.0, np.array([]), 1.0
        
    actual_sharpe = (mean_ret / std_ret) * np.sqrt(252)
    
    # Randomly flip signs to simulate the null hypothesis (mean = 0)
    sign_flips = np.random.choice([-1, 1], size=(n_iterations, len(excess_rets)))
    simulated_excess_rets = excess_rets * sign_flips
    
    sim_means = np.mean(simulated_excess_rets, axis=1)
    sim_stds = np.std(simulated_excess_rets, axis=1)
    sim_stds = np.where(sim_stds == 0, 1e-10, sim_stds)
    sim_sharpes = (sim_means / sim_stds) * np.sqrt(252)
    
    p_value = np.sum(sim_sharpes >= actual_sharpe) / n_iterations
    
    return actual_sharpe, sim_sharpes, p_value

def run_monte_carlo_bootstrap(daily_returns, n_iterations=10000):
    """
    Runs a Monte Carlo bootstrap simulation (resampling with replacement) to 
    generate alternative historical paths. Calculates Cumulative Returns and 
    Max Drawdowns for each simulated reality.
    """
    rets = daily_returns.dropna().values
    n_days = len(rets)
    if n_days < 30:
        return None, None, None, None

    # Actual Cumulative Return Path
    actual_equity = np.cumprod(1 + rets)
    actual_cum_ret = actual_equity[-1] - 1
    actual_max_dd = np.max((np.maximum.accumulate(actual_equity) - actual_equity) / np.maximum.accumulate(actual_equity))

    # Resample with replacement to create 10,000 alternative paths
    indices = np.random.randint(0, n_days, size=(n_iterations, n_days))
    sim_rets = rets[indices]
    
    # Calculate geometric compounding equity curves natively
    sim_equity = np.cumprod(1 + sim_rets, axis=1)
    
    # 1. Final Cumulative Returns
    sim_cum_rets = sim_equity[:, -1] - 1
    
    # 2. Max Drawdowns per path
    sim_running_max = np.maximum.accumulate(sim_equity, axis=1)
    sim_drawdowns = (sim_running_max - sim_equity) / sim_running_max
    sim_max_dd = np.max(sim_drawdowns, axis=1)
    
    return actual_equity, actual_max_dd, sim_equity, sim_max_dd

def get_monte_carlo_plot(daily_returns, n_iterations=10000, show=False):
    """
    Generates a comprehensive 3-panel Plotly visualization:
    1. Spaghetti Plot of Bootstrapped Equity Paths
    2. Expected Max Drawdown Distribution
    3. Sharpe Ratio Significance Test
    """
    actual_sharpe, sim_sharpes, p_value = run_monte_carlo_permutation(daily_returns, n_iterations)
    bootstrap_results = run_monte_carlo_bootstrap(daily_returns, n_iterations)
    
    if np.isnan(p_value) or bootstrap_results[0] is None:
        fig = go.Figure()
        fig.add_annotation(text="Insufficient data for Monte Carlo simulation (need 30+ days).",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color="#6b7280"))
        fig.update_layout(template='plotly_white', height=400)
        return fig, {
            'p_value': np.nan, 'actual_sharpe': np.nan, 'threshold_95': np.nan, 
            'n_iterations': n_iterations, 'expected_max_dd_95': np.nan
        }
        
    actual_equity, actual_max_dd, sim_equity, sim_max_dd = bootstrap_results
    
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"colspan": 2}, None],
               [{}, {}]],
        subplot_titles=(
            "Cone of Uncertainty (Bootstrap Equity Paths)", 
            "Expected Max Drawdown Distribution", 
            "Sharpe Ratio Statistical Significance"
        ),
        vertical_spacing=0.15,
        horizontal_spacing=0.08
    )

    # ==========================================
    # 1. Spaghetti Plot (Row 1, spanning both cols)
    # ==========================================
    n_days = len(actual_equity)
    x_axis = np.arange(1, n_days + 1)
    
    # Plot ~100 random simulated paths as faint grey lines
    sample_idx = np.random.choice(n_iterations, min(100, n_iterations), replace=False)
    for idx in sample_idx:
        fig.add_trace(go.Scatter(
            x=x_axis, y=sim_equity[idx], 
            mode='lines', line=dict(color='rgba(156, 163, 175, 0.1)', width=1),
            showlegend=False, hoverinfo='skip'
        ), row=1, col=1)
        
    # Calculate confidence bands
    upper_band = np.percentile(sim_equity, 95, axis=0)
    median_band = np.median(sim_equity, axis=0)
    lower_band = np.percentile(sim_equity, 5, axis=0)
    
    fig.add_trace(go.Scatter(
        x=x_axis, y=upper_band, mode='lines', 
        line=dict(color='rgba(37, 99, 235, 0.8)', dash='dash', width=2),
        name='95th Percentile'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=x_axis, y=lower_band, mode='lines', 
        line=dict(color='rgba(220, 38, 38, 0.8)', dash='dash', width=2),
        name='5th Percentile'
    ), row=1, col=1)
    
    # Plot Actual Equity curve
    fig.add_trace(go.Scatter(
        x=x_axis, y=actual_equity, mode='lines', 
        line=dict(color='#111827', width=3),
        name='Actual Path (Multiplier)'
    ), row=1, col=1)

    # ==========================================
    # 2. Max Drawdown Distribution (Row 2, Col 1)
    # ==========================================
    fig.add_trace(go.Histogram(
        x=sim_max_dd, nbinsx=60, name='Simulated Max DD',
        marker_color='rgba(239, 68, 68, 0.6)', 
        marker_line=dict(color='rgba(185, 28, 28, 0.9)', width=0.5),
        histnorm='probability density',
        showlegend=False
    ), row=2, col=1)
    
    # Expected 95% Worst Case Drawdown
    expected_md_95 = np.percentile(sim_max_dd, 95)
    
    fig.add_vline(
        x=expected_md_95, line_dash="dash", line_color="#b91c1c", line_width=2,
        annotation_text=f"95% Worst Case: {expected_md_95:.1%}",
        annotation_position="top right" if expected_md_95 < 0.5 else "top left",
        annotation_font=dict(color="#b91c1c", size=10), row=2, col=1
    )
    fig.add_vline(
        x=actual_max_dd, line_dash="solid", line_color="#111827", line_width=2,
        annotation_text=f"Actual: {actual_max_dd:.1%}",
        annotation_position="bottom right" if actual_max_dd < 0.5 else "bottom left",
        annotation_font=dict(color="#111827", size=10, weight="bold"), row=2, col=1
    )

    # ==========================================
    # 3. Sharpe Permutation Distribution (Row 2, Col 2)
    # ==========================================
    fig.add_trace(go.Histogram(
        x=sim_sharpes, nbinsx=60, name='Sim. Sharpe (Null)',
        marker_color='rgba(156, 163, 175, 0.6)',
        marker_line=dict(color='rgba(107, 114, 128, 0.9)', width=0.5),
        histnorm='probability density',
        showlegend=False
    ), row=2, col=2)
    
    threshold_95 = np.percentile(sim_sharpes, 95)
    
    fig.add_vline(
        x=actual_sharpe, line_dash="solid", line_color="#2563eb", line_width=3,
        annotation_text=f"Actual: {actual_sharpe:.2f}<br>p: {p_value:.4f}",
        annotation_position="top right" if actual_sharpe > 0 else "top left",
        annotation_font=dict(color="#1e40af", size=10, weight="bold"), row=2, col=2
    )
    fig.add_vline(
        x=threshold_95, line_dash="dash", line_color="#dc2626", line_width=2,
        annotation_text=f"95% Threshold: {threshold_95:.2f}",
        annotation_position="bottom right" if threshold_95 > 0 else "bottom left",
        annotation_font=dict(color="#dc2626", size=10), row=2, col=2
    )
    
    # Highlight significant region
    max_x = max(sim_sharpes.max(), actual_sharpe) * 1.2
    if actual_sharpe > threshold_95:
        fig.add_vrect(
            x0=threshold_95, x1=max_x,
            fillcolor="rgba(34, 197, 94, 0.1)", layer="below", line_width=0,
            annotation_text="Signif.", annotation_position="top right",
            annotation_font=dict(color="#15803d", size=9), row=2, col=2
        )

    # ==========================================
    # Layout Adjustments
    # ==========================================
    fig.update_layout(
        template='plotly_white',
        height=750,
        margin=dict(t=60, b=40, l=50, r=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    
    fig.update_yaxes(title_text='Equity Multiplier', row=1, col=1)
    fig.update_xaxes(title_text='Trading Days', row=1, col=1)
    fig.update_xaxes(title_text='Max Drawdown depth', tickformat=".1%", row=2, col=1)
    fig.update_xaxes(title_text='Annualized Sharpe Ratio', row=2, col=2)

    if show:
        fig.show()

    results = {
        'p_value': p_value,
        'actual_sharpe': actual_sharpe,
        'threshold_95': threshold_95,
        'n_iterations': n_iterations,
        'expected_max_dd_95': expected_md_95
    }

    return fig, results
