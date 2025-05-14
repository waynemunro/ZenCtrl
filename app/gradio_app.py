# Recycled from Ominicontrol 

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

import gradio as gr
import torch
from PIL import Image
from diffusers.pipelines import FluxPipeline
from diffusers import FluxTransformer2DModel

from flux.condition import Condition
from flux.generate import generate
from flux.lora_controller import set_lora_scale

# Imports for ZEN Backtester
import pandas as pd
import ast
import numpy as np
from trading_logic.lenia_ooda_strategy import DEFAULT_PARAMS as LOS_DEFAULT_PARAMS
from trading_logic.lenia_ooda_strategy import fetch_data as los_fetch_data
from trading_logic.lenia_ooda_strategy import load_optimized_parameters as los_load_optimized_parameters
from trading_logic.lenia_ooda_strategy import run_simulation as los_run_simulation
from binance.client import Client as BinanceClient
from app.zen_predictor import get_zen_signal

pipe = None
use_int8 = False
model_config = { "union_cond_attn": True, "add_cond_attn": False, "latent_lora": False, "independent_condition": False}

def get_gpu_memory():
    return torch.cuda.get_device_properties(0).total_memory / 1024**3


def init_pipeline():
    global pipe
    # Create absolute path for offload folder to avoid path-related issues
    offload_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'offload_weights'))
    os.makedirs(offload_folder, exist_ok=True)  # Ensure the folder exists
    print(f"Using offload folder: {offload_folder}")
    pipe = None # Initialize pipe to None
    
    # Force garbage collection before loading models
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        print(f"CUDA available. Current memory: {torch.cuda.memory_allocated()/1024**2:.2f}MB allocated")

    try:
        print("Attempting to initialize pipeline on GPU...")
        # Always use int8 version for more memory efficiency
        print("Using int8 transformer model configuration for memory efficiency.")
        try:
            # Add safe globals for trusted sources
            torch.serialization.add_safe_globals({"__torch__.FluxTransformer2DModel": FluxTransformer2DModel})

            # Ensure weights_only is set to False for trusted sources
            transformer_model = FluxTransformer2DModel.from_pretrained(
                "sayakpaul/flux.1-schell-int8wo-improved",
                torch_dtype=torch.bfloat16,
                use_safetensors=False,  # Disable safetensors as the file is missing
                weights_only=False      # Ensure full model loading
            )
        except Exception as e:
            print(f"[Error] Primary model loading failed: {e}")
            print("[Fallback] Attempting to load alternative model checkpoint...")
            transformer_model = FluxTransformer2DModel.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.bfloat16,
                use_safetensors=False
            )
        
        pipe = FluxPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-schnell",
            transformer=transformer_model, # Pass the transformer
            torch_dtype=torch.float16,     # Other components in float16
            use_safetensors=True,         # Use safetensors for other components
            low_cpu_mem_usage=True,
            device_map="auto",            # Automatically map model to available devices
            offload_folder=offload_folder # offload_state_dict=True removed
        )
        print(f"Pipeline initialized. Target device (from first component, e.g., transformer): {pipe.device if pipe else 'N/A'}")

    except (RuntimeError, MemoryError, ValueError) as e: # Catch all relevant errors
        print(f"Error during GPU pipeline initialization ({type(e).__name__}: {e}). Falling back to CPU.")
        pipe = None # Ensure pipe is None before attempting CPU fallback
        
        # Force garbage collection again
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        try:
            print("Attempting to load FLUX.1-schnell on CPU with float32...")
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.float32,    # Use float32 for CPU compatibility
                use_safetensors=True,         # Use safetensors for CPU fallback
                low_cpu_mem_usage=True,       # Still useful for CPU
                device_map="cpu",             # Explicitly map to CPU
                offload_folder=offload_folder # offload_state_dict=True removed
            )
            print(f"Pipeline initialized on CPU. Target device: {pipe.device if pipe else 'N/A'}")
        except Exception as cpu_e:
            print(f"Failed to initialize pipeline on CPU as well ({type(cpu_e).__name__}: {cpu_e}).")
            pipe = None # Ensure pipe is None if CPU fallback also fails
    
    # Optional: Load additional LoRA weights, put the loaded weights here!
    if pipe is not None:
        try:
            print("Loading LoRA weights...")
            pipe.load_lora_weights("weights/zen2con_1440_17000/pytorch_lora_weights.safetensors",
                adapter_name="subject")
            pipe.set_adapters(["subject"])
            print("LoRA weights loaded and adapter set.")
        except Exception as lora_e:
            print(f"Error loading LoRA weights ({type(lora_e).__name__}: {lora_e}). Proceeding without LoRA.")
    else:
        print("Pipeline not initialized. Skipping LoRA weights loading.")

def paste_on_white_background(image: Image.Image) -> Image.Image:
    """
    Pastes a transparent image onto a white background of the same size.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Create white background
    white_bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    white_bg.paste(image, (0, 0), mask=image)
    return white_bg.convert("RGB")  # Convert back to RGB if you don't need alpha


def process_image_and_text(image, text, steps=8, strength_sub=1.0, strength_spat=1.0, size=1024):
    # center crop image
    w, h, min_size = image.size[0], image.size[1], min(image.size)
    box = (
        (w - min_size) // 2,
        (h - min_size) // 2,
        (w + min_size) // 2,
        (h + min_size) // 2,
    )
    if box is None or len(box) != 4 or box[3] < box[1] or box[2] < box[0]:
        raise ValueError(f"Invalid crop box: {box}")
    image = image.crop(box)
    image = image.resize((size, size))
    image = paste_on_white_background(image) #Optional, you can remove this line if you want just make sure the size it matched.
    condition0 = Condition("subject", image, position_delta=(0, size // 16))
    condition1 = Condition("subject", image, position_delta=(0, -size // 16))
    
    if pipe is None:
        init_pipeline()
    
    with set_lora_scale(["subject"], scale=3.0):
        result_img = generate(
            pipe,
            prompt=text.strip(),
            conditions=[condition0, condition1],
            num_inference_steps=steps,
            height=1024,
            width=1024,
            condition_scale = [strength_sub,strength_spat],
            model_config=model_config,
            default_lora=True,
        ).images[0]

    return [condition0.condition, condition1.condition, result_img]


def get_samples():
    sample_list = [
        {
            "image": "samples/1.png",   #place your image path here
            "text": "A man sitting in a yellow chair drinking a cup of coffee",
        }
    ]
    processed_samples = []
    for sample in sample_list:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.join(base_dir, '..')
            image_path = os.path.join(project_root, sample["image"])
            
            if not os.path.exists(image_path):
                print(f"Warning: Sample image not found at {image_path}")
                if os.path.exists(sample["image"]):
                    image_path = sample["image"]
                else:
                    continue

            processed_samples.append([Image.open(image_path), sample["text"]])
        except Exception as e:
            print(f"Error loading sample image {sample.get('image', 'N/A')}: {e}")
            
    if not processed_samples:
        print("Warning: No samples loaded. Using a placeholder example.")
        try:
            dummy_image = Image.new('RGB', (100, 100), color = 'red')
            return [[dummy_image, "Placeholder if no samples load."]]
        except Exception:
            return [["Placeholder text if image creation fails."]]
            
    return processed_samples


def run_zen_backtest_callback(symbol, timeframe, ema_period, atr_period, atr_multiplier, 
                              momentum_period, rsi_period, rsi_oversold, rsi_overbought,
                              lenia_r, lenia_t, lenia_b_str, lenia_m, lenia_s, 
                              lookback_candles, trade_amount_usd,
                              optimization_log_file, 
                              enable_zen, zen_signal_weight, base_prompt_zen, zen_prediction_frequency):
    
    print("Run ZEN-Augmented Backtest button clicked.")
    
    strategy_params = LOS_DEFAULT_PARAMS.copy()

    ui_params = {
        'symbol': symbol,
        'timeframe': timeframe,
        'ema_period': int(ema_period),
        'atr_period': int(atr_period),
        'atr_multiplier': float(atr_multiplier),
        'momentum_period': int(momentum_period),
        'rsi_period': int(rsi_period),
        'rsi_oversold': float(rsi_oversold),
        'rsi_overbought': float(rsi_overbought),
        'lenia_r': int(lenia_r),
        'lenia_t': int(lenia_t),
        'lenia_m': float(lenia_m),
        'lenia_s': float(lenia_s),
        'lookback_candles': int(lookback_candles),
        'trade_amount_usd': float(trade_amount_usd)
    }

    try:
        lenia_b_list = ast.literal_eval(lenia_b_str)
        if not isinstance(lenia_b_list, list) or not all(isinstance(item, (float, int)) for item in lenia_b_list):
            raise ValueError("Lenia B must be a list of numbers.")
        ui_params['lenia_b'] = lenia_b_list
    except Exception as e:
        error_message = f"Error parsing Lenia B: {e}. Using default: {strategy_params['lenia_b']}"
        print(error_message)
        ui_params['lenia_b'] = strategy_params['lenia_b']
        
    strategy_params.update(ui_params)

    # Initialize Binance client for fetching data
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print(f"WARNING: Binance API keys not found in environment variables!")
        print(f"For testing purposes, using a demo mode with sample data.")
        # Here we could load sample data instead for demo purposes
        # For now, continue with None values, and handle the error in fetch_data
    
    try:
        binance_client = BinanceClient(api_key, api_secret)
        print("Binance client initialized successfully.")
    except Exception as e:
        print(f"ERROR initializing Binance client: {e}")
        binance_client = None

    # Create a directory for ZEN images if using ZEN
    zen_images_dir = None
    if enable_zen:
        zen_images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'zen_images')
        os.makedirs(zen_images_dir, exist_ok=True)
        print(f"ZEN images will be saved to: {zen_images_dir}")

    if optimization_log_file is not None:
        try:
            print(f"Attempting to load parameters from uploaded file: {optimization_log_file.name}")
            loaded_opt_params = los_load_optimized_parameters(optimization_log_file.name, symbol, timeframe)
            if loaded_opt_params:
                strategy_params.update(loaded_opt_params)
                print("Successfully loaded and merged parameters from optimization log.")
            else:
                print("No specific parameters found in log for symbol/timeframe, or log was empty. Using UI/default parameters.")
        except Exception as e:
            print(f"Error loading from optimization log: {e}. Using UI/default parameters.")
    
    print(f"Final Strategy Parameters: {strategy_params}")
    
    candles_for_simulation_run = 500
    total_candles_to_fetch = strategy_params['lookback_candles'] + candles_for_simulation_run
    
    print(f"Fetching {total_candles_to_fetch} candles for {strategy_params['symbol']} ({strategy_params['timeframe']})...")
    
    if binance_client is None:
        error_msg = "ERROR: Binance API keys not set or not valid. Cannot fetch market data."
        print(error_msg)
        print("You need to set BINANCE_API_KEY and BINANCE_API_SECRET environment variables.")
        print("For example on Windows: ")
        print("    set BINANCE_API_KEY=your_api_key")
        print("    set BINANCE_API_SECRET=your_api_secret")
        print("Or on Linux/macOS:")
        print("    export BINANCE_API_KEY=your_api_key")
        print("    export BINANCE_API_SECRET=your_api_secret")
        return error_msg, None, error_msg, error_msg, None
    
    historical_data = los_fetch_data(binance_client, strategy_params['symbol'], strategy_params['timeframe'], total_candles_to_fetch)

    if historical_data.empty or len(historical_data) < strategy_params['lookback_candles']:
        error_msg = "Failed to fetch sufficient historical data for backtesting."
        print(error_msg)
        print("This could be due to:")
        print("1. Invalid API keys")
        print("2. API rate limits")
        print("3. Symbol doesn't exist (check trading pair)")
        print("4. Network issues")
        return error_msg, None, error_msg, error_msg, None

    print(f"Fetched {len(historical_data)} data points.")

    historical_data_summary_for_zen = pd.Series(dtype=object)
    if not historical_data.empty:
        summary_agg = historical_data.agg({
            'close': ['mean', 'median', 'std'],
            'volume': ['mean', 'sum']
        }).unstack()
        if not summary_agg.empty:
            summary_agg.index = ['_'.join(map(str,col)).strip() for col in summary_agg.index.values]
            historical_data_summary_for_zen = summary_agg.copy()

        if len(historical_data['close']) > 0:
            total_return = (historical_data['close'].iloc[-1] / historical_data['close'].iloc[0] - 1) if len(historical_data['close']) > 1 else 0.0
            historical_data_summary_for_zen['total_period_return'] = total_return
        else:
            historical_data_summary_for_zen['total_period_return'] = 0.0

    actual_zen_predictor_func = None
    zen_images = []  # List to store paths to generated ZEN images
    
    if enable_zen:
        if pipe is None:
            print("ZEN enabled, but pipeline not initialized. Attempting to initialize now.")
            init_pipeline()
            if pipe is None:
                print("Failed to initialize pipeline for ZEN. ZEN augmentation will be skipped.")
                enable_zen = False

    if enable_zen and pipe is not None:
        def zen_predictor_wrapper_for_simulation(simulation_df, current_idx):
            slice_size = 5
            start_slice_idx = max(0, current_idx - slice_size + 1)
            current_market_data_slice = simulation_df.iloc[start_slice_idx : current_idx + 1]
            
            # Format timestamp for the image filename
            timestamp = simulation_df.index[current_idx].strftime("%Y%m%d_%H%M%S")
            print(f"Calling actual get_zen_signal for candle at index: {current_idx}, timestamp: {timestamp}")
            
            # Call ZEN predictor with image saving enabled
            signal = get_zen_signal(
                current_market_data=current_market_data_slice, 
                historical_data_summary=historical_data_summary_for_zen, 
                base_prompt=base_prompt_zen,
                flux_pipe=pipe, 
                model_config=model_config,
                strategy_params=strategy_params,
                save_images=True,
                save_path=zen_images_dir,
                image_timestamp=timestamp
            )
            
            # Find the most recently created image file in the zen_images_dir
            if zen_images_dir:
                try:
                    all_images = [os.path.join(zen_images_dir, f) for f in os.listdir(zen_images_dir) 
                                 if f.startswith(timestamp) and f.endswith('.png')]
                    if all_images:
                        latest_image = max(all_images, key=os.path.getctime)
                        zen_images.append(latest_image)
                        print(f"Added ZEN image to collection: {latest_image}")
                except Exception as e:
                    print(f"Error finding ZEN image: {e}")
            
            return signal
            
        actual_zen_predictor_func = zen_predictor_wrapper_for_simulation
        print("ZEN augmentation enabled. ZEN predictor function is set.")
    elif enable_zen:
        print("ZEN was enabled, but pipeline failed to initialize. Proceeding without ZEN.")

    print("Starting simulation...")
    initial_balance = 10000
    trades_df, final_value, pnl = los_run_simulation(
        df=historical_data,
        params=strategy_params,
        initial_balance_usd=initial_balance,
        zen_signal_enabled=enable_zen and pipe is not None,
        zen_weight=float(zen_signal_weight) if enable_zen and pipe is not None else 0.0,
        zen_predictor_func=actual_zen_predictor_func if enable_zen and pipe is not None else None,
        zen_prediction_frequency=int(zen_prediction_frequency) if enable_zen and pipe is not None else 1,
        binance_client=binance_client
    )
    print("Simulation finished.")

    trade_log_output_str = "No trades executed." 
    if trades_df is not None and not trades_df.empty:
        trade_log_output_str = trades_df.to_markdown(index=False)
    
    pnl_chart_data = None
    if trades_df is not None and not trades_df.empty:
        cumulative_pnl = trades_df[trades_df['action'] == 'SELL']['profit_usd'].cumsum()
        if not cumulative_pnl.empty:
            plot_df = pd.DataFrame({
                'Trade Number': range(1, len(cumulative_pnl) + 1),
                'Cumulative P&L (USD)': cumulative_pnl.values
            })
            pnl_chart_data = plot_df
            print("P&L chart data prepared.")
        else:
            print("No SELL trades to plot P&L.")
    else:
        print("No trades data for P&L chart.")

    num_trades = 0
    win_rate = 0.0
    total_profit_usd = pnl
    max_drawdown = "N/A"

    if trades_df is not None and not trades_df.empty:
        sell_trades = trades_df[trades_df['action'] == 'SELL']
        num_trades = len(sell_trades)
        if num_trades > 0:
            winning_trades = sell_trades[sell_trades['profit_usd'] > 0]
            win_rate = (len(winning_trades) / num_trades) * 100 if num_trades > 0 else 0
    
    key_metrics_str = f"Total P&L: {total_profit_usd:.2f} USD\n"
    key_metrics_str += f"Number of Trades (Sells): {num_trades}\n"
    key_metrics_str += f"Win Rate: {win_rate:.2f}%\n"
    key_metrics_str += f"Max Drawdown: {max_drawdown}"
    print(f"Key Metrics: {key_metrics_str}")

    zen_insights_str = "ZEN Insights: Not yet implemented. Will show ZEN images/signals here."
    zen_images_output = None
    
    if enable_zen and zen_images:
        # Limit to the most important images (start, end, and a few in between)
        max_images_to_show = 9  # for a 3x3 gallery
        if len(zen_images) > max_images_to_show:
            # Select evenly spaced images including first and last
            indices = np.linspace(0, len(zen_images)-1, max_images_to_show, dtype=int)
            selected_images = [zen_images[i] for i in indices]
        else:
            selected_images = zen_images
            
        try:
            # Convert file paths to PIL images
            pil_images = [Image.open(img_path) for img_path in selected_images]
            zen_images_output = pil_images
            
            # Create a more informative insights string
            zen_insights_str = f"ZEN generated {len(zen_images)} images during the backtest.\n"
            
            if trades_df is not None and not trades_df.empty and 'active_zen_signal' in trades_df.columns:
                # Calculate some statistics about ZEN signals
                zen_signals = trades_df['active_zen_signal'].dropna()
                if not zen_signals.empty:
                    avg_signal = zen_signals.mean()
                    max_signal = zen_signals.max()
                    min_signal = zen_signals.min()
                    zen_insights_str += f"Average ZEN signal: {avg_signal:.4f} (range: {min_signal:.4f} to {max_signal:.4f})\n"
                    
                    # Count how many trades were influenced by ZEN
                    zen_influenced = trades_df[trades_df['active_zen_signal'].abs() > 0.1]
                    if not zen_influenced.empty:
                        zen_insights_str += f"ZEN influenced {len(zen_influenced)} trading decisions.\n"
            
            zen_insights_str += "The gallery shows selected ZEN-generated images from the backtest period."
        except Exception as e:
            print(f"Error preparing ZEN images for display: {e}")
            zen_insights_str += f"\nError displaying images: {e}"
    elif enable_zen:
        zen_insights_str = "ZEN was enabled but no images were generated during the backtest."
    
    return trade_log_output_str, pnl_chart_data, key_metrics_str, zen_insights_str, zen_images_output

with gr.Blocks() as demo:
    gr.Markdown("# ZenCtrl: Generative Backtesting & Visualization")
    with gr.Tab("ZEN Image Generation"):
        gr.Markdown("## Subject-Driven Image Generation with FLUX")
        with gr.Row():
            with gr.Column():
                img_input = gr.Image(type="pil", label="Input Image")
                text_input = gr.Textbox(lines=2, label="Prompt")
                with gr.Accordion("Advanced Options", open=False):
                    steps_input = gr.Slider(minimum=2, maximum=28, value=8, step=1, label="Inference Steps")
                    strength_sub_input = gr.Slider(minimum=0, maximum=2.0, value=1.0, label="Subject Strength (Condition Scale Subject)")
                    strength_spat_input = gr.Slider(minimum=0, maximum=2.0, value=1.0, label="Spatial Strength (Condition Scale Spatial)")
                    size_input = gr.Slider(minimum=512, maximum=2048, step=256, value=1024, label="Size (Height/Width)")
                generate_button = gr.Button("Generate Image")
            with gr.Column():
                gallery_output = gr.Gallery(
                    label="Outputs", show_label=False, elem_id="gallery",
                    columns=[3], rows=[1], object_fit="contain", height="auto"
                )
        
        generate_button.click(
            fn=process_image_and_text,
            inputs=[img_input, text_input, steps_input, strength_sub_input, strength_spat_input, size_input],
            outputs=gallery_output
        )
        gr.Examples(
            examples=get_samples(),
            inputs=[img_input, text_input],
            label="Example Prompts & Images"
        )

    with gr.Tab("ZEN Backtester"):
        gr.Markdown("## LeniaOODA Strategy Backtester with ZEN Predictive Augmentation")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Strategy Parameters (LeniaOODA)")
                symbol_input = gr.Textbox(label="Symbol (e.g., BTCUSDT)", value=LOS_DEFAULT_PARAMS['symbol'])
                
                timeframe_choices = [
                    ("1 minute", BinanceClient.KLINE_INTERVAL_1MINUTE),
                    ("3 minutes", BinanceClient.KLINE_INTERVAL_3MINUTE),
                    ("5 minutes", BinanceClient.KLINE_INTERVAL_5MINUTE),
                    ("15 minutes", BinanceClient.KLINE_INTERVAL_15MINUTE),
                    ("30 minutes", BinanceClient.KLINE_INTERVAL_30MINUTE),
                    ("1 hour", BinanceClient.KLINE_INTERVAL_1HOUR),
                    ("2 hours", BinanceClient.KLINE_INTERVAL_2HOUR),
                    ("4 hours", BinanceClient.KLINE_INTERVAL_4HOUR),
                    ("6 hours", BinanceClient.KLINE_INTERVAL_6HOUR),
                    ("12 hours", BinanceClient.KLINE_INTERVAL_12HOUR),
                    ("1 day", BinanceClient.KLINE_INTERVAL_1DAY),
                ]
                timeframe_input = gr.Dropdown(label="Timeframe", choices=timeframe_choices, value=LOS_DEFAULT_PARAMS['timeframe'])
                
                ema_period_input = gr.Number(label="EMA Period", value=LOS_DEFAULT_PARAMS['ema_period'])
                atr_period_input = gr.Number(label="ATR Period", value=LOS_DEFAULT_PARAMS['atr_period'])
                atr_multiplier_input = gr.Number(label="ATR Multiplier", value=LOS_DEFAULT_PARAMS['atr_multiplier'])
                momentum_period_input = gr.Number(label="Momentum Period", value=LOS_DEFAULT_PARAMS['momentum_period'])
                rsi_period_input = gr.Number(label="RSI Period", value=LOS_DEFAULT_PARAMS['rsi_period'])
                rsi_oversold_input = gr.Number(label="RSI Oversold", value=LOS_DEFAULT_PARAMS['rsi_oversold'])
                rsi_overbought_input = gr.Number(label="RSI Overbought", value=LOS_DEFAULT_PARAMS['rsi_overbought'])

                gr.Markdown("#### Lenia Parameters")
                lenia_r_input = gr.Number(label="Lenia R", value=LOS_DEFAULT_PARAMS['lenia_r'])
                lenia_t_input = gr.Number(label="Lenia T", value=LOS_DEFAULT_PARAMS['lenia_t'])
                lenia_b_input_str = gr.Textbox(label="Lenia B (e.g., [0.1, 0.2, 0.3])", value=str(LOS_DEFAULT_PARAMS['lenia_b']))
                lenia_m_input = gr.Number(label="Lenia M", value=LOS_DEFAULT_PARAMS['lenia_m'])
                lenia_s_input = gr.Number(label="Lenia S", value=LOS_DEFAULT_PARAMS['lenia_s'])
                
                lookback_candles_input = gr.Number(label="Lookback Candles (for indicator init)", value=LOS_DEFAULT_PARAMS['lookback_candles'])
                trade_amount_usd_input = gr.Number(label="Trade Amount (USD)", value=LOS_DEFAULT_PARAMS['trade_amount_usd'])

                gr.Markdown("### Parameter Loading")
                optimization_log_upload = gr.File(label="Upload Optimization Log CSV (Optional)", file_types=['.csv'])

            with gr.Column(scale=1):
                gr.Markdown("### ZEN Integration Controls")
                enable_zen_checkbox = gr.Checkbox(label="Enable ZEN Predictive Augmentation", value=False)
                zen_signal_weight_slider = gr.Slider(minimum=0.0, maximum=2.0, step=0.05, label="ZEN Signal Weight", value=0.5)
                base_prompt_zen_textbox = gr.Textbox(label="Base Prompt for ZEN", lines=3, placeholder="e.g., Market sentiment based on recent price action:")
                zen_prediction_frequency_input = gr.Number(label="ZEN Prediction Frequency (every N candles)", value=10, minimum=1, step=1)
                
                run_backtest_button = gr.Button("Run ZEN-Augmented Backtest")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Backtest Results")
                trade_log_output = gr.Textbox(label="Trade Log", lines=10, interactive=False)
                key_metrics_output = gr.Textbox(label="Key Metrics", lines=5, interactive=False)
            with gr.Column():
                pnl_chart_output = gr.Plot(label="P&L Chart")
                zen_insights_output = gr.Textbox(label="ZEN Insights/Images (Placeholder)", lines=5, interactive=False)
                zen_images_gallery = gr.Gallery(label="ZEN Images", show_label=True, elem_id="zen_gallery", columns=[3], rows=[3], object_fit="contain", height="auto")

        backtest_inputs = [
            symbol_input, timeframe_input, ema_period_input, atr_period_input, atr_multiplier_input,
            momentum_period_input, rsi_period_input, rsi_oversold_input, rsi_overbought_input,
            lenia_r_input, lenia_t_input, lenia_b_input_str, lenia_m_input, lenia_s_input,
            lookback_candles_input, trade_amount_usd_input,
            optimization_log_upload,
            enable_zen_checkbox, zen_signal_weight_slider, base_prompt_zen_textbox, zen_prediction_frequency_input
        ]
        backtest_outputs = [trade_log_output, pnl_chart_output, key_metrics_output, zen_insights_output, zen_images_gallery]

        run_backtest_button.click(
            fn=run_zen_backtest_callback,
            inputs=backtest_inputs,
            outputs=backtest_outputs
        )

if __name__ == "__main__":
    # Enable debug mode if needed
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", 5679))
        print("debugpy is listening on port 5679. Attach your debugger now.")
    except ImportError:
        print("debugpy not available. Continuing without remote debugging capability.")
    
    # Model will be lazy-loaded when needed to prevent memory errors at startup
    # DO NOT initialize the pipeline here - it will be initialized on-demand
    # when the user tries to generate an image or run a ZEN-augmented backtest
    
    print("Launching Gradio interface. The FLUX model will be loaded when needed...")
    demo.launch(
        debug=True,
        share=False,  # Set to True if you want to create a public link
    )
