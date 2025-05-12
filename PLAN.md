# PLAN: Assimilation of LeniaOodaStrategy into ZenCtrl with ZEN Predictive Augmentation

**Date:** May 12, 2025
**Target Branch:** `draft/assimilate-lenia-ooda-strategy`
**Primary Goal:** To develop a Gradio-based application where users can design, visualize, and backtest trading strategies (initially `LeniaOodaStrategy.py`). The core innovation will be the integration of ZenCtrl's image generation/analysis capabilities (ZEN) into the backtesting process. This means the simulation will not only use historical market data and standard indicators but will also be able to incorporate predictive signals derived from ZEN at each step (or specified intervals) of the backtest. This will allow users to explore "what-if" scenarios where trading decisions are augmented or influenced by ZEN's "insights."

---

## Section 1: Phase 1 - Initial Setup & Foundational Integration

1.  **Git Branch Management:**
    *   **Action:** Create a new branch named `draft/assimilate-lenia-ooda-strategy`. (Completed)
    *   **Purpose:** Isolate development work for this feature.

2.  **File Placement & Structure for `LeniaOodaStrategy.py`:**
    *   **Action:** Copy `LeniaOodaStrategy.py` (from `c:\source\BinanceTradingMVP\Python\LeniaOodaStrategy.py`) into the `ZenCtrl` project.
    *   **Proposed Location:** Create `d:\source\ZenCtrl\trading_logic\` and place the file as `d:\source\ZenCtrl\trading_logic\lenia_ooda_strategy.py`.
    *   **Action:** Create `d:\source\ZenCtrl\trading_logic\__init__.py` to make it a Python package.

3.  **Dependency Management:**
    *   **Action:** Identify external libraries used by `LeniaOodaStrategy.py` (e.g., `pandas`, `numpy`, `python-binance`).
    *   **Action:** Add these to `d:\source\ZenCtrl\requirements.txt`.
        *   `pandas>=<version>`
        *   `numpy>=<version>`
        *   `python-binance>=<version>`
    *   **Action:** Ensure the virtual environment (`d:\source\ZenCtrl\venv`) is updated: `pip install -r requirements.txt`.

4.  **Configuration Management for `lenia_ooda_strategy.py`:**
    *   **API Keys (`api_key`, `api_secret`):**
        *   **Action:** Modify `lenia_ooda_strategy.py` to read API keys from environment variables (e.g., `BINANCE_API_KEY`, `BINANCE_API_SECRET`) or a configuration file (e.g., `config.ini` or `settings.py` at the project root, ensuring it's in `.gitignore` if it contains secrets).
        *   **Recommendation:** Use a `.env` file with `python-dotenv` library for local development.
    *   **Optimization Log CSV Path:**
        *   **Action:** Modify `load_optimized_parameters` in `lenia_ooda_strategy.py` to accept a path or look for the CSV in a predefined relative location (e.g., `d:\source\ZenCtrl\data\`).
        *   **Consideration:** For initial integration, the default path can be temporarily hardcoded to a location within `ZenCtrl` if the file is copied over.
    *   **Binance Client Initialization:**
        *   **Action:** Ensure `Client(api_key, api_secret)` is initialized correctly after sourcing keys.

5.  **Basic Refactoring of `lenia_ooda_strategy.py` for Modularity:**
    *   **Goal:** Make core logic callable from `gradio_app.py`.
    *   **Action:**
        *   Ensure `fetch_data` is easily callable.
        *   Ensure `load_optimized_parameters` is easily callable.
        *   Refactor `run_simulation`:
            *   Separate indicator calculation logic from the main simulation loop if possible.
            *   The core trading decision logic (buy/sell/hold based on consensus) should be a clearly defined function.
            *   The part of the loop that iterates through data and makes decisions step-by-step will be key for ZEN integration.
        *   The `main()` function in `lenia_ooda_strategy.py` will likely be adapted or removed for Gradio integration, with its orchestration logic moving to `gradio_app.py`.

6.  **Define ZEN Prediction Interface (`zen_predictor.py` or similar):**
    *   **Action:** Create a new file, e.g., `d:\source\ZenCtrl\app\zen_predictor.py`.
    *   **Action:** Define a function `get_zen_signal(current_market_data, historical_data_summary, optional_prompt_elements) -> float:`
        *   `current_market_data`: DataFrame row or dict for the current timestep.
        *   `historical_data_summary`: Potentially a small window of past prices, volumes, or LeniaOODA indicator states.
        *   `optional_prompt_elements`: User-defined text or parameters to guide image generation.
        *   **Internal Logic:**
            1.  Construct a prompt for `flux.generate.generate`. This prompt will be based on the input data and aim to elicit an image that can be interpreted for a "predictive signal."
            2.  Call `flux.generate.generate` to get an image.
            3.  **Image-to-Signal Conversion (Crucial Design Point):**
                *   **Initial Approach (Prototyping):** Could be as simple as a placeholder. e.g., if a certain color is dominant, or if a user-defined keyword appears in a text overlay (if ZEN supports that).
                *   **Intermediate:** A very simple image classification model (e.g., trained on "bullish" vs "bearish" example images generated by ZEN) or a rule-based system.
                *   **Advanced:** More sophisticated image analysis or a dedicated small model.
            4.  Return a normalized signal (e.g., -1.0 for strong sell, 0.0 for neutral, 1.0 for strong buy).

7.  **Initial Standalone Test (Post-Refactor):**
    *   **Action:** Create a small test script or modify `lenia_ooda_strategy.py`'s `if __name__ == "__main__":` block to call its refactored components and ensure it runs within the `ZenCtrl` environment using the new configuration methods.

---

## Section 2: Phase 2 - Integrating ZEN Predictions into Backtesting Logic & Gradio UI

1.  **Modify `lenia_ooda_strategy.py` (`run_simulation` or equivalent core logic):**
    *   **Action:** The core simulation function must now be able to accept a `zen_signal` (float) for each timestep.
    *   **Action:** Modify the `consensus_value` calculation:
        *   `consensus_value = signal_ma + signal_mom + ... + (zen_signal * zen_weight)`
        *   `zen_weight` should be a new configurable parameter (e.g., via Gradio).
    *   **Consideration:** How to handle `zen_signal` if it's not available for every step (e.g., if ZEN prediction is computationally expensive and run less frequently).

2.  **Gradio UI Development (`gradio_app.py`):**
    *   **New Tab/Section for "ZEN Backtester":**
    *   **Inputs:**
        *   Standard LeniaOODA parameters (symbol, timeframe, EMA period, ATR periods, etc. - potentially loaded from optimized params or user-overridden).
        *   File upload for `optimization_log.csv` (or selection from a `data/` dir).
        *   ZEN Integration Controls:
            *   Checkbox: "Enable ZEN Predictive Augmentation".
            *   Slider/Number Input: "ZEN Signal Weight" (0.0 to N.N).
            *   Textbox: "Base Prompt for ZEN" (e.g., "Market sentiment based on recent price action:").
            *   Number Input: "ZEN Prediction Frequency" (e.g., run ZEN every N candles).
        *   Button: "Run ZEN-Augmented Backtest".
    *   **Core Backtesting Loop in Gradio Callback:**
        1.  Load historical data using `lenia_ooda_strategy.fetch_data`.
        2.  Load/set strategy parameters.
        3.  Initialize simulation variables (position, entry_price, trades_log, etc.).
        4.  Iterate through historical data (candles):
            *   Calculate standard LeniaOODA indicators for the current step.
            *   If ZEN augmentation is enabled AND it's a ZEN prediction step (based on frequency):
                *   Prepare context for `zen_predictor.get_zen_signal`.
                *   Call `zen_predictor.get_zen_signal()` to get the `current_zen_signal`.
                *   Store this signal.
            *   Else (if not a ZEN step or ZEN disabled):
                *   Use the last known `current_zen_signal` or a neutral value (0.0).
            *   Call the (refactored) core trading logic from `lenia_ooda_strategy.py` for the current step, passing in market data and the `current_zen_signal` and its weight.
            *   Log trades, P&L, and importantly, the `current_zen_signal` used for that decision point.
    *   **Outputs:**
        *   Trade Log Table: Include columns for entry/exit dates, prices, position, return, **and the ZEN signal active at trade entry**.
        *   P&L Chart (e.g., using `gr.LinePlot`).
        *   Key Metrics: Total P&L, Win Rate, Max Drawdown, etc.
        *   **ZEN Insights Visualization (Key Feature):**
            *   A section to display a few key images generated by ZEN during the backtest, perhaps linked to significant trades or turning points.
            *   A plot showing the `zen_signal` over time, overlaid on the price chart or P&L chart.

---

## Section 3: Phase 3 - Advanced What-If Scenarios, Visualization & Refinement

1.  **Parameter Sweeping & Comparison:**
    *   Allow users to run multiple backtests with different ZEN weights or prompt strategies and compare results side-by-side in the UI.
2.  **Interactive ZEN Analysis:**
    *   On clicking a trade in the log, display the specific ZEN image (if generated) and context that led to the signal for that trade.
3.  **Refine `zen_predictor.get_zen_signal()`:**
    *   Iteratively improve the prompt engineering for ZEN.
    *   Experiment with different image-to-signal conversion methods. If a simple model is used, provide a way to train/update it.
4.  **Performance Optimization:**
    *   ZEN image generation can be slow. Consider optimizations:
        *   Caching ZEN predictions for similar inputs if applicable.
        *   Running ZEN predictions in the background if the backtest can proceed with stale data for a few steps.
        *   Allowing users to select a less resource-intensive ZEN model variant for backtesting.

---

## Section 4: Phase 4 - Testing, Documentation & Finalization

1.  **Testing:**
    *   Unit tests for `zen_predictor.py` functions.
    *   Unit tests for modified `lenia_ooda_strategy.py` logic.
    *   Integration tests for the Gradio UI callbacks and the full backtesting loop with ZEN.
    *   Validate that ZEN signals are correctly influencing trades as per their weight.
2.  **Documentation:**
    *   Update `README.md` extensively:
        *   How to set up API keys and configurations.
        *   How to run the ZEN-augmented backtester.
        *   Explanation of all Gradio UI controls.
        *   Guidance on interpreting ZEN-augmented results and designing ZEN prompts.
    *   Detailed docstrings and comments in all new/modified Python files.
3.  **Code Cleanup & Refinement:**
    *   Ensure code is clean, readable, and follows Python best practices.
    *   Final review of error handling and user feedback in the UI.

---
