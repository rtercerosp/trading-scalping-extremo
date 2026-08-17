import json
import os
from collections import defaultdict
from typing import Any

from brain.models import TradeRecord


class ResearchDatabase:
    def __init__(self, base_dir: str = "research"):
        self.base_dir = base_dir
        self.trades_file = os.path.join(base_dir, "ml_database_trades.json")
        self.summary_file = os.path.join(base_dir, "ml_database_summary.json")
        self.exit_models_file = os.path.join(base_dir, "exit_model_rankings.json")
        self.ai_recommendations_file = os.path.join(base_dir, "ai_recommendations.json")
        os.makedirs(base_dir, exist_ok=True)

    def append_trade(self, trade: TradeRecord) -> None:
        data = self._load_json(self.trades_file, [])
        data.append(trade.to_dict())
        self._save_json(self.trades_file, data)

    def get_trades(self) -> list[dict]:
        return self._load_json(self.trades_file, [])

    def update_summary(self, summary: dict[str, Any]) -> None:
        existing = self._load_json(self.summary_file, {})
        existing.update(summary)
        self._save_json(self.summary_file, existing)

    def get_summary(self) -> dict[str, Any]:
        return self._load_json(self.summary_file, {})

    def update_exit_model_rankings(self, rankings: dict[str, Any]) -> None:
        self._save_json(self.exit_models_file, rankings)

    def get_exit_model_rankings(self) -> dict[str, Any]:
        return self._load_json(self.exit_models_file, {})

    def update_ai_recommendations(self, recommendations: dict[str, Any]) -> None:
        self._save_json(self.ai_recommendations_file, recommendations)

    def get_ai_recommendations(self) -> dict[str, Any]:
        return self._load_json(self.ai_recommendations_file, {})

    def _load_json(self, path: str, default: Any):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, path: str, payload: Any) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
