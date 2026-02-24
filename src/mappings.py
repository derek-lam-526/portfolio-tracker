"""
Centralized mapping for asset categorization.
Maps Yahoo Finance ETF categories and Stock sectors to standardized portfolio groups.
"""

# Mapping for ETF Categories from yfinance info['category']
ETF_CATEGORY_MAP = {
    # US Broad Market
    'Large Blend': 'US Broad Market',
    'Large Growth': 'US Broad Market',
    'Large Value': 'US Broad Market',
    'Mid-Cap Blend': 'US Broad Market',
    'Mid-Cap Growth': 'US Broad Market',
    'Mid-Cap Value': 'US Broad Market',
    'Small Blend': 'US Broad Market',
    'Small Growth': 'US Broad Market',
    'Small Value': 'US Broad Market',
    
    # International Broad Market
    'Foreign Large Blend': 'International Broad Market',
    'Foreign Large Growth': 'International Broad Market',
    'Foreign Large Value': 'International Broad Market',
    'Foreign Small/Mid Blend': 'International Broad Market',
    'Foreign Small/Mid Growth': 'International Broad Market',
    'Foreign Small/Mid Value': 'International Broad Market',
    'Pacific/Asia ex-Japan Stk': 'International Broad Market',
    'Europe Stock': 'International Broad Market',
    'Emerging Markets Stock': 'International Broad Market',
    
    # Sector ETFs
    'Technology': 'Technology',
    'Communications': 'Communication Services',
    'Consumer Defensive': 'Consumer Staples',
    'Consumer Cyclical': 'Consumer Discretionary',
    'Energy': 'Energy',
    'Healthcare': 'Healthcare',
    'Financial': 'Financials',
    'Industrials': 'Industrials',
    'Natural Resources': 'Commodities',
    'Commodities Focused': 'Commodities',
    'Precious Metals': 'Commodities',
    'Miscellaneous Sector': 'Equity ETF (Other)',
    
    # Fixed Income
    'Ultrashort Bond': 'Treasury Bonds',
    'Short-Term Bond': 'Corporate Bonds',
    'Intermediate-Term Bond': 'Corporate Bonds',
    'Long-Term Bond': 'Corporate Bonds',
    'High Yield Bond': 'Corporate Bonds (HY)',
    'Inflation-Protected Bond': 'Other Fixed Income',
    'Muni National Short': 'Other Fixed Income',
}

# Mapping for Stock Sectors from yfinance info['sector']
STOCK_SECTOR_MAP = {
    'Technology': 'Technology',
    'Consumer Defensive': 'Consumer Staples',
    'Consumer Cyclical': 'Consumer Discretionary',
    'Communication Services': 'Communication Services',
    'Energy': 'Energy',
    'Healthcare': 'Healthcare',
    'Financial Services': 'Financials',
    'Industrials': 'Industrials',
    'Basic Materials': 'Basic Materials',
    'Real Estate': 'Real Estate',
    'Utilities': 'Utilities'
}

# Ticker-specific overrides (highest priority)
TICKER_OVERRIDES = {
    'VOO': 'US Broad Market',
    'QQQ': 'US Broad Market',
    'QQQM': 'US Broad Market',
    'VEU': 'International Broad Market',
    'SPYM': 'US Broad Market',
    'SGOV': 'Treasury Bonds',
    'SGOL': 'Commodities',
    'GLDM': 'Commodities',
    'COPX': 'Commodities',
}
