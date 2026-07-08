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

    Параметры
    ----------
    values : array-like
        Объёмы (QTY) по ячейкам сетки.
    grid_size : int
        Размер одного фрагмента распределения в перцентилях.
        Например, если grid_size=20, то всё распределение делится на 5 частей по 20 перцентилей каждая.
        Количество цветов в палитре будет равно 100 // grid_size.
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

    # --- 1. Расчет количества цветов и шага перцентилей ---
    # PERCENTILE_GRID_SIZE определяет количество перцентилей в одном фрагменте (бакете).
    # Всего 100 перцентилей. Значит, количество цветовых групп = 100 / grid_size.
    num_colors = 100 // grid_size
    if num_colors < 1:
        num_colors = 1 # Защита от слишком большого grid_size

    # --- 2. Перцентильные пороги ---
    # Мы делим распределение на num_colors равных частей по grid_size перцентилей.
    # Но для корректного разбиения по квантилям matplotlib/numpy удобнее использовать
    # прямую связь с количеством цветов.
    quantiles = np.linspace(0, 1, num_colors + 1)
    thresholds = np.quantile(non_zero_vals, quantiles)

    # --- 3. Определяем бакет-индекс для каждого значения ---
    indices = []
    for v in values:
        if v <= 0:
            indices.append(-1)
        else:
            # Находим в каком интервале лежит значение
            idx = int(np.searchsorted(thresholds, v, side='right') - 1)
            idx = max(0, min(idx, num_colors - 1))
            indices.append(idx)

    # --- 4. Colormap ---
    cmap = plt.get_cmap(cmap_name)

    colors = []
    for idx in indices:
        if idx == -1:
            colors.append((0, 0, 0, 0)) # Transparent/None
        else:
            # Нормализуем индекс для получения цвета из colormap [0, 1]
            color_val = idx / (num_colors - 1) if num_colors > 1 else 0.5
            colors.append(cmap(color_val))

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

    # Vertical lines at whole hours (or 10 minutes/1 hour based on TIME_STEP_SEC)
    if time_step < 600:
        time_interval = timedelta(minutes=10)
    else:
        time_interval = timedelta(hours=1)

    current_time = datetime.fromtimestamp(start_ts).replace(second=0, microsecond=0)
    # Align current_time to the interval
    if time_interval == timedelta(minutes=10):
        # minutes must be multiple of 10
        minute = (current_time.minute // 10) * 10
        current_time = current_time.replace(minute=minute)
    else:
        current_time = current_time.replace(hour=(current_time.hour), minute=0)

    end_time_dt = datetime.fromtimestamp(end_ts)
    
    time_ticks = []
    while current_time <= end_time_dt:
        ts = current_time.timestamp()
        if start_ts <= ts <= end_ts:
            time_ticks.append(ts)
        current_time += time_interval
    
    # Add boundary ticks if they are not included but within range
    if start_ts > time_ticks[0] if time_ticks else False: # This is a bit simplified
         pass # In practice, we might want to ensure the very first tick is visible

    ax2.set_xticks(time_ticks)
    # For 10 min intervals, show HH:MM. For hours, show HH:00 or similar.
    ax2.set_xticklabels([datetime.fromtimestamp(t).strftime('%H:%M') for t in time_ticks], rotation=45)
    
    # Horizontal lines (Price grid) - multiples of 100
    # Find the first multiple of 100 >= min_p and last <= max_p
    start_price_tick = np.floor(min_p / 100) * 100
    end_price_tick = np.ceil(max_p / 100) * 100
    price_ticks = np.arange(start_price_tick, end_price_tick + 100, 100)
    
    # Filter price_ticks to only include those within the visible range (or slightly outside for grid effect)
    ax1.set_yticks(price_ticks)
    ax2.set_yticks(price_ticks)

    ax1.grid(True, which='both', axis='both', linestyle='--', linewidth=0.8, alpha=0.7, color='gray')

    # Add price ticks on the right side for ax1
    ax1.tick_params(axis='y', which='both', labelright=True, direction='inout', length=6)

    ax1.set_ylabel("Price (BUY)")
    ax1.set_title(f"Aggregated Profits Heatmap (Step: {time_step}s, {price_step} pts)")

    ax2.grid(True, which='both', axis='both', linestyle='--', linewidth=0.8, alpha=0.7, color='gray')
    # Add price ticks on the right side for ax2
    ax2.tick_params(axis='y', which='both', labelright=True, direction='inout', length=6)

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
