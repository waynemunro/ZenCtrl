'''
import pandas as pd
import numpy as np
import logging
from binance.client import Client
import os
import sys
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
API_KEY = os.getenv('BINANCE_API_KEY', "YOUR_API_KEY")
API_SECRET = os.getenv('BINANCE_API_SECRET', "YOUR_API_SECRET")
client = Client(API_KEY, API_SECRET)

# Optimization Log CSV Path - adjust as needed
OPTIMIZATION_LOG_CSV = 'optimization_log.csv' # Expects this in the same directory or provide full path

# --- Lenia OODA Parameters (Example - these should be optimized) ---
# These are just placeholders; actual parameters will be loaded from optimization_log.csv
DEFAULT_PARAMS = {
    'symbol': 'BTCUSDT',
    'timeframe': Client.KLINE_INTERVAL_15MINUTE,
    'ema_period': 20,
    'atr_period': 14,
    'atr_multiplier': 2.0,
    'momentum_period': 10,
    'rsi_period': 14,
    'rsi_oversold': 30,
    'rsi_overbought': 70,
    'lenia_r': 5,
    'lenia_t': 10,
    'lenia_b': [0.14, 0.26, 0.38, 0.33], # Example B values for Lenia
    'lenia_m': 0.15,
    'lenia_s': 0.015,
    'lookback_candles': 200, # Number of candles to fetch for initial calculations
    'trade_amount_usd': 1000 # USD value per trade
}

# --- Lenia Cellular Automaton ---
def lenia_update(grid, R, T, B, m, s):
    kh, kw = noyau_g(R)
    K = np.fft.fft2(np.fft.ifftshift(kh * kw))
    
    f_grid = np.fft.fft2(grid)
    g = np.real(np.fft.ifft2(f_grid * K))
    
    g_norm = (g - g.min()) / (g.max() - g.min() + 1e-9) # Normalize to [0,1]
    
    # Growth function G(u) = 2 * exp(-((u - m) / s)^2 / 2) - 1
    growth = 2 * np.exp(-((g_norm - m)**2) / (2 * s**2)) - 1
    
    # Apply birth/survival rules (simplified for this context)
    # This is a conceptual adaptation. A direct mapping of Lenia's B/S rules to a 1D signal is non-trivial.
    # Here, we'll use the growth value directly, scaled by a factor derived from B.
    # For simplicity, let's use the average of B as a scaling factor.
    b_factor = np.mean(B) if isinstance(B, list) else B # Handle single B value or list
    
    # Update rule: grid_new = grid + (1/T) * growth * b_factor
    # We need to ensure the update is bounded and makes sense for a financial signal.
    # Let's assume 'grid' here is a 1D array representing a feature over time.
    # The update will be applied to the latest value of this feature.
    
    # For a 1D signal (e.g., price or indicator), Lenia's 2D update needs adaptation.
    # Let's assume 'grid' is the latest value of a signal we want to evolve with Lenia dynamics.
    # The 'growth' is calculated based on this 'grid' value (normalized).
    # The update rule becomes: new_value = current_value + (1/T) * growth * b_factor
    # This is a conceptual interpretation.
    
    # In a trading context, we might apply Lenia to an indicator series.
    # For this example, let's return the 'growth' value as a Lenia-based signal.
    # The 'grid' input to this function would be the current state of some market feature.
    return growth # Returning the raw growth value for now

def noyau_g(R, n=1):
    x = np.arange(-R, R+1)
    r = np.sqrt(x**2 + x[:,np.newaxis]**2)
    K = (r < R) * (1 - r/R)**4 * (1 + 4*r/R)
    K = K / np.sum(K)
    return K, K.T # Simplified for conceptual use

# --- Data Fetching and Preparation ---
def fetch_data(symbol, timeframe, lookback_candles):
    logging.info(f"Fetching {lookback_candles} candles for {symbol} on {timeframe} timeframe.")
    # Calculate start time for fetching data
    # Binance API max limit is 1000 candles per request for klines
    # For longer history, multiple requests might be needed or a longer 'since' string.
    # For simplicity, fetching 'lookback_candles' up to 1000.
    
    # Calculate the start_str. Example: "1 day ago UTC", "1 week ago UTC"
    # For 15-minute candles, 200 candles = 200 * 15 minutes = 3000 minutes = 50 hours
    # We need to be more precise if 'lookback_candles' is large.
    
    # Max 1000 candles per request. If lookback_candles > 1000, this needs pagination.
    # For now, assume lookback_candles <= 1000
    if lookback_candles > 1000:
        logging.warning("lookback_candles > 1000, fetching only last 1000 due to API limit. Implement pagination for more.")
        limit = 1000
    else:
        limit = lookback_candles

    try:
        klines = client.get_klines(symbol=symbol, interval=timeframe, limit=limit)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                           'close_time', 'quote_asset_volume', 'number_of_trades', 
                                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        logging.info(f"Successfully fetched {len(df)} candles for {symbol}.")
        return df
    except Exception as e:
        logging.error(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- Indicator Calculations ---
def calculate_indicators(df, params):
    df['EMA'] = df['close'].ewm(span=params['ema_period'], adjust=False).mean()
    
    # ATR
    df['TR'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    df['ATR'] = df['TR'].ewm(span=params['atr_period'], adjust=False).mean()
    
    # Momentum
    df['Momentum'] = df['close'] - df['close'].shift(params['momentum_period'])
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=params['rsi_period'], adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=params['rsi_period'], adjust=False).mean()
    rs = gain / (loss + 1e-9) # Add epsilon to prevent division by zero
    df['RSI'] = 100 - (100 / (1 + rs))

    # Lenia Signal (Conceptual - applied to RSI for this example)
    # We need a 1D 'grid' for Lenia. Let's use normalized RSI.
    # This is highly experimental and needs proper design.
    # For simplicity, we'll apply a Lenia-like update to the RSI signal itself or a derivative.
    # Let's assume the 'lenia_update' function returns a value that can be used as a signal.
    # The 'grid' input to lenia_update would be the current RSI value (normalized).
    
    # Normalize RSI to [0,1] to act as 'grid' for Lenia
    rsi_norm = (df['RSI'] - df['RSI'].min()) / (df['RSI'].max() - df['RSI'].min() + 1e-9)
    
    # Apply Lenia update conceptually. This is not a direct application of 2D Lenia.
    # We are taking the 'growth' value from Lenia based on the current normalized RSI.
    # This requires careful thought on how to map Lenia's dynamics to a 1D financial signal.
    # For this example, let's assume lenia_update takes the current rsi_norm value.
    # The parameters R, T, B, m, s are from the 'params' dict.
    
    # This is a placeholder for a more sophisticated Lenia signal integration.
    # We might apply Lenia to a series of indicator values over a small window.
    # For now, let's generate a 'lenia_signal' based on the current RSI.
    # This is a conceptual step and needs refinement.
    # The 'grid' for lenia_update should ideally be a small 1D array (e.g., last few RSI values).
    # For simplicity, we pass the single current normalized RSI value.
    # The lenia_update function as defined returns a 'growth' value.
    
    # This is a simplification: applying Lenia to each RSI point individually.
    df['LeniaSignal'] = rsi_norm.apply(lambda x: lenia_update(x, 
                                                              params['lenia_r'], 
                                                              params['lenia_t'], 
                                                              params['lenia_b'], 
                                                              params['lenia_m'], 
                                                              params['lenia_s']))
    return df

# --- OODA Loop Logic ---
def ooda_loop_decision(df_point, params):
    # Observe: Current market data (df_point)
    # Orient: Based on indicators
    
    # Signals from indicators
    signal_ma = 1 if df_point['close'] > df_point['EMA'] else -1 if df_point['close'] < df_point['EMA'] else 0
    signal_atr_volatility = df_point['ATR'] # Not a direct buy/sell, but context
    signal_mom = 1 if df_point['Momentum'] > 0 else -1 if df_point['Momentum'] < 0 else 0
    signal_rsi = 0
    if df_point['RSI'] < params['rsi_oversold']:
        signal_rsi = 1 # Oversold, potential buy
    elif df_point['RSI'] > params['rsi_overbought']:
        signal_rsi = -1 # Overbought, potential sell
        
    # Lenia Signal (using the pre-calculated LeniaSignal column)
    # This signal is already a 'growth' value. We need to interpret it.
    # For example, positive growth -> buy, negative growth -> sell.
    signal_lenia = 0
    if df_point['LeniaSignal'] > 0.1: # Threshold for Lenia signal (example)
        signal_lenia = 1
    elif df_point['LeniaSignal'] < -0.1:
        signal_lenia = -1

    # Decide: Combine signals (simple consensus for now)
    # More sophisticated decision logic can be implemented here (e.g., weighted, rule-based)
    consensus_value = signal_ma + signal_mom + signal_rsi + signal_lenia
    
    action = "HOLD"
    if consensus_value >= 2: # Example threshold for BUY
        action = "BUY"
    elif consensus_value <= -2: # Example threshold for SELL
        action = "SELL"
        
    # Act: (Handled by the simulation loop based on 'action')
    return action, consensus_value, {
        "MA": signal_ma, "Momentum": signal_mom, "RSI": signal_rsi, "Lenia": signal_lenia,
        "ATR": signal_atr_volatility, "Close": df_point['close'], "EMA": df_point['EMA']
    }

# --- Backtesting/Simulation Engine ---
def run_simulation(df, params, initial_balance_usd=10000):
    logging.info("Starting simulation...")
    balance_usd = initial_balance_usd
    position_asset = 0  # Amount of base asset (e.g., BTC)
    entry_price = 0
    trades_log = []
    
    df_with_indicators = calculate_indicators(df.copy(), params)
    
    if df_with_indicators.empty or len(df_with_indicators) < params['lookback_candles']:
        logging.warning("Not enough data to run simulation after indicator calculation.")
        return pd.DataFrame(), 0, 0

    # Iterate through each data point (candle)
    for i in range(params['lookback_candles'] -1, len(df_with_indicators)): # Start after initial lookback period for indicators
        current_point = df_with_indicators.iloc[i]
        action, consensus, signals = ooda_loop_decision(current_point, params)
        
        current_price = current_point['close']
        
        # Trading Logic
        if action == "BUY" and position_asset == 0: # Buy only if not already in position
            amount_to_buy_asset = params['trade_amount_usd'] / current_price
            position_asset += amount_to_buy_asset
            balance_usd -= params['trade_amount_usd'] # Assume full use of trade_amount_usd
            entry_price = current_price
            trades_log.append({
                'timestamp': current_point.name, 'action': 'BUY', 'price': current_price, 
                'amount_asset': amount_to_buy_asset, 'amount_usd': params['trade_amount_usd'],
                'balance_usd': balance_usd, 'position_asset': position_asset,
                'consensus': consensus, **signals
            })
            logging.info(f"BUY: {amount_to_buy_asset:.6f} {params['symbol']} at {current_price:.2f}")

        elif action == "SELL" and position_asset > 0: # Sell only if in position
            sell_value_usd = position_asset * current_price
            balance_usd += sell_value_usd
            amount_sold_asset = position_asset
            position_asset = 0
            profit = sell_value_usd - (amount_sold_asset * entry_price) # Simple profit calc
            trades_log.append({
                'timestamp': current_point.name, 'action': 'SELL', 'price': current_price,
                'amount_asset': amount_sold_asset, 'amount_usd': sell_value_usd,
                'balance_usd': balance_usd, 'position_asset': position_asset, 'profit_usd': profit,
                'consensus': consensus, **signals
            })
            logging.info(f"SELL: {amount_sold_asset:.6f} {params['symbol']} at {current_price:.2f}, Profit: {profit:.2f}")
            entry_price = 0
            
    # Final portfolio value
    final_portfolio_value = balance_usd + (position_asset * df_with_indicators['close'].iloc[-1])
    profit_or_loss = final_portfolio_value - initial_balance_usd
    
    logging.info(f"Simulation finished. Initial Balance: {initial_balance_usd:.2f} USD")
    logging.info(f"Final Portfolio Value: {final_portfolio_value:.2f} USD")
    logging.info(f"Total Profit/Loss: {profit_or_loss:.2f} USD")
    
    return pd.DataFrame(trades_log), final_portfolio_value, profit_or_loss

# --- Parameter Optimization (Conceptual) ---
# In a real scenario, this would involve running simulations with many parameter sets.
# For this script, we'll load pre-optimized parameters from a CSV.
def load_optimized_parameters(csv_path, symbol, timeframe_str):
    '''
    Loads optimized parameters from a CSV file.
    The CSV should have columns like: symbol, timeframe, ema_period, atr_period, ..., score (or PnL)
    It will pick the row with the best score for the given symbol and timeframe.
    '''
    try:
        df_opt = pd.read_csv(csv_path)
        # Filter for the specific symbol and timeframe
        # Ensure timeframe_str matches the format in CSV (e.g., '15m', '1h')
        # The Client.KLINE_INTERVAL_15MINUTE is '15m'. We might need a mapping if CSV stores it differently.
        
        # Assuming timeframe_str is like '15m', '1h' etc.
        filtered_params = df_opt[(df_opt['symbol'] == symbol) & (df_opt['timeframe'] == timeframe_str)]
        
        if filtered_params.empty:
            logging.warning(f"No optimized parameters found for {symbol} on {timeframe_str} in {csv_path}. Using default.")
            return None
            
        # Sort by a 'score' or 'profit_usd' column (assuming higher is better)
        # Adjust 'score_column_name' as per your CSV
        score_column_name = 'profit_usd' # Or 'score', 'fitness', etc.
        if score_column_name not in filtered_params.columns:
            logging.warning(f"Score column '{score_column_name}' not found in {csv_path}. Using first found entry.")
            best_params_series = filtered_params.iloc[0]
        else:
            best_params_series = filtered_params.sort_values(by=score_column_name, ascending=False).iloc[0]
        
        # Convert series to dict and ensure types are correct
        best_params_dict = best_params_series.to_dict()
        
        # Type conversions (example, adjust as needed based on CSV content)
        int_keys = ['ema_period', 'atr_period', 'momentum_period', 'rsi_period', 'lenia_r', 'lenia_t', 'lookback_candles']
        float_keys = ['atr_multiplier', 'rsi_oversold', 'rsi_overbought', 'lenia_m', 'lenia_s', 'trade_amount_usd']
        
        for key in int_keys:
            if key in best_params_dict:
                best_params_dict[key] = int(best_params_dict[key])
        for key in float_keys:
            if key in best_params_dict:
                best_params_dict[key] = float(best_params_dict[key])
        
        # Handle 'lenia_b' which might be a string representation of a list
        if 'lenia_b' in best_params_dict and isinstance(best_params_dict['lenia_b'], str):
            try:
                # Safely evaluate string representation of list: e.g., "[0.1, 0.2]"
                import ast
                best_params_dict['lenia_b'] = ast.literal_eval(best_params_dict['lenia_b'])
            except (ValueError, SyntaxError):
                logging.error(f"Could not parse 'lenia_b' string: {best_params_dict['lenia_b']}. Using default.")
                best_params_dict['lenia_b'] = DEFAULT_PARAMS['lenia_b']

        logging.info(f"Loaded optimized parameters for {symbol} ({timeframe_str}): {best_params_dict}")
        return best_params_dict
        
    except FileNotFoundError:
        logging.warning(f"Optimization log CSV '{csv_path}' not found. Using default parameters.")
        return None
    except Exception as e:
        logging.error(f"Error loading optimized parameters: {e}. Using default parameters.")
        return None

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Lenia OODA Strategy Bot - Backtesting Mode")

    # --- Parameters Setup ---
    # Try to load optimized parameters, otherwise use defaults
    # Map Client.KLINE_INTERVAL_15MINUTE ('15m') to string for CSV lookup
    timeframe_str_map = {
        Client.KLINE_INTERVAL_1MINUTE: '1m', Client.KLINE_INTERVAL_3MINUTE: '3m',
        Client.KLINE_INTERVAL_5MINUTE: '5m', Client.KLINE_INTERVAL_15MINUTE: '15m',
        Client.KLINE_INTERVAL_30MINUTE: '30m', Client.KLINE_INTERVAL_1HOUR: '1h',
        Client.KLINE_INTERVAL_2HOUR: '2h', Client.KLINE_INTERVAL_4HOUR: '4h',
        Client.KLINE_INTERVAL_6HOUR: '6h', Client.KLINE_INTERVAL_8HOUR: '8h',
        Client.KLINE_INTERVAL_12HOUR: '12h', Client.KLINE_INTERVAL_1DAY: '1d',
        Client.KLINE_INTERVAL_3DAY: '3d', Client.KLINE_INTERVAL_1WEEK: '1w',
        Client.KLINE_INTERVAL_1MONTH: '1M'
    }
    current_timeframe_str = timeframe_str_map.get(DEFAULT_PARAMS['timeframe'], DEFAULT_PARAMS['timeframe'])

    # Attempt to load optimized params
    # The OPTIMIZATION_LOG_CSV path might need to be adjusted if this script is moved
    # For example, if it's in a parent directory: os.path.join(os.path.dirname(__file__), '..', OPTIMIZATION_LOG_CSV)
    
    # Construct path to CSV relative to this script's location
    # This assumes OPTIMIZATION_LOG_CSV is in the same directory as this script.
    # If the script is moved, this path might need to be made absolute or more robust.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(script_dir, OPTIMIZATION_LOG_CSV) # Default if not found elsewhere
    
    # Check if OPTIMIZATION_LOG_CSV exists at the script's location or if it's an absolute path
    if not os.path.exists(OPTIMIZATION_LOG_CSV) and not os.path.isabs(OPTIMIZATION_LOG_CSV):
        # If not found and not absolute, assume it's relative to script_dir
        effective_csv_path = csv_file_path
    else:
        # If it exists at OPTIMIZATION_LOG_CSV (could be relative to CWD or absolute) or is absolute
        effective_csv_path = OPTIMIZATION_LOG_CSV

    logging.info(f"Attempting to load optimization log from: {effective_csv_path}")

    strategy_params = load_optimized_parameters(effective_csv_path, 
                                                DEFAULT_PARAMS['symbol'], 
                                                current_timeframe_str)
    if strategy_params is None:
        strategy_params = DEFAULT_PARAMS.copy() # Use a copy to avoid modifying defaults
        logging.info("Using default parameters for the simulation.")
    else:
        # Ensure all necessary keys from DEFAULT_PARAMS are present, fill with defaults if missing
        for key, value in DEFAULT_PARAMS.items():
            if key not in strategy_params:
                strategy_params[key] = value
        logging.info("Successfully used loaded/merged parameters for the simulation.")

    # --- Fetch Data ---
    # Adjust lookback_candles based on what indicators need + some buffer
    # For example, if max period is EMA (20) or Momentum (10), lookback_candles=200 is plenty.
    # The simulation loop starts after 'lookback_candles' to ensure indicators are mature.
    # So, fetch enough data for indicators to initialize.
    # The `calculate_indicators` function uses `df.copy()`, so original df is safe.
    # The simulation loop itself starts from `params['lookback_candles'] - 1`.
    # This means we need at least `lookback_candles` for the indicators to be calculated on.
    # And then the simulation runs on the subsequent data.
    # So, if `lookback_candles` is 200, we fetch 200 candles. Indicators are calculated on these.
    # The loop `for i in range(params['lookback_candles'] -1, len(df_with_indicators))`
    # will effectively start processing from the last point of the initial 200 candles,
    # which is fine as indicators up to that point are available.

    historical_data = fetch_data(strategy_params['symbol'], 
                                 strategy_params['timeframe'], 
                                 strategy_params['lookback_candles'] + 150) # Fetch more for simulation run
                                                                          # e.g., 200 for init, 150 for sim
    
    if not historical_data.empty and len(historical_data) > strategy_params['lookback_candles']:
        # --- Run Simulation ---
        trades, final_value, pnl = run_simulation(historical_data, strategy_params, initial_balance_usd=10000)
        
        logging.info(f"\n--- Simulation Summary for {strategy_params['symbol']} ({current_timeframe_str}) ---")
        logging.info(f"Parameters Used: {strategy_params}")
        logging.info(f"Initial Balance: 10000.00 USD")
        logging.info(f"Final Portfolio Value: {final_value:.2f} USD")
        logging.info(f"Total Profit/Loss: {pnl:.2f} USD")
        
        if not trades.empty:
            logging.info(f"Number of trades: {len(trades[trades['action']=='SELL'])}") # Count sell trades for round trips
            # logging.info("\nTrades Log:")
            # print(trades.to_string()) # Using print for better table format if needed
            
            # Save trades to CSV
            trades_csv_path = f"trades_log_{strategy_params['symbol']}_{current_timeframe_str}.csv"
            trades.to_csv(trades_csv_path, index=False)
            logging.info(f"Trades log saved to {trades_csv_path}")
        else:
            logging.info("No trades were executed.")
            
    else:
        logging.error("Could not fetch sufficient historical data to run the simulation.")

    logging.info("Strategy execution finished.")
'''
