"""
Central Strategy Registry for Darwin Trader algorithmic trading engines.
"""
from typing import Dict, List, Type

from strategy_engine.strategy_base import BaseStrategy
from strategy_engine.sample_strategy import DarwinTrendStrategy
from strategy_engine.strategies.darwinx_zero_trader import DarwinXZeroTraderStrategy

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {
    "darwin_trend": DarwinTrendStrategy,
    "darwinx_zero_trader": DarwinXZeroTraderStrategy,
}


def get_strategy(strategy_id: str) -> Type[BaseStrategy]:
    """Retrieves strategy class by its registered identifier."""
    if strategy_id not in STRATEGY_REGISTRY:
        raise KeyError(f"Strategy '{strategy_id}' not found in STRATEGY_REGISTRY. Available: {list_strategies()}")
    return STRATEGY_REGISTRY[strategy_id]


def list_strategies() -> List[str]:
    """Returns a list of all registered strategy identifiers."""
    return list(STRATEGY_REGISTRY.keys())
