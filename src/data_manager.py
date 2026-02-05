import shutil 
import warnings 
import pandas as pd
import os
import config

def copy_file(source, destination_dir):
    """
    Copy a file from source to destination.
    """
    try:
        shutil.copy(source, destination_dir)
        print(f"File copied from {source} to {destination_dir}")
    except Exception as e:
        print(f"Error copying file: {e}")

def get_trade_df(file_path, sheet_name=config.TRADE_EXCEL_SHEET):
    """
    Read the Excel file and return a list of symbols from the specified sheet.
    """
    
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        if "CHECK" in df.columns:
            df = df.drop(["CHECK"], axis = 1)
        
        df.columns = df.columns.str.upper().str.strip()

        if "FEE" not in df.columns:
            df["FEE"] = 0.0
        else:
            df["FEE"] = df["FEE"].fillna(0.0)

        df.dropna(inplace = True)
        df["DATE"] = df["DATE"].dt.date
        if "AMT" in df.columns:
            df = df.drop(["AMT"], axis=1)
        df["QTY"] = df["QTY"].apply(int)
        df["AMT"] = (df["QTY"] * df["PRICE"]).round(3)
        df["FEE"] = df["FEE"].astype(float).round(3)

        return df
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return []

def export_trade_csv(trade_df, output_dir):
    try:
        output_path = os.path.join(output_dir, "trade_history.csv")
        trade_df.to_csv(output_path, sep=',', index=False)
        return 
    except Exception as e:
        print(f"Error exporting CSV file: {e}")
        return 

def create_trade_csv():
    source_filename = os.path.basename(config.TRADE_EXCEL_SOURCE)
    copy_file(source=config.TRADE_EXCEL_SOURCE,
              destination_dir=config.INPUT_DIR)
    
    excel_file_path = os.path.join(config.INPUT_DIR, source_filename)
    trade_df = get_trade_df(excel_file_path)

    if hasattr(trade_df, 'to_csv'):
        export_trade_csv(trade_df, config.INPUT_DIR)

def load_trade_history(filepath):
    df = pd.read_csv(filepath)
    df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=False)
    
    if 'FEE' not in df.columns:
        df['FEE'] = 0.0
        
    buysell_order = ['DEPOSIT', 'BUY', 'WITHDRAW', 'SELL']
    df['BUY/SELL'] = pd.Categorical(df['BUY/SELL'], categories=buysell_order, ordered=True)

    return df.sort_values(['DATE', 'BUY/SELL'])

