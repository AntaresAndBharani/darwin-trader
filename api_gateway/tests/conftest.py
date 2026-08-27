"""
Pytest configuration and test isolation fixtures for API Gateway tests.
"""
import pytest
from strategy_engine.config import StrategyConfig
from strategy_engine.models import StrategyStatus
from api_gateway.routes_strategy import connector, global_config
import api_gateway.routes_strategy as routes_strategy


@pytest.fixture(autouse=True)
def reset_shared_state():
    """
    Autouse fixture that resets module-level connector and global_config singleton
    state before and after each test for full test isolation.
    """
    def _reset():
        global_config.reset_from(StrategyConfig(mock_mode=True))
        connector.__init__(global_config)
        connector.initialize()
        routes_strategy.current_status = StrategyStatus.IDLE

    _reset()
    yield
    _reset()
