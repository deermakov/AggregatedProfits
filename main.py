import pandas as pd
import matplotlib.pyplot as plt
import os

# --- CONFIGURATION (Can be set via environment variables in docker-compose) ---
# We use default values for local testing, but Docker will override them via ENV
INPUT_FILE = os.getenv('INPUT_FILE', r'c:\_Work\ML\AggregatedProfits\2026.06.23.txt')
OUTPUT_GRAPH = os.getenv('OUTPUT_GRAPH', r'c:\_Work\ML\AggregatedProfits\plot.png')
N_SECONDS = int(os.getenv('N_SECONDS', 10))
PROFIT_Y_LIMIT = os.getenv('PROFIT_Y_LIMIT', None) # Set as tuple (min, max) or None
# ---------------------

def analyze_profits(input_path, output_path, n_seconds):
    if not os.path.exists(input_path):
        print(f"Error: File not found at {input_path}")
        return

    print(f"Loading file: {input_path}")
    try:
        # Load tab-separated file
        df = pd.read_csv(input_path, sep='\t', engine='python')
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    df.columns = df.columns.str.strip()
    
    # Preprocess timestamp: combine TRADETIME and TRADETIME_MSEC
    df['timestamp'] = pd.to_datetime(
        df['TRADETIME'] + '.' + df['TRADETIME_MSEC'].astype(str).str.zfill(3), 
        format='%H:%M:%S.%f'
    )
    
    # Create N-second interval bins
    df['interval'] = df['timestamp'].dt.floor(f'{n_seconds}s')
    
    # Get the last price in each interval for profit calculation
    last_price_per_interval = df.groupby('interval')['PRICE'].last()
    
    # Calculate profit for each row
    # BUY: Vol * (LastPrice - EntryPrice)
    # SELL: Vol * (EntryPrice - LastPrice)
    df = df.copy()
    df['last_p_in_interval'] = df['interval'].map(last_price_per_interval)
    
    df['buy_profit_val'] = 0.0
    df.loc[df['BUYSELL'] == 'BUY', 'buy_profit_val'] = df['QTY'] * (df['last_p_in_interval'] - df['PRICE'])
    
    df['sell_profit_val'] = 0.0
    df.loc[df['BUYSELL'] == 'SELL', 'sell_profit_val'] = df['QTY'] * (df['PRICE'] - df['last_p_in_interval'])
    
    # Aggregate by interval
    agg_df = df.groupby('interval').agg(
        price=('PRICE', 'last'),
        buy_profit=('buy_profit_val', 'sum'),
        sell_profit=('sell_profit_val', 'sum')
    ).reset_index()

    if agg_df.empty:
        print("No data found to process.")
        return

    # Plotting
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(14, 10))
    
    # Top Plot: Price
    ax1.plot(agg_df['interval'], agg_df['price'], color='black', label='Price', linewidth=1.5)
    ax1.set_ylabel('Price')
    ax1.legend(loc='upper right')
    ax1.grid(True, which='both', linestyle='--', alpha=0.5)
    
    # Vertical grid lines for both plots
    ax1.xaxis.grid(True, which='major', color='gray', linestyle='-', alpha=0.3)
    ax1.xaxis.set_tick_params(labelbottom=False)

    # Bottom Plot: Profits
    ax2.plot(agg_df['interval'], agg_df['buy_profit'], color='green', label='Sum Buy Profit', linewidth=1.5)
    ax2.plot(agg_df['interval'], agg_df['sell_profit'], color='red', label='Sum Sell Profit', linewidth=1.5)
    ax2.set_ylabel('Profit')
    ax2.legend(loc='upper right')
    ax2.grid(True, which='both', linestyle='--', alpha=0.5)
    ax2.xaxis.grid(True, which='major', color='gray', linestyle='-', alpha=0.3)

    if PROFIT_Y_LIMIT is not None:
        try:
            # Expecting string format like "(min,max)" from ENV
            limits = eval(PROFIT_Y_LIMIT)
            if isinstance(limits, (tuple, list)) and len(limits) == 2:
                ax2.set_ylim(limits[0], limits[1])
        except Exception as e:
            print(f"Warning: Could not parse PROFIT_Y_LIMIT '{PROFIT_Y_LIMIT}': {e}")

    plt.xticks(rotation=45)
    plt.xlabel('Time')
    plt.tight_layout()
    
    try:
        plt.savefig(output_path)
        print(f"Success! Graph saved to: {output_path}")
    except Exception as e:
        print(f"Error saving graph: {e}")

if __name__ == "__main__":
    analyze_profits(INPUT_FILE, OUTPUT_GRAPH, N_SECONDS)
