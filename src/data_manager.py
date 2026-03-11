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
        df.columns = df.columns.str.upper().str.strip()
        
        # Backward compatibility: Rename BUY/SELL to ACTION
        if "BUY/SELL" in df.columns and "ACTION" not in df.columns:
            df = df.rename(columns={"BUY/SELL": "ACTION"})

        expected_columns = ["DATE", "MARKET", "SYMBOL", "ACTION", "QTY", "PRICE", "FEE"]
        cols_to_keep = [col for col in expected_columns if col in df.columns]
        df = df[cols_to_keep].copy()

        if "FEE" not in df.columns:
            df["FEE"] = 0.0
        else:
            df["FEE"] = df["FEE"].fillna(0.0)

        df.dropna(inplace=True)
        df["DATE"] = df["DATE"].dt.date
        df["QTY"] = df["QTY"].apply(int)
        
        # Calculate AMT: for standard trades it's QTY * PRICE, but for EXCHANGE it should just be QTY (the source amount)
        # or we can keep it as PRICE if the user prefers to see the target amount. 
        # Given the user says "it multiply the two numbers together. fix this", 
        # let's make it more logic-aware.
        
        def calculate_amt(row):
            action = str(row.get('ACTION', '')).upper()
            if action == 'EXCHANGE':
                return row['QTY'] # Show the source amount being exchanged
            return row['QTY'] * row['PRICE']

        df["AMT"] = df.apply(calculate_amt, axis=1).round(3)
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
        
    buysell_order = ['DEPOSIT', 'BUY', 'WITHDRAW', 'SELL', 'EXCHANGE']
    
    # Backward compatibility for CSV
    if 'BUY/SELL' in df.columns and 'ACTION' not in df.columns:
        df = df.rename(columns={'BUY/SELL': 'ACTION'})
        
    df['ACTION'] = pd.Categorical(df['ACTION'].str.upper(), categories=buysell_order, ordered=True)

    return df.sort_values(['DATE', 'ACTION'])

