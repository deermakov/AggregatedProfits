import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os

# --- Settings/Config (Now using relative paths for Docker compatibility) ---
# When running in Docker, we will mount the local directory to /app/data
# So we use paths relative to /app/data inside the container.

def get_paths():
    # Default paths if not provided via environment variables
    input_file = os.environ.get('INPUT_FILE', '/app/data/2026.06.23.txt')
    output_image = os.environ.get('OUTPUT_IMAGE', '/app/data/result_chart.png')
    output_text = os.environ.get('OUTPUT_TEXT', '/app/data/cells_data.txt')
    time_step = float(os.environ.get('TIME_STEP_SEC', 1))
    price_step = float(os.environ.get('PRICE_STEP', 1))
    percentile_grid = int(os.environ.get('PERCENTILE_GRID_SIZE', 10))
    return input_file, output_image, output_text, time_step, price_step, percentile_grid

INPUT_FILE, OUTPUT_IMAGE, OUTPUT_TEXT, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE = get_paths()

def process_data(input_path, time_step, price_step, percentile_grid):
    # Load data
    df = pd.read_csv(input_path, sep='\t')
    
    # Combine time and msec to get proper datetime.
    # Since there is no date in the file, we'll use a placeholder date (e.g., 2026-06-23)
    df['datetime'] = pd.to_datetime('2026-06-23 ' + df['TRADETIME']) + \
                     pd.to_timedelta(df['TRADETIME_MSEC'], unit='us')

    # 1. & 2. Grid aggregation
    # Use timestamp for time grid to handle calculations easily
    df['ts'] = df['datetime'].apply(lambda x: x.timestamp())
    df['time_grid_ts'] = (df['ts'] // time_step) * time_step
    df['price_grid'] = (df['PRICE'] // price_step) * price_step

    # Group by grid and side
    grouped = df.groupby(['time_grid_ts', 'price_grid', 'BUYSELL'])['QTY'].sum().reset_index()

    # Pivot to get BUY and SELL in same row for easy processing
    pivot_df = grouped.pivot_table(index=['time_grid_ts', 'price_grid'], 
                                   columns='BUYSELL', 
                                   values='QTY', 
                                   fill_value=0).reset_index()

    # Ensure both columns exist even if one side is missing in data
    for col in ['BUY', 'SELL']:
        if col not in pivot_df.columns:
            pivot_df[col] = 0.0

    return pivot_df, df['datetime'].min(), df['datetime'].max()

def get_colors(values, grid_size, cmap_name='viridis'):
    """Вычисляет цвета для ячеек heatmap.

    Использует perceptually uniform colormap (viridis / magma) и логарифмическую
    нормализацию индексов, чтобы мелкие объёмы не «зашкаливали» по яркости,
    а крупные — чётко выделялись.

    Параметры
    ----------
    values : array-like
        Объёмы (QTY) по ячейкам сетки.
    grid_size : int
        Количество перцентильных бакетов.
    cmap_name : str
        Имя matplotlib colormap. 'viridis' — для BUY, 'magma' — для SELL.

    Возвращает
    ----------
    list of RGBA tuples
    """
    if len(values) == 0:
        return []

    non_zero_vals = values[values > 0]
    if len(non_zero_vals) == 0:
        return [(0, 0, 0, 0)] * len(values)

    # --- 1. Перцентильные пороги по ненулевым значениям ---
    quantiles = np.linspace(0, 1, grid_size + 1)
    thresholds = np.quantile(non_zero_vals, quantiles)

    # --- 2. Определяем бакет-индекс для каждого значения ---
    indices = []
    for v in values:
        if v <= 0:
            indices.append(-1)
        else:
            idx = int(np.searchsorted(thresholds, v, side='right') - 1)
            idx = max(0, min(idx, grid_size - 1))
            indices.append(idx)

    # --- 3. Perceptually uniform colormap ---
    cmap = plt.get_cmap(cmap_name)

    # --- 4. Логарифмическая нормализация индекса в [0, 1] ---
    #    log1p сглаживает переход: первые бакеты остаются тёмными,
    #    последние — ярко выражены. Без логарифма линейная шкала
    #    делает даже средние квантили слишком яркими.
    max_idx = grid_size - 1
    log_max = np.log1p(max_idx)

    colors = []
    for idx in indices:
        if idx == -1:
            colors.append((0, 0, 0, 0)) # Transparent/None
        else:
            # Normalize index to [0, 1] for colormap
            colors.append(cmap(idx / (grid_size - 1) if grid_size > 1 else 0))
            

    return colors

def save_cells_to_txt(pivot_df, start_time, output_path):
    """Сохраняет непустые ячейки BUY и SELL в текстовый файл."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Type\tStartTime\tMinPrice\tTotalVolume\n")
        for _, row in pivot_df.iterrows():
            t_ts = row['time_grid_ts']
            p = row['price_grid']
            start_dt = datetime.fromtimestamp(t_ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            if row['BUY'] > 0:
                f.write(f"BUY\t{start_dt}\t{p:.2f}\t{row['BUY']:.6f}\n")
            if row['SELL'] > 0:
                f.write(f"SELL\t{start_dt}\t{p:.2f}\t{row['SELL']:.6f}\n")

def plot_data(pivot_df, start_time, end_time, time_step, price_step, percentile_grid):
    if pivot_df.empty:
        print("No data to plot.")
        return

    # viridis  — perceptually uniform, тёмный→светлый (BUY)
    # magma    — perceptually uniform, тёмный→светлый (SELL)
    buy_colors = get_colors(pivot_df['BUY'].values, percentile_grid, cmap_name='viridis')
    sell_colors = get_colors(pivot_df['SELL'].values, percentile_grid, cmap_name='inferno')

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 14), sharex=True)

    for i, row in pivot_df.iterrows():
        t_ts = row['time_grid_ts']
        p = row['price_grid']
        
        if row['BUY'] > 0:
            rect_buy = plt.Rectangle((t_ts, p), time_step, price_step, facecolor=buy_colors[i], edgecolor='none')
            ax1.add_patch(rect_buy)
                
        if row['SELL'] > 0:
            rect_sell = plt.Rectangle((t_ts, p), time_step, price_step, facecolor=sell_colors[i], edgecolor='none')
            ax2.add_patch(rect_sell)

    start_ts = start_time.timestamp()
    end_ts = end_time.timestamp()
    min_p = pivot_df['price_grid'].min()
    max_p = pivot_df['price_grid'].max()

    ax1.set_xlim(start_ts, end_ts)
    ax1.set_ylim(min_p - price_step, max_p + price_step)
    ax2.set_xlim(start_ts, end_ts)
    ax2.set_ylim(min_p - price_step, max_p + price_step)

    # Vertical lines at whole hours
    current_hour = datetime.fromtimestamp(start_ts).replace(minute=0, second=0, microsecond=0)
    end_hour = datetime.fromtimestamp(end_ts).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    hour_ticks = []
    while current_hour <= end_hour:
        ts = current_hour.timestamp()
        if start_ts <= ts <= end_ts:
            hour_ticks.append(ts)
        current_hour += timedelta(hours=1)
    
    ax2.set_xticks(hour_ticks)
    ax2.set_xticklabels([datetime.fromtimestamp(t).strftime('%H:%M') for t in hour_ticks], rotation=45)
    
    # Horizontal lines (Price grid)
    price_ticks = np.linspace(min_p, max_p, 20) # Reasonable number of ticks
    ax1.set_yticks(price_ticks)
    ax2.set_yticks(price_ticks)

    ax1.grid(True, which='both', axis='both', linestyle='--', alpha=0.5)
    ax1.set_ylabel("Price (BUY)")
    ax1.set_title(f"Aggregated Profits Heatmap (Step: {time_step}s, {price_step} pts)")

    ax2.grid(True, which='both', axis='both', linestyle='--', alpha=0.5)
    ax2.set_xlabel("Time")
    ax2.set_ylabel("Price (SELL)")

    plt.tight_layout()
    plt.savefig(OUTPUT_IMAGE)
    print(f"Graph saved to {OUTPUT_IMAGE}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file not found at {INPUT_FILE}")
    else:
        try:
            df_pivot, start_t, end_t = process_data(INPUT_FILE, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE)
            plot_data(df_pivot, start_t, end_t, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE)
            save_cells_to_txt(df_pivot, start_t, OUTPUT_TEXT)
            print(f"Cells data saved to {OUTPUT_TEXT}")
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
