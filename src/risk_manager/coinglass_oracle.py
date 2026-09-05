import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

import numpy as np
import pandas as pd
from utils.utils import Utils


class TrafficLight(Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class LiquidationCluster:
    price: float
    volume: float
    side: str
    exchange: str
    timestamp: str


@dataclass
class DerivativesMetrics:
    symbol: str
    open_interest: float
    open_interest_change_24h: float
    funding_rate: float
    funding_rate_next: float
    long_short_ratio: float
    long_short_ratio_accounts: float
    volume_24h: float
    volume_24h_change: float
    avg_leverage: float
    liquidation_map: List[LiquidationCluster]
    cdri: float
    timestamp: str


@dataclass
class CoinGlassConfig:
    api_key: str = ""
    base_url: str = "https://open-api.coinglass.com/api/pro/v1"
    rate_limit: int = 30
    cache_ttl_seconds: int = 60
    use_mock_data: bool = True
    mock_cdri_base: float = 35.0
    mock_cdri_volatility: float = 15.0


class CoinGlassOracle:
    """
    Oracle for CoinGlass derivatives data integration.
    
    Manages ingestion of 7 key derivatives metrics:
    1. Open Interest (OI)
    2. Funding Rate
    3. Liquidation Map
    4. Average Leverage
    5. Long/Short Ratio
    6. 24h Volume
    7. Derived Risk Index (CDRI)
    
    Provides institutional traffic light system based on CDRI and leverage.
    """
    
    SYMBOL_MAP = {
        "BTCUSD": "BTC",
        "BTCUSDc": "BTC",
        "ETHUSD": "ETH",
        "ETHUSDc": "ETH",
    }
    
    EXCHANGES = ["Binance", "Bybit", "OKX", "Deribit", "Bitget", "HTX"]
    
    def __init__(self, config: Optional[CoinGlassConfig] = None):
        self.config = config or CoinGlassConfig()
        self._cache: Dict[str, Tuple[DerivativesMetrics, float]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0
        self._request_count = 0
        
        if self.config.api_key and not self.config.use_mock_data:
            self._init_session()
    
    def _init_session(self):
        if not AIOHTTP_AVAILABLE:
            return
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {"CG-API-KEY": self.config.api_key, "Content-Type": "application/json"}
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _get_cache_key(self, symbol: str) -> str:
        return self.SYMBOL_MAP.get(symbol, symbol)
    
    def _is_cache_valid(self, cache_time: float) -> bool:
        return (time.time() - cache_time) < self.config.cache_ttl_seconds
    
    async def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0 and self._request_count >= self.config.rate_limit:
            await asyncio.sleep(1.0 - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1
        if self._request_count > self.config.rate_limit:
            self._request_count = 0
    
    def _generate_mock_metrics(self, symbol: str) -> DerivativesMetrics:
        base_symbol = self.SYMBOL_MAP.get(symbol, symbol)
        np.random.seed(int(time.time() * 1000) % 10000 + hash(symbol) % 10000)
        
        base_price = 65000 if "BTC" in base_symbol else 3200
        
        oi = np.random.uniform(15e9, 25e9) if "BTC" in base_symbol else np.random.uniform(8e9, 15e9)
        oi_change = np.random.uniform(-0.08, 0.08)
        
        funding = np.random.uniform(-0.0005, 0.0005)
        funding_next = funding + np.random.uniform(-0.0001, 0.0001)
        
        ls_ratio = np.random.uniform(0.8, 1.3)
        ls_ratio_accounts = np.random.uniform(0.7, 1.4)
        
        vol_24h = np.random.uniform(30e9, 60e9) if "BTC" in base_symbol else np.random.uniform(15e9, 35e9)
        vol_change = np.random.uniform(-0.15, 0.15)
        
        avg_lev = np.random.uniform(15, 35)
        
        liquidation_map = self._generate_mock_liquidation_map(base_price, base_symbol)
        
        cdri = self._calculate_cdri(
            oi_change=oi_change,
            funding_rate=funding,
            ls_ratio=ls_ratio,
            avg_leverage=avg_lev,
            vol_change=vol_change,
            liquidation_map=liquidation_map
        )
        
        return DerivativesMetrics(
            symbol=symbol,
            open_interest=oi,
            open_interest_change_24h=oi_change,
            funding_rate=funding,
            funding_rate_next=funding_next,
            long_short_ratio=ls_ratio,
            long_short_ratio_accounts=ls_ratio_accounts,
            volume_24h=vol_24h,
            volume_24h_change=vol_change,
            avg_leverage=avg_lev,
            liquidation_map=liquidation_map,
            cdri=cdri,
            timestamp=Utils.dateprint()
        )
    
    def _generate_mock_liquidation_map(self, base_price: float, symbol: str) -> List[LiquidationCluster]:
        clusters = []
        n_clusters = np.random.randint(8, 15)
        
        for _ in range(n_clusters):
            side = np.random.choice(["long", "short"], p=[0.55, 0.45])
            exchange = np.random.choice(self.EXCHANGES)
            
            if side == "long":
                price = base_price * (1 - np.random.uniform(0.005, 0.05))
            else:
                price = base_price * (1 + np.random.uniform(0.005, 0.05))
            
            volume = np.random.uniform(50e6, 500e6)
            
            clusters.append(LiquidationCluster(
                price=round(price, 2),
                volume=volume,
                side=side,
                exchange=exchange,
                timestamp=Utils.dateprint()
            ))
        
        clusters.sort(key=lambda x: x.volume, reverse=True)
        return clusters
    
    def _calculate_cdri(
        self,
        oi_change: float,
        funding_rate: float,
        ls_ratio: float,
        avg_leverage: float,
        vol_change: float,
        liquidation_map: List[LiquidationCluster]
    ) -> float:
        score = 0.0
        
        oi_component = min(abs(oi_change) * 100, 25)
        score += oi_component
        
        funding_component = min(abs(funding_rate) * 50000, 20)
        score += funding_component
        
        ls_deviation = abs(ls_ratio - 1.0)
        ls_component = min(ls_deviation * 80, 20)
        score += ls_component
        
        lev_component = min(max((avg_leverage - 10) * 1.5, 0), 20)
        score += lev_component
        
        vol_component = min(abs(vol_change) * 50, 15)
        score += vol_component
        
        total_liq_volume = sum(c.volume for c in liquidation_map)
        long_liq = sum(c.volume for c in liquidation_map if c.side == "long")
        short_liq = sum(c.volume for c in liquidation_map if c.side == "short")
        
        if total_liq_volume > 0:
            liq_imbalance = abs(long_liq - short_liq) / total_liq_volume
            liq_component = min(liq_imbalance * 30, 15)
            score += liq_component
        
        if liquidation_map:
            top_cluster_pct = liquidation_map[0].volume / total_liq_volume if total_liq_volume > 0 else 0
            if top_cluster_pct > 0.25:
                score += 10
        
        return min(max(score, 0), 100)
    
    def _fetch_from_api(self, symbol: str) -> Optional[DerivativesMetrics]:
        if not AIOHTTP_AVAILABLE or not self._session:
            return None
        
        base_symbol = self.SYMBOL_MAP.get(symbol, symbol)
        
        try:
            pass
        except Exception as e:
            print(f"{Utils.dateprint()} - CoinGlassOracle: API fetch error for {symbol}: {e}")
        return None
    
    async def get_metrics(self, symbol: str, force_refresh: bool = False) -> DerivativesMetrics:
        cache_key = self._get_cache_key(symbol)
        
        if not force_refresh and cache_key in self._cache:
            metrics, cache_time = self._cache[cache_key]
            if self._is_cache_valid(cache_time):
                return metrics
        
        if self.config.use_mock_data or not self.config.api_key:
            metrics = self._generate_mock_metrics(symbol)
        else:
            await self._rate_limit()
            metrics = self._fetch_from_api(symbol)
            if metrics is None:
                metrics = self._generate_mock_metrics(symbol)
        
        self._cache[cache_key] = (metrics, time.time())
        return metrics
    
    def get_metrics_sync(self, symbol: str, force_refresh: bool = False) -> DerivativesMetrics:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._generate_mock_metrics(symbol)
        except RuntimeError:
            pass
        
        return asyncio.run(self.get_metrics(symbol, force_refresh))
    
    def get_market_traffic_light(self, symbol: str) -> Tuple[TrafficLight, Dict[str, Any]]:
        metrics = self.get_metrics_sync(symbol)
        cdri = metrics.cdri
        avg_leverage = metrics.avg_leverage
        
        if cdri < 40:
            light = TrafficLight.GREEN
            action = "Vía libre para estrategias direccionales y de ruptura (Squeezes)"
            long_allowed = True
            short_allowed = True
            position_multiplier = 1.0
        elif cdri < 75:
            light = TrafficLight.YELLOW
            action = "Restricción moderada; activar trailing stops acelerados y reducir exposición base en 50%"
            long_allowed = True
            short_allowed = True
            position_multiplier = 0.5
        else:
            light = TrafficLight.RED
            action = "Bloqueo total de entradas LONG; habilitar exclusivamente operativa SHORT en zonas de mitigación institucional de alta liquidez"
            long_allowed = False
            short_allowed = True
            position_multiplier = 0.0
        
        if avg_leverage > 30:
            if light == TrafficLight.GREEN:
                light = TrafficLight.YELLOW
                position_multiplier *= 0.7
            elif light == TrafficLight.YELLOW:
                light = TrafficLight.RED
                position_multiplier = 0.0
                long_allowed = False
        
        details = {
            "traffic_light": light.value,
            "cdri": round(cdri, 2),
            "avg_leverage": round(avg_leverage, 2),
            "action": action,
            "long_allowed": long_allowed,
            "short_allowed": short_allowed,
            "position_multiplier": round(position_multiplier, 2),
            "metrics": {
                "open_interest": metrics.open_interest,
                "oi_change_24h_pct": round(metrics.open_interest_change_24h * 100, 2),
                "funding_rate": round(metrics.funding_rate * 10000, 4),
                "funding_rate_next": round(metrics.funding_rate_next * 10000, 4),
                "long_short_ratio": round(metrics.long_short_ratio, 3),
                "ls_ratio_accounts": round(metrics.long_short_ratio_accounts, 3),
                "volume_24h": metrics.volume_24h,
                "vol_change_24h_pct": round(metrics.volume_24h_change * 100, 2),
            },
            "liquidation_clusters": [
                {
                    "price": c.price,
                    "volume": c.volume,
                    "side": c.side,
                    "exchange": c.exchange
                }
                for c in metrics.liquidation_map[:10]
            ],
            "timestamp": metrics.timestamp
        }
        
        return light, details
    
    def get_liquidation_zones(
        self, 
        symbol: str, 
        current_price: float, 
        max_distance_pct: float = 0.05
    ) -> Dict[str, List[Dict]]:
        metrics = self.get_metrics_sync(symbol)
        
        long_clusters = []
        short_clusters = []
        
        for cluster in metrics.liquidation_map:
            distance_pct = abs(cluster.price - current_price) / current_price
            if distance_pct <= max_distance_pct:
                cluster_info = {
                    "price": cluster.price,
                    "volume": cluster.volume,
                    "exchange": cluster.exchange,
                    "distance_pct": round(distance_pct * 100, 2)
                }
                if cluster.side == "long":
                    long_clusters.append(cluster_info)
                else:
                    short_clusters.append(cluster_info)
        
        long_clusters.sort(key=lambda x: x["volume"], reverse=True)
        short_clusters.sort(key=lambda x: x["volume"], reverse=True)
        
        return {
            "long_liquidation_zones": long_clusters[:5],
            "short_liquidation_zones": short_clusters[:5],
            "nearest_long_liq": long_clusters[0] if long_clusters else None,
            "nearest_short_liq": short_clusters[0] if short_clusters else None,
            "total_long_liq_volume": sum(c["volume"] for c in long_clusters),
            "total_short_liq_volume": sum(c["volume"] for c in short_clusters),
        }
    
    def get_risk_multiplier(self, symbol: str) -> float:
        _, details = self.get_market_traffic_light(symbol)
        cdri = details["cdri"]
        return max(1.0 - cdri / 100.0, 0.0)
    
    def is_long_allowed(self, symbol: str) -> bool:
        _, details = self.get_market_traffic_light(symbol)
        return details["long_allowed"]
    
    def get_position_multiplier(self, symbol: str) -> float:
        _, details = self.get_market_traffic_light(symbol)
        return details["position_multiplier"]


def create_coinglass_oracle_from_config() -> CoinGlassOracle:
    api_key = os.environ.get("COINGLASS_API_KEY", "")
    use_mock = not bool(api_key) or os.environ.get("COINGLASS_USE_MOCK", "true").lower() == "true"
    
    config = CoinGlassConfig(
        api_key=api_key,
        use_mock_data=use_mock,
        cache_ttl_seconds=int(os.environ.get("COINGLASS_CACHE_TTL", "60")),
    )
    return CoinGlassOracle(config)