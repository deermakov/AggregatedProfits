import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import numpy as np

def run_aggregation(input_file, output_image, interval_seconds):
    # 1. Load data
    # Based on file analysis: tab-separated, with header.
    # Columns: SECURITY_NAME, TRADETIME, TRADETIME_MSEC, PRICE, QTY, BUYSELL, OPEN_INTEREST
    try:
        df = pd.read_csv(input_file, sep='\t')
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 2. Parse timestamp
    # TRADETIME is H:MM:SS, TRADETIME_MSEC is milliseconds
    # We need to combine them into a proper datetime object.
    # Note: The file doesn't have a date, but the filename suggests 2026-06-23.
    # Let's assume the date from the filename for completeness.
    date_part = "2026-06-23" # This could be extracted from filename if needed
    
    def combine_time(row):
        time_str = f"{date_part} {row['TRADETIME']}.{str(row['TRADETIME_MSEC']).zfill(3)}"
        return pd.to_datetime(time_str)

    df['timestamp'] = df.apply(combine_time, axis=1)
    df.set_index('timestamp', inplace=True)

    # 3. Resample to OHLC
    # 'S' for seconds. interval_seconds is passed as N.
    resampled = df['PRICE'].resample(f'{interval_seconds}s').ohlc()
    
    # Remove rows where no data exists (NaN) to make the chart cleaner, 
    # or keep them to show gaps. Usually, for trading, we drop NaN.
    resampled = resampled.dropna()

    if resampled.empty:
        print("No data available for the given interval.")
        return

    # 4. Plotting
    import matplotlib.patches as patches
    num_candles = len(resampled)
    # Calculate figure width based on number of candles. 
    # Each candle gets ~0.5 inches of width, with a min/max cap.
    fig_width = max(12, min(num_candles * 0.5, 40))
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    
    candle_body_width = 0.6  # Width of the rectangle

    for i, (index, row) in enumerate(resampled.iterrows()):
        color = 'green' if row['close'] >= row['open'] else 'red'
        # Wick (High-Low)
        ax.vlines(i, row['low'], row['high'], color=color, linewidth=1)
        # Body (Rectangle)
        bottom = min(row['open'], row['close'])
        height = abs(row['open'] - row['close'])
        if height == 0:
             ax.vlines(i, row['open'], row['open'], color=color, linewidth=2)
        else:
             # Center the candle body on index i
             rect = patches.Rectangle((i - candle_body_width/2, bottom), candle_body_width, height, color=color)
             ax.add_patch(rect)

    # Formatting X axis to show time instead of indices
    all_timestamps = resampled.index
    if not all_timestamps.empty:
        # We want ticks at the start of each candle (which is index i)
        # or at specific time intervals. 
        # The user wants candles centered on their start time's index.
        # Currently, 'i' IS the index for the candle starting at resampled.index[i].
        
        # Let's set ticks to be the indices of the candles themselves
        tick_indices = np.arange(len(resampled))
        
        # To avoid overcrowding, we only show some ticks
        step = max(1, len(resampled) // 20) 
        plot_ticks = tick_indices[::step]
        
        ax.set_xticks(plot_ticks)
        ax.set_xticklabels([resampled.index[i].strftime('%H:%M:%S') for i in plot_ticks], rotation=45)

    ax.set_title(f"OHLC Chart - Interval {interval_seconds}s")
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    
    # Добавление сетки
    ax.grid(True, which='both', linestyle='--', linewidth=1, alpha=1)

    # Вторая ось Y справа
    ax.tick_params(axis='y', labelright=True)
    
    # Set limits to show all candles correctly
    ax.set_xlim(-0.5, num_candles - 0.5)
    
    plt.tight_layout()
    
    # 5. Save
    plt.savefig(output_image)
    print(f"Chart saved to {output_image}")

if __name__ == "__main__":
    import sys
    
    # Using environment variables or command line args for config
    import os
    
    INPUT_FILE = os.getenv("INPUT_FILE", "data/2026.06.23.txt")
    OUTPUT_FILE = os.getenv("OUTPUT_FILE", "chart.png")
    N = int(os.getenv("INTERVAL_N", "60"))

    run_aggregation(INPUT_FILE, OUTPUT_FILE, N)
