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

# --- Configuration Constants (can be overridden by passed-in params) ---
DEFAULT_OPTIMIZATION_LOG_CSV = 'optimization_log.csv'

# --- Binance Client Initialization ---
def initialize_binance_client(api_key=None, api_secret=None):
    """Initializes and returns a Binance client."""
    key = api_key or os.getenv('BINANCE_API_KEY')
    secret = api_secret or os.getenv('BINANCE_API_SECRET')
    if not key or not secret:
        logging.warning("Binance API key or secret not provided or found in environment variables. Client may not work for live operations.")
    return Client(key, secret)

# --- Lenia OODA Parameters (Example - these should be optimized) ---
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
    
    b_factor = np.mean(B) if isinstance(B, list) else B # Handle single B value or list
    
    return growth # Returning the raw growth value for now

def noyau_g(R, n=1):
    x = np.arange(-R, R+1)
    r = np.sqrt(x**2 + x[:,np.newaxis]**2)
    K = (r < R) * (1 - r/R)**4 * (1 + 4*r/R)
    K = K / np.sum(K)
    return K, K.T # Simplified for conceptual use

# --- Data Fetching and Preparation ---
def fetch_data(binance_client, symbol, timeframe, lookback_candles):
    logging.info(f"Fetching {lookback_candles} candles for {symbol} on {timeframe} timeframe.")
    if lookback_candles > 1000:
        logging.warning("lookback_candles > 1000, fetching only last 1000 due to API limit. Implement pagination for more.")
        limit = 1000
    else:
        limit = lookback_candles

    try:
        klines = binance_client.get_klines(symbol=symbol, interval=timeframe, limit=limit)
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
    
    df['TR'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    df['ATR'] = df['TR'].ewm(span=params['atr_period'], adjust=False).mean()
    
    df['Momentum'] = df['close'] - df['close'].shift(params['momentum_period'])
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=params['rsi_period'], adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=params['rsi_period'], adjust=False).mean()
    rs = gain / (loss + 1e-9) # Add epsilon to prevent division by zero
    df['RSI'] = 100 - (100 / (1 + rs))

    rsi_norm = (df['RSI'] - df['RSI'].min()) / (df['RSI'].max() - df['RSI'].min() + 1e-9)
    
    df['LeniaSignal'] = rsi_norm.apply(lambda x: lenia_update(x, 
                                                              params['lenia_r'], 
                                                              params['lenia_t'], 
                                                              params['lenia_b'], 
                                                              params['lenia_m'], 
                                                              params['lenia_s']))
    return df

# --- OODA Loop Logic ---
def ooda_loop_decision(df_point, params, zen_signal=0.0, zen_weight=0.0): # Added zen_signal and zen_weight
    signal_ma = 1 if df_point['close'] > df_point['EMA'] else -1 if df_point['close'] < df_point['EMA'] else 0
    signal_atr_volatility = df_point['ATR']
    signal_mom = 1 if df_point['Momentum'] > 0 else -1 if df_point['Momentum'] < 0 else 0
    signal_rsi = 0
    if df_point['RSI'] < params['rsi_oversold']:
        signal_rsi = 1
    elif df_point['RSI'] > params['rsi_overbought']:
        signal_rsi = -1
        
    signal_lenia = 0
    if df_point['LeniaSignal'] > 0.1:
        signal_lenia = 1
    elif df_point['LeniaSignal'] < -0.1:
        signal_lenia = -1

    consensus_value = signal_ma + signal_mom + signal_rsi + signal_lenia + (zen_signal * zen_weight)
    
    action = "HOLD"
    if consensus_value >= 2:
        action = "BUY"
    elif consensus_value <= -2:
        action = "SELL"
        
    return action, consensus_value, {
        "MA": signal_ma, "Momentum": signal_mom, "RSI": signal_rsi, "Lenia": signal_lenia,
        "ZEN": zen_signal, "ZEN_WEIGHT": zen_weight,
        "ATR": signal_atr_volatility, "Close": df_point['close'], "EMA": df_point['EMA']
    }

# --- Backtesting/Simulation Engine ---
def run_simulation(df, params, initial_balance_usd=10000, 
                   zen_signal_enabled=False, zen_weight=0.0, 
                   zen_predictor_func=None, zen_prediction_frequency=1,
                   binance_client=None): 
    logging.info("Starting simulation...")
    balance_usd = initial_balance_usd
    position_asset = 0
    entry_price = 0
    trades_log = []
    current_zen_signal = 0.0
    
    df_with_indicators = calculate_indicators(df.copy(), params)
    
    if df_with_indicators.empty or len(df_with_indicators) < params['lookback_candles']:
        logging.warning("Not enough data to run simulation after indicator calculation.")
        return pd.DataFrame(), 0, 0

    for i in range(params['lookback_candles'] -1, len(df_with_indicators)):
        current_point = df_with_indicators.iloc[i]
        
        if zen_signal_enabled and zen_predictor_func is not None:
            if (i - (params['lookback_candles'] -1)) % zen_prediction_frequency == 0:
                # Pass the entire df_with_indicators and the current index i
                # The zen_predictor_func (wrapper in gradio_app) will handle slicing.
                current_zen_signal = zen_predictor_func(df_with_indicators, i) 
                logging.info(f"ZEN signal generated at step {i}: {current_zen_signal}")

        action, consensus, signals = ooda_loop_decision(current_point, params, 
                                                        zen_signal=current_zen_signal if zen_signal_enabled else 0.0, 
                                                        zen_weight=zen_weight if zen_signal_enabled else 0.0)
        
        current_price = current_point['close']
        
        if action == "BUY" and position_asset == 0:
            amount_to_buy_asset = params['trade_amount_usd'] / current_price
            position_asset += amount_to_buy_asset
            balance_usd -= params['trade_amount_usd']
            entry_price = current_price
            trades_log.append({
                'timestamp': current_point.name, 'action': 'BUY', 'price': current_price, 
                'amount_asset': amount_to_buy_asset, 'amount_usd': params['trade_amount_usd'],
                'balance_usd': balance_usd, 'position_asset': position_asset,
                'consensus': consensus, 'active_zen_signal': current_zen_signal if zen_signal_enabled else None,
                **signals
            })
            logging.info(f"BUY: {amount_to_buy_asset:.6f} {params['symbol']} at {current_price:.2f}")

        elif action == "SELL" and position_asset > 0:
            sell_value_usd = position_asset * current_price
            balance_usd += sell_value_usd
            amount_sold_asset = position_asset
            position_asset = 0
            profit = sell_value_usd - (amount_sold_asset * entry_price)
            trades_log.append({
                'timestamp': current_point.name, 'action': 'SELL', 'price': current_price,
                'amount_asset': amount_sold_asset, 'amount_usd': sell_value_usd,
                'balance_usd': balance_usd, 'position_asset': position_asset, 'profit_usd': profit,
                'consensus': consensus, 'active_zen_signal': current_zen_signal if zen_signal_enabled else None,
                **signals
            })
            logging.info(f"SELL: {amount_sold_asset:.6f} {params['symbol']} at {current_price:.2f}, Profit: {profit:.2f}")
            entry_price = 0
            
    final_portfolio_value = balance_usd + (position_asset * df_with_indicators['close'].iloc[-1])
    profit_or_loss = final_portfolio_value - initial_balance_usd
    
    logging.info(f"Simulation finished. Initial Balance: {initial_balance_usd:.2f} USD")
    logging.info(f"Final Portfolio Value: {final_portfolio_value:.2f} USD")
    logging.info(f"Total Profit/Loss: {profit_or_loss:.2f} USD")
    
    return pd.DataFrame(trades_log), final_portfolio_value, profit_or_loss

# --- Parameter Optimization (Conceptual) ---
def load_optimized_parameters(csv_path, symbol, timeframe_str, default_params_dict):
    try:
        df_opt = pd.read_csv(csv_path)
        filtered_params = df_opt[(df_opt['symbol'] == symbol) & (df_opt['timeframe'] == timeframe_str)]
        
        if filtered_params.empty:
            logging.warning(f"No optimized parameters found for {symbol} on {timeframe_str} in {csv_path}. Using default.")
            return default_params_dict.copy()
            
        score_column_name = 'profit_usd'
        if score_column_name not in filtered_params.columns:
            logging.warning(f"Score column '{score_column_name}' not found in {csv_path}. Using first found entry.")
            best_params_series = filtered_params.iloc[0]
        else:
            best_params_series = filtered_params.sort_values(by=score_column_name, ascending=False).iloc[0]
        
        best_params_dict = best_params_series.to_dict()
        
        int_keys = ['ema_period', 'atr_period', 'momentum_period', 'rsi_period', 'lenia_r', 'lenia_t', 'lookback_candles']
        float_keys = ['atr_multiplier', 'rsi_oversold', 'rsi_overbought', 'lenia_m', 'lenia_s', 'trade_amount_usd']
        
        for key in int_keys:
            if key in best_params_dict:
                best_params_dict[key] = int(best_params_dict[key])
        for key in float_keys:
            if key in best_params_dict:
                best_params_dict[key] = float(best_params_dict[key])
        
        if 'lenia_b' in best_params_dict and isinstance(best_params_dict['lenia_b'], str):
            try:
                import ast
                best_params_dict['lenia_b'] = ast.literal_eval(best_params_dict['lenia_b'])
            except (ValueError, SyntaxError):
                logging.error(f"Could not parse 'lenia_b' string: {best_params_dict['lenia_b']}. Using default.")
                best_params_dict['lenia_b'] = default_params_dict['lenia_b']

        final_params = default_params_dict.copy()
        final_params.update(best_params_dict)

        logging.info(f"Loaded and merged optimized parameters for {symbol} ({timeframe_str}): {final_params}")
        return final_params
        
    except FileNotFoundError:
        logging.warning(f"Optimization log CSV '{csv_path}' not found. Using default parameters.")
        return default_params_dict.copy()
    except Exception as e:
        logging.error(f"Error loading optimized parameters: {e}. Using default parameters.")
        return default_params_dict.copy()

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Lenia OODA Strategy Bot - Backtesting Mode")

    client = initialize_binance_client()

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

    script_dir = os.path.dirname(os.path.abspath(__file__))
    optimization_log_filename = DEFAULT_OPTIMIZATION_LOG_CSV 
    
    if os.path.isabs(optimization_log_filename):
        effective_csv_path = optimization_log_filename
    else:
        effective_csv_path = os.path.join(script_dir, optimization_log_filename)

    logging.info(f"Attempting to load optimization log from: {effective_csv_path}")

    strategy_params = load_optimized_parameters(effective_csv_path, 
                                                DEFAULT_PARAMS['symbol'], 
                                                current_timeframe_str,
                                                DEFAULT_PARAMS)
    logging.info(f"Using parameters for simulation: {strategy_params}")

    historical_data = fetch_data(client, 
                                 strategy_params['symbol'], 
                                 strategy_params['timeframe'], 
                                 strategy_params['lookback_candles'] + 150)
    
    def placeholder_zen_predictor(market_data, index):
        if market_data.iloc[index]['close'] > market_data.iloc[index]['open']:
            return 0.5
        elif market_data.iloc[index]['close'] < market_data.iloc[index]['open']:
            return -0.5
        return 0.0

    if not historical_data.empty and len(historical_data) > strategy_params['lookback_candles']:
        trades, final_value, pnl = run_simulation(historical_data, 
                                                  strategy_params, 
                                                  initial_balance_usd=10000,
                                                  binance_client=client)
        
        logging.info(f"\n--- Simulation Summary for {strategy_params['symbol']} ({current_timeframe_str}) ---")
        logging.info(f"Parameters Used: {strategy_params}")
        logging.info(f"Initial Balance: 10000.00 USD")
        logging.info(f"Final Portfolio Value: {final_value:.2f} USD")
        logging.info(f"Total Profit/Loss: {pnl:.2f} USD")
        
        if not trades.empty:
            logging.info(f"Number of trades: {len(trades[trades['action']=='SELL'])}")
            trades_csv_path = f"trades_log_{strategy_params['symbol']}_{current_timeframe_str}.csv"
            trades.to_csv(trades_csv_path, index=False)
            logging.info(f"Trades log saved to {trades_csv_path}")
        else:
            logging.info("No trades were executed.")
            
    else:
        logging.error("Could not fetch sufficient historical data to run the simulation.")

    logging.info("Strategy execution finished.")
