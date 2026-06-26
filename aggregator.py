import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os

# Settings/Config loaded from environment variables or defaults
INPUT_FILE = os.getenv('INPUT_FILE', '/data/2026.06.23.txt')
OUTPUT_FILE = os.getenv('OUTPUT_FILE', '/output/chart.png')
N_SECONDS = int(os.getenv('N_SECONDS', 5))
CANDLE_WIDTH_PX = int(os.getenv('CANDLE_WIDTH_PX', 10))

def load_and_process_data(file_path, n_seconds):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    df = pd.read_csv(file_path, sep='\t')
    
    def combine_time(row):
        t_str = row['TRADETIME']
        msec = row['TRADETIME_MSEC']
        base_date = datetime.strptime("2026-01-01 " + t_str, "%Y-%m-%d %H:%M:%S")
        return base_date + timedelta(milliseconds=int(msec))

    df['timestamp'] = df.apply(combine_time, axis=1)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    resampler = df.resample(f'{n_seconds}S')
    ohlc = resampler['PRICE'].ohlc()
    ohlc['color'] = ['green' if c >= o else 'red' for o, c in zip(ohlc['open'], ohlc['close'])]
    
    buy_vol = df[df['BUYSELL'] == 'BUY']['QTY'].resample(f'{n_seconds}S').sum()
    sell_vol = df[df['BUYSELL'] == 'SELL']['QTY'].resample(f'{n_seconds}S').sum()
    
    combined = pd.DataFrame({
        'open': ohlc['open'],
        'high': ohlc['high'],
        'low': ohlc['low'],
        'close': ohlc['close'],
        'color': ohlc['color'],
        'buy_vol': buy_vol,
        'sell_vol': sell_vol
    }).fillna(0)
    
    return combined

def plot_data_final(df, output_path):
    n = len(df)
    if n == 0:
        return
        
    DPI = 100
    # Calculate figsize in inches to achieve desired pixel width per candle
    # Each candle interval (integer index step) will be exactly CANDLE_WIDTH_PX wide.
    fig_width_inch = (n * CANDLE_WIDTH_PX) / DPI
    # Maintain a reasonable aspect ratio for the whole figure
    fig_height_inch = fig_width_inch * 0.6 

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width_inch, fig_height_inch), 
                                  sharex=True, gridspec_kw={'height_ratios': [2, 1]}, dpi=DPI)
    plt.subplots_adjust(hspace=0.05)

    x = range(n)
    
    # Relative widths within one interval unit (which is CANDLE_WIDTH_PX wide)
    body_width = 0.6
    vol_width = 0.4

    # Plotting ax1 (Price Candlesticks)
    for i in range(n):
        row = df.iloc[i]
        if pd.isna(row['open']) or (row['open'] == 0 and row['close'] == 0): 
            continue
        
        color = row['color']
        ax1.vlines(i, row['low'], row['high'], color=color, linewidth=1)
        height = abs(row['open'] - row['close'])
        bottom = min(row['open'], row['close'])
        plot_height = max(height, (row['high'] - row['low']) * 0.01) if height == 0 else height
        ax1.bar(i, plot_height, bottom=bottom, color=color, width=body_width, edgecolor=color, align='center')

    ax1.set_ylabel('Price')
    ax1.grid(True, which='major', axis='both', linestyle='--', alpha=0.7)
    ax1.xaxis.grid(True, which='major', color='gray', linestyle='-', alpha=0.5)

    # Plotting ax2 (Volume Bars side-by-side)
    ax2.bar([idx - vol_width/2 for idx in x], df['buy_vol'].values, width=vol_width, color='green', label='BUY Volume', align='center')
    ax2.bar([idx + vol_width/2 for idx in x], df['sell_vol'].values, width=vol_width, color='red', label='SELL Volume', align='center')

    ax2.set_ylabel('Volume')
    ax2.set_xlabel('Time')
    ax2.legend(loc='upper left')
    ax2.grid(True, which='major', axis='y', linestyle='--', alpha=0.5)

    # Formatting X-axis with Time labels
    time_labels = [df.index[i].strftime('%H:%M:%S') for i in range(n)]
    ax2.set_xticks(x)
    ax2.set_xticklabels(time_labels, rotation=45, fontsize=8)
    
    step = max(1, n // 20)
    for i, label in enumerate(ax2.get_xticklabels()):
        if i % step != 0:
            label.set_visible(False)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    plt.savefig(output_path)
    print(f"Chart saved to {output_path} (Size: {int(fig_width_inch*DPI)}x{int(fig_height_inch*DPI)} px)")

def main():
    try:
        print(f"Loading data from: {INPUT_FILE}")
        df = load_and_process_data(INPUT_FILE, N_SECONDS)
        if df.empty:
            print("No data found.")
            return
        print(f"Data loaded. Resampled with N={N_SECONDS}s. Target candle width: {CANDLE_WIDTH_PX}px. Processing plot...")
        plot_data_final(df, OUTPUT_FILE)
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
