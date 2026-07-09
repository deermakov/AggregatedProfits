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
    output_image_aggregated = os.environ.get('OUTPUT_IMAGE_AGGREGATED', '/app/data/result_chart_aggregated.png')
    time_step = float(os.environ.get('TIME_STEP_SEC', 1))
    price_step = float(os.environ.get('PRICE_STEP', 1))
    percentile_grid = int(os.environ.get('PERCENTILE_GRID_SIZE', 10))
    return input_file, output_image, output_text, output_image_aggregated, time_step, price_step, percentile_grid

INPUT_FILE, OUTPUT_IMAGE, OUTPUT_TEXT, OUTPUT_IMAGE_AGGREGATED, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE = get_paths()

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

def aggregate_cells(pivot_df, time_step):
    """
    Aggregates adjacent horizontal cells with non-zero volume into a single cell.
    """
    if pivot_df.empty:
        return pivot_df

    # Sort by price and then by timestamp to ensure we process rows in order
    df = pivot_df.sort_values(['price_grid', 'time_grid_ts']).copy()
    
    new_rows = []
    
    for price, group in df.groupby('price_grid'):
        group = group.sort_values('time_grid_ts')
        
        i = 0
        n = len(group)
        while i < n:
            current_row = group.iloc[i]
            total_vol = current_row['BUY'] + current_row['SELL']
            
            if total_vol > 0:
                # Start a new aggregated cell
                start_idx = i
                end_idx = i
                
                # Try to extend this group horizontally (temporally)
                while end_idx + 1 < n:
                    next_row = group.iloc[end_idx + 1]
                    next_total_vol = next_row['BUY'] + next_row['SELL']
                    
                    # Check if it's the immediate next cell in time
                    if next_row['time_grid_ts'] <= group.iloc[end_idx]['time_grid_ts'] + time_step:
                        if next_total_vol > 0:
                            end_idx += 1
                        else:
                            break
                    else:
                        break
                
                # We have a group from start_idx to end_idx
                group_rows = group.iloc[start_idx : end_idx + 1]
                agg_row = {
                    'time_grid_ts': group_rows['time_grid_ts'].min(),
                    'price_grid': price,
                    'BUY': group_rows['BUY'].sum(),
                    'SELL': group_rows['SELL'].sum(),
                    'width_cells': len(group_rows) # Number of elementary cells it spans
                }
                new_rows.append(agg_row)
                i = end_idx + 1
            else:
                # Zero volume cell, just keep it as is
                new_rows.append(current_row.to_dict())
                i += 1

    agg_df = pd.DataFrame(new_rows)
    if 'width_cells' not in agg_df.columns:
        agg_df['width_cells'] = 1
        
    return agg_df

def get_colors(values, grid_size, cmap_name='viridis'):
    """Вычисляет цвета для ячеек heatmap."""
    if len(values) == 0:
        return []

    non_zero_vals = values[values > 0]
    if len(non_zero_vals) == 0:
        return [(0, 0, 0, 0)] * len(values)

    num_colors = 100 // grid_size
    if num_colors < 1:
        num_colors = 1

    quantiles = np.linspace(0, 1, num_colors + 1)
    thresholds = np.quantile(non_zero_vals, quantiles)

    indices = []
    for v in values:
        if v <= 0:
            indices.append(-1)
        else:
            idx = int(np.searchsorted(thresholds, v, side='right') - 1)
            idx = max(0, min(idx, num_colors - 1))
            indices.append(idx)

    cmap = plt.get_cmap(cmap_name)

    colors = []
    for idx in indices:
        if idx == -1:
            colors.append((0, 0, 0, 0))
        else:
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

def plot_data(pivot_df, start_time, end_time, time_step, price_step, percentile_grid, output_path=None):
    if pivot_df.empty:
        print("No data to plot.")
        return

    buy_colors = get_colors(pivot_df['BUY'].values, percentile_grid, cmap_name='viridis')
    sell_colors = get_colors(pivot_df['SELL'].values, percentile_grid, cmap_name='inferno')

    start_ts = start_time.timestamp()
    end_ts = end_time.timestamp()

    width_per_second = 0.1 / 60.0  # inches per second
    calculated_width = (end_ts - start_ts) * width_per_second
    final_width = max(12, calculated_width)
    final_height = 14
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(final_width, final_height), sharex=True)

    for i, row in pivot_df.iterrows():
        t_ts = row['time_grid_ts']
        p = row['price_grid']
        width = time_step * row.get('width_cells', 1)

        if row['BUY'] > 0:
            rect_buy = plt.Rectangle((t_ts, p), width, price_step, facecolor=buy_colors[i], edgecolor='none')
            ax1.add_patch(rect_buy)
                
        if row['SELL'] > 0:
            rect_sell = plt.Rectangle((t_ts, p), width, price_step, facecolor=sell_colors[i], edgecolor='none')
            ax2.add_patch(rect_sell)

    min_p = pivot_df['price_grid'].min()
    max_p = pivot_df['price_grid'].max()

    ax1.set_xlim(start_ts, end_ts)
    ax1.set_ylim(min_p - price_step, max_p + price_step)
    ax2.set_xlim(start_ts, end_ts)
    ax2.set_ylim(min_p - price_step, max_p + price_step)

    if time_step < 600:
        time_interval = timedelta(minutes=10)
    else:
        time_interval = timedelta(hours=1)

    current_time = datetime.fromtimestamp(start_ts).replace(second=0, microsecond=0)
    if time_interval == timedelta(minutes=10):
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
    
    ax2.set_xticks(time_ticks)
    ax2.set_xticklabels([datetime.fromtimestamp(t).strftime('%H:%M') for t in time_ticks], rotation=45)
    
    start_price_tick = np.floor(min_p / 100) * 100
    end_price_tick = np.ceil(max_p / 100) * 100
    price_ticks = np.arange(start_price_tick, end_price_tick + 100, 100)
    
    ax1.set_yticks(price_ticks)
    ax2.set_yticks(price_ticks)

    ax1.grid(True, which='both', axis='both', linestyle='--', linewidth=0.8, alpha=0.7, color='gray')
    ax1.tick_params(axis='y', which='both', labelright=True, direction='inout', length=6)
    ax1.set_ylabel("Price (BUY)")
    ax1.set_title(f"Aggregated Profits Heatmap (Step: {time_step}s, {price_step} pts)")

    ax2.grid(True, which='both', axis='both', linestyle='--', linewidth=0.8, alpha=0.7, color='gray')
    ax2.tick_params(axis='y', which='both', labelright=True, direction='inout', length=6)
    ax2.set_xlabel("Time")
    ax2.set_ylabel("Price (SELL)")

    plt.tight_layout()
    target_path = output_path if output_path else OUTPUT_IMAGE
    plt.savefig(target_path)
    print(f"Graph saved to {target_path}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file not found at {INPUT_FILE}")
    else:
        try:
            df_pivot, start_t, end_t = process_data(INPUT_FILE, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE)
            plot_data(df_pivot, start_t, end_t, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE)
            save_cells_to_txt(df_pivot, start_t, OUTPUT_TEXT)
            print(f"Cells data saved to {OUTPUT_TEXT}")

            print("Running aggregated version...")
            df_agg = aggregate_cells(df_pivot, TIME_STEP_SEC)
            plot_data(df_agg, start_t, end_t, TIME_STEP_SEC, PRICE_STEP, PERCENTILE_GRID_SIZE, output_path=OUTPUT_IMAGE_AGGREGATED)
            print(f"Aggregated graph saved to {OUTPUT_IMAGE_AGGREGATED}")

        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
