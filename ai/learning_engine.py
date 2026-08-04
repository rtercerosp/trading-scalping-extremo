# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import json
import os
import logging
from typing import Dict, Optional
from datetime import datetime
from utils.symbol_utils import normalize_symbol
import config


logger = logging.getLogger(__name__)


class LearningEngine:
    def __init__(self, storage_path: str = "ai/learning_params.json"):
        self.storage_path = storage_path
        self.params: Dict[str, Dict] = {}
        self._load_params()

    def _load_params(self) -> None:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding="utf-8") as f:
                    self.params = json.load(f)
            except Exception as e:
                logger.error("LEARNING: Error cargando params desde %s: %s", self.storage_path, e, exc_info=True)

    def _save_params(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w', encoding="utf-8") as f:
                json.dump(self.params, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("LEARNING: Error guardando params en %s: %s", self.storage_path, e, exc_info=True)

    def get_params(self, symbol: str) -> Dict:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.params:
            base_params = {
                "sl_atr_mult": config.LEARNING_DEFAULT_SL_ATR_MULT,
                "tp_atr_mult": config.LEARNING_DEFAULT_TP_ATR_MULT,
                "risk_pct": config.LEARNING_DEFAULT_RISK_PCT,
                "learning_rate": config.LEARNING_DEFAULT_LEARNING_RATE,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_profit": 0.0,
                "last_update": datetime.now().isoformat(),
            }
            extreme_params = getattr(config, "EXTREME_SCALPING_PARAMS", {}).get(symbol_key, {})
            if extreme_params and extreme_params.get("enabled", False):
                for key in ("sl_atr_mult", "tp_atr_mult", "risk_pct", "trailing_activation_pct", "trailing_offset_pct"):
                    if key in extreme_params:
                        base_params[key] = extreme_params[key]
            if symbol_key in config.LEARNING_ASSET_SPECIFIC_PARAMS:
                base_params.update(config.LEARNING_ASSET_SPECIFIC_PARAMS[symbol_key])
            self.params[symbol_key] = base_params
        return self.params[symbol_key]

    def update_params(self, symbol: str, profit: float, sl_hit: bool, tp_hit: bool) -> Dict:
        symbol_key = normalize_symbol(symbol)
        params = self.get_params(symbol_key)
        params["total_trades"] += 1
        params["total_profit"] += profit
        if profit > 0:
            params["winning_trades"] += 1
        else:
            params["losing_trades"] += 1

        win_rate = params["winning_trades"] / params["total_trades"] if params["total_trades"] > 0 else 0
        lr = params.get("learning_rate", 0.1)

        # Decrement params on Stop Loss hit
        if sl_hit and not tp_hit:
            params["sl_atr_mult"] = max(config.LEARNING_SL_ATR_MULT_MIN, params["sl_atr_mult"] - lr * config.LEARNING_STEP_SL_DECREASE)
            params["tp_atr_mult"] = max(config.LEARNING_TP_ATR_MULT_MIN, params["tp_atr_mult"] - lr * config.LEARNING_STEP_TP_DECREASE)
            params["risk_pct"] = max(config.LEARNING_RISK_PCT_MIN, params["risk_pct"] - lr * config.LEARNING_STEP_RISK_DECREASE)

        # Increment params on Take Profit hit
        elif tp_hit and not sl_hit:
            params["sl_atr_mult"] = min(config.LEARNING_SL_ATR_MULT_MAX, params["sl_atr_mult"] + lr * config.LEARNING_STEP_SL_INCREASE)
            params["tp_atr_mult"] = min(config.LEARNING_TP_ATR_MULT_MAX, params["tp_atr_mult"] + lr * config.LEARNING_STEP_TP_INCREASE)

            # Increase risk only if win rate is high enough
            if win_rate > config.LEARNING_WIN_RATE_THRESHOLD_FOR_RISK_INCREASE:
                params["risk_pct"] = min(config.LEARNING_RISK_PCT_MAX, params["risk_pct"] + lr * config.LEARNING_STEP_RISK_INCREASE)

        # Ensure params stay within global bounds after any adjustment
        params["sl_atr_mult"] = max(config.LEARNING_SL_ATR_MULT_MIN, min(config.LEARNING_SL_ATR_MULT_MAX, params["sl_atr_mult"]))
        params["tp_atr_mult"] = max(config.LEARNING_TP_ATR_MULT_MIN, min(config.LEARNING_TP_ATR_MULT_MAX, params["tp_atr_mult"]))
        params["risk_pct"] = max(config.LEARNING_RISK_PCT_MIN, min(config.LEARNING_RISK_PCT_MAX, params["risk_pct"]))

        params["last_update"] = datetime.now().isoformat()
        self.params[symbol_key] = params
        self._save_params()
        return params

    def get_adaptive_params(self, symbol: str) -> Dict:
        return self.get_params(symbol)
