import pandas as pd
import numpy as np
import logging
from binance.client import Client
import os
import sys
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv # Add this import
from binance import ThreadedWebsocketManager
import threading

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')) # Add this line

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration Constants (can be overridden by passed-in params) ---
DEFAULT_OPTIMIZATION_LOG_CSV = 'optimization_log.csv'

# --- Binance Client Initialization ---
def initialize_binance_client(api_key=None, api_secret=None, testnet=False, tld='com', timeout=30):
    """
    Initializes and returns a Binance client with improved configuration options.
    
    Args:
        api_key: Binance API key (optional if in env vars)
        api_secret: Binance API secret (optional if in env vars)
        testnet: Whether to use the testnet (sandbox) environment
        tld: Top level domain for the Binance API (com, us, etc.)
        timeout: Request timeout in seconds
        
    Returns:
        Initialized Binance client or None if initialization fails
    """
    key = api_key or os.getenv('BINANCE_API_KEY')
    secret = api_secret or os.getenv('BINANCE_API_SECRET')
    
    if not key or not secret:
        logging.warning("Binance API key or secret not provided or found in environment variables.")
        logging.warning("For testing, you can use the testnet with demo API keys.")
        logging.warning("Visit https://testnet.binance.vision/ to get testnet API keys.")
    
    try:
        client = Client(
            api_key=key,
            api_secret=secret,
            testnet=testnet,
            tld=tld,
            requests_params={'timeout': timeout} # Correct way to pass timeout
        )
        
        # Test the connection with a simple request
        if key and secret:
            try:
                account_info = client.get_account()
                if account_info:
                    logging.info(f"Successfully connected to Binance API. Account status: {account_info.get('status', 'N/A')}")
            except Exception as e:
                logging.warning(f"API connection test failed: {e}")
                # Continue anyway as the client might still work for public endpoints
        
        return client
    except Exception as e:
        logging.error(f"Error initializing Binance client: {e}")
        return None

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
def lenia_update(grid, r, t, b, m, s):
    # Debugging: Check the shape and content of the grid
    if not isinstance(grid, np.ndarray):
        print(f"[Error] Invalid input type for lenia_update: {type(grid)}")
        return np.zeros((1, 1))
    
    if grid is None or grid.size == 0:
        print("[Error] Grid is empty or None in lenia_update.")
        return np.zeros_like(grid)  # Return a grid of zeros to avoid errors

    try:
        f_grid = np.fft.fft2(grid)
        kh, kw = noyau_g(r)
        K = np.fft.fft2(np.fft.ifftshift(kh * kw))
        b_factor = np.mean(b) if isinstance(b, list) else b  # Handle single B value or list
        e = np.fft.ifft2(f_grid * K).real  # Example logic for `e`
        return e  # Return the updated grid
    except Exception as e:
        print(f"[Error] Exception in lenia_update: {e}")
        return np.zeros_like(grid)  # Return a grid of zeros to avoid errors

def noyau_g(R, n=1):
    x = np.arange(-R, R+1)
    r = np.sqrt(x**2 + x[:,np.newaxis]**2)
    K = (r < R) * (1 - r/R)**4 * (1 + 4*r/R)
    K = K / np.sum(K)
    return K, K.T # Simplified for conceptual use

# --- Data Fetching and Preparation ---
def fetch_data(binance_client, symbol, timeframe, lookback_candles):
    logging.info(f"Fetching {lookback_candles} candles for {symbol} on {timeframe} timeframe.")
    
    # Handle case where client is None (API keys not provided)
    if binance_client is None:
        logging.error("Binance client is None! Cannot fetch data. Please provide valid API keys.")
        # Return empty DataFrame with appropriate structure
        empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        empty_df.index.name = 'timestamp'
        return empty_df
    
    # Maximum records per API call
    MAX_LIMIT = 1000
    
    try:
        all_klines = []
        
        # If we need more than MAX_LIMIT candles, we need to make multiple calls
        if lookback_candles > MAX_LIMIT:
            # We'll use pagination to fetch all required candles
            remaining = lookback_candles
            end_time = None  # Start from the most recent candle
            
            while remaining > 0:
                # Calculate how many candles to fetch in this iteration
                limit = min(remaining, MAX_LIMIT)
                
                # Fetch klines
                params = {
                    'symbol': symbol,
                    'interval': timeframe,
                    'limit': limit
                }
                
                # Add end_time if we have one (not for the first call)
                if end_time:
                    params['endTime'] = end_time
                
                klines = binance_client.get_klines(**params)
                
                if not klines:
                    break  # No more data available
                
                # Add to our collection
                all_klines = klines + all_klines
                
                # Update for next iteration
                remaining -= len(klines)
                
                # If we received fewer candles than requested, we've reached the beginning
                if len(klines) < limit:
                    break
                
                # Set the end_time for the next request to be the start time of the first candle in this batch
                # Subtract 1 ms to avoid duplicate candle
                end_time = klines[0][0] - 1
                
                # Rate limiting - sleep to avoid hitting API limits
                time.sleep(0.1)
                
                logging.info(f"Fetched {len(klines)} candles, {remaining} remaining to fetch")
        else:
            # If requesting fewer than MAX_LIMIT candles, make a single call
            all_klines = binance_client.get_klines(symbol=symbol, interval=timeframe, limit=lookback_candles)
        
        # Process the klines into a DataFrame
        if all_klines:
            df = pd.DataFrame(all_klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                            'close_time', 'quote_asset_volume', 'number_of_trades', 
                                            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            logging.info(f"Successfully fetched {len(df)} candles for {symbol}.")
            return df
        else:
            logging.warning(f"No data returned for {symbol} on {timeframe}.")
            empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
            empty_df.index.name = 'timestamp'
            return empty_df
            
    except Exception as e:
        logging.error(f"Error fetching klines for {symbol}: {e}")
        # Provide more specific error messages for common issues
        if "APIError(code=-2015)" in str(e):
            logging.error("Invalid API keys or authentication failed. Please check your API keys.")
        elif "APIError(code=-1121)" in str(e):
            logging.error(f"Invalid symbol: {symbol}. The trading pair may not exist on Binance.")
        elif "APIError(code=-1003)" in str(e):
            logging.error("Too many requests. Rate limit exceeded. Please wait and try again.")
        elif "APIError(code=-1010)" in str(e):
            logging.error("Insufficient funds or other trading error.")
        elif "APIError(code=-1022)" in str(e):
            logging.error("Invalid signature or API key format.")
            
        # Return empty DataFrame with appropriate structure
        empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        empty_df.index.name = 'timestamp'
        return empty_df

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
    
    df['LeniaSignal'] = rsi_norm.apply(lambda x: lenia_update(np.array([x]), 
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

# --- WebSocket Data Streaming for Real-time Trading ---
# Note: To use WebSocket features, you need to install the websocket-client package:
# pip install websocket-client python-binance>=1.0.12
def setup_market_data_stream(binance_client, symbol, callback_function, interval=None):
    """
    Sets up a WebSocket connection to stream real-time market data.
    This is more efficient than polling the REST API for live trading.
    
    Args:
        binance_client: Initialized Binance client
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        callback_function: Function to call when new data is received
        interval: Optional kline/candlestick interval for kline streams
        
    Returns:
        WebSocket connection object that can be closed with .close()
    """
    if binance_client is None:
        logging.error("Cannot setup WebSocket stream: Binance client is None!")
        return None
        
    try:
        # Check if ThreadedWebsocketManager is available in the current python-binance version
        from importlib.util import find_spec
        
        if find_spec("binance.streams"):
            from binance.streams import ThreadedWebsocketManager
            logging.info("Using ThreadedWebsocketManager for WebSocket connection")

            twm = ThreadedWebsocketManager(
                api_key=binance_client.API_KEY if hasattr(binance_client, 'API_KEY') else None,
                api_secret=binance_client.API_SECRET if hasattr(binance_client, 'API_SECRET') else None
            )
            twm.start()

            if interval:
                stream_name = f"{symbol.lower()}@kline_{interval}"
                stream = twm.start_kline_socket(callback=callback_function, symbol=symbol.lower(), interval=interval)
                logging.info(f"Started kline WebSocket stream for {symbol} ({interval})")
            else:
                stream = twm.start_trade_socket(callback=callback_function, symbol=symbol.lower())
                logging.info(f"Started trade WebSocket stream for {symbol}")

            return {
                'stream': stream,
                'manager': twm,
                'type': 'threaded'
            }

        else:
            logging.warning("WebSocket modules not found. Falling back to REST API polling.")

            class RestPollingManager:
                def __init__(self, client, symbol, callback, interval=None, polling_interval=5.0):
                    self.client = client
                    self.symbol = symbol
                    self.callback = callback
                    self.interval = interval
                    self.polling_interval = polling_interval
                    self.running = False
                    self.thread = None
                    self.last_timestamp = 0

                def _polling_worker(self):
                    while self.running:
                        try:
                            if self.interval:
                                klines = self.client.get_klines(symbol=self.symbol, interval=self.interval, limit=10)
                                for kline in klines:
                                    timestamp = kline[0]
                                    if timestamp > self.last_timestamp:
                                        formatted_msg = {
                                            'e': 'kline',
                                            's': self.symbol,
                                            'k': {
                                                't': kline[0],
                                                'T': kline[6],
                                                's': self.symbol,
                                                'i': self.interval,
                                                'o': kline[1],
                                                'c': kline[4],
                                                'h': kline[2],
                                                'l': kline[3],
                                                'v': kline[5]
                                            }
                                        }
                                        self.callback(formatted_msg)
                                        self.last_timestamp = timestamp
                        except Exception as e:
                            logging.error(f"Error in polling worker: {e}")
                        time.sleep(self.polling_interval)

                def start(self):
                    if not self.running:
                        self.running = True
                        self.thread = threading.Thread(target=self._polling_worker)
                        self.thread.daemon = True
                        self.thread.start()
                        logging.info(f"Started REST API polling for {self.symbol}")

                def stop(self):
                    if self.running:
                        self.running = False
                        if self.thread:
                            self.thread.join(timeout=2.0)
                        logging.info(f"Stopped REST API polling for {self.symbol}")

            manager = RestPollingManager(client=binance_client, symbol=symbol, callback=callback_function, interval=interval)
            manager.start()

            return {
                'manager': manager,
                'type': 'rest_polling'
            }
        
    except Exception as e:
        logging.error(f"Error setting up data stream: {e}")
        if "No such file or directory" in str(e):
            logging.error("Dependencies may not be installed. Try 'pip install python-binance websocket-client'")
        return None
        
def close_market_data_stream(stream_data):
    """
    Closes a WebSocket stream connection.
    
    Args:
        stream_data: The object returned by setup_market_data_stream
    """
    if not stream_data:
        logging.error("Cannot close stream: No stream data provided")
        return
        
    try:
        stream_type = stream_data.get('type', '')
        
        # Handle different stream types
        if stream_type == 'threaded':
            # ThreadedWebsocketManager
            twm = stream_data.get('manager')
            stream = stream_data.get('stream')
            
            if twm and stream:
                try:
                    twm.stop_socket(stream)
                    logging.info(f"Stopped WebSocket stream: {stream}")
                    twm.stop()
                    logging.info("Stopped WebSocket manager")
                except Exception as e:
                    logging.error(f"Error stopping ThreadedWebsocketManager: {e}")
            else:
                logging.warning("Invalid stream data, could not close properly")
        
        elif stream_type == 'legacy':
            # Legacy BinanceSocketManager
            bm = stream_data.get('socket_manager')
            conn_key = stream_data.get('connection_key')
            
            if bm and conn_key:
                try:
                    bm.stop_socket(conn_key)
                    logging.info(f"Stopped WebSocket stream with key: {conn_key}")
                    bm.close()
                    logging.info("Closed WebSocket manager")
                except Exception as e:
                    logging.error(f"Error stopping BinanceSocketManager: {e}")
            else:
                logging.warning("Invalid stream data, could not close properly")
        
        elif stream_type == 'rest_polling':
            # REST API polling fallback
            manager = stream_data.get('manager')
            
            if manager:
                try:
                    manager.stop()
                    logging.info("Stopped REST API polling manager")
                except Exception as e:
                    logging.error(f"Error stopping REST API polling manager: {e}")
            else:
                logging.warning("Invalid polling manager, could not close properly")
                
        else:
            # Backward compatibility with older implementations
            if 'manager' in stream_data and 'stream' in stream_data:
                # Assume ThreadedWebsocketManager
                twm = stream_data.get('manager')
                stream = stream_data.get('stream')
                
                if twm and stream:
                    try:
                        twm.stop_socket(stream)
                        logging.info(f"Stopped WebSocket stream: {stream}")
                        twm.stop()
                        logging.info("Stopped WebSocket manager")
                    except Exception as e:
                        logging.error(f"Error stopping WebSocket manager: {e}")
                else:
                    logging.warning("Invalid stream data, could not close properly")
                    
            elif 'socket_manager' in stream_data and 'connection_key' in stream_data:
                # Assume legacy BinanceSocketManager
                bm = stream_data.get('socket_manager')
                conn_key = stream_data.get('connection_key')
                
                if bm and conn_key:
                    try:
                        bm.stop_socket(conn_key)
                        logging.info(f"Stopped WebSocket stream with key: {conn_key}")
                        bm.close()
                        logging.info("Closed WebSocket manager")
                    except Exception as e:
                        logging.error(f"Error stopping WebSocket manager: {e}")
                else:
                    logging.warning("Invalid stream data, could not close properly")
            else:
                logging.warning("Unknown stream data format, could not close properly")
                
    except Exception as e:
        logging.error(f"Error closing WebSocket stream: {e}")

def process_market_stream_message(msg):
    """
    Example callback function to process WebSocket messages.
    You would typically implement a custom version of this.
    
    Args:
        msg: The message data from WebSocket
        
    Returns:
        Processed data in a standardized format
    """
    try:
        # Check if this is a kline message
        if 'k' in msg:
            kline = msg['k']
            # Extract relevant data
            processed_data = {
                'timestamp': kline['t'],  # Kline start time
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v']),
                'is_closed': kline['x'],  # Whether this kline is closed
                'symbol': msg['s']
            }
            
            if processed_data['is_closed']:
                logging.info(f"Received closed kline: {processed_data['symbol']} @ {processed_data['timestamp']} - Close: {processed_data['close']}")
            
            return processed_data
            
        # Check if this is a trade message
        elif 'p' in msg and 'q' in msg:
            processed_data = {
                'symbol': msg['s'],
                'price': float(msg['p']),
                'quantity': float(msg['q']),
                'timestamp': msg['T'],
                'buyer_maker': msg['m']  # True if buyer is maker
            }
            return processed_data
            
        # Handle error messages
        elif 'e' in msg and msg['e'] == 'error':
            logging.error(f"WebSocket error: {msg}")
            return None
            
        # Unknown message format
        else:
            logging.warning(f"Unknown WebSocket message format: {msg}")
            return msg
            
    except Exception as e:
        logging.error(f"Error processing WebSocket message: {e}")
        logging.error(f"Message was: {msg}")
        return None

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

    # Define project paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Moves from trading_logic to ZenCtrl
    data_dir = os.path.join(project_root, 'data')
    output_dir = os.path.join(data_dir, 'output')

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    optimization_log_filename = DEFAULT_OPTIMIZATION_LOG_CSV 
    
    # Path for optimization log CSV
    effective_csv_path = os.path.join(data_dir, optimization_log_filename)

    logging.info(f"Attempting to load optimization log from: {effective_csv_path}")

    strategy_params = load_optimized_parameters(effective_csv_path, 
                                                DEFAULT_PARAMS['symbol'], 
                                                current_timeframe_str,
                                                DEFAULT_PARAMS)
    logging.info(f"Using parameters for simulation: {strategy_params}")

    historical_data = fetch_data(client, 
                                 strategy_params['symbol'], 
                                 strategy_params['timeframe'], 
                                 strategy_params['lookback_candles'] + 150) # Fetch a bit more for safety
    
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
                                                  binance_client=client) # Pass client here
        
        logging.info(f"\n--- Simulation Summary for {strategy_params['symbol']} ({current_timeframe_str}) ---")
        logging.info(f"Parameters Used: {strategy_params}")
        logging.info(f"Initial Balance: 10000.00 USD")
        logging.info(f"Final Portfolio Value: {final_value:.2f} USD")
        logging.info(f"Total Profit/Loss: {pnl:.2f} USD")
        
        if not trades.empty:
            logging.info(f"Number of trades: {len(trades[trades['action']=='SELL'])}") # Corrected to count sell trades for round trips
            # Path for saving trades log
            trades_csv_filename = f"trades_log_{strategy_params['symbol']}_{current_timeframe_str}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_csv_path = os.path.join(output_dir, trades_csv_filename)
            trades.to_csv(trades_csv_path, index=False)
            logging.info(f"Trades log saved to {trades_csv_path}")
        else:
            logging.info("No trades were executed.")
            
    else:
        logging.error("Could not fetch sufficient historical data to run the simulation.")

    logging.info("Strategy execution finished.")
