import os 
from dotenv import load_dotenv

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR) 
DOTENV_PATH = os.path.join(PROJECT_ROOT, ".env")

load_dotenv(DOTENV_PATH)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MINUTE_DATA_DIR = os.path.join(DATA_DIR, "Minute")
DAILY_DATA_DIR = os.path.join(DATA_DIR, "Daily")
INPUT_DIR = os.path.join(PROJECT_ROOT, "input") # For trade.csv, financials.xlsx
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output") # For report generated

TRADE_EXCEL_SOURCE = os.getenv("TRADE_EXCEL_FILE")
TRADE_EXCEL_SHEET = os.getenv("TRADE_EXCEL_SHEET")

# Configuration
TRADE_HISTORY_FILE = os.path.join(INPUT_DIR, 'trade_history.csv')
METRICS_BENCHMARK = "SPY"
PLOT_BENCHMARK = ["SPY","QQQ","VEU"]

# Tickers without dividend tax
NO_DIVIDEND_TAX = ['SHV', 'SGOV', 'BIL']

# Hosting 

HOST = os.getenv("HOST")
USER = os.getenv("HOST_USER")
SUBPAGE = os.getenv("SUBPAGE")
REMOTE_REPORT_PATH = f"/home/{USER}/public_html/{SUBPAGE}/index.html"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(MINUTE_DATA_DIR, exist_ok=True)
os.makedirs(DAILY_DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

