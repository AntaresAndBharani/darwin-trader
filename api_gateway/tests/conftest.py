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
        fresh_config = StrategyConfig(mock_mode=True)
        global_config.__dict__.clear()
        global_config.__dict__.update(fresh_config.__dict__)
        if hasattr(global_config, "__pydantic_fields_set__"):
            global_config.__pydantic_fields_set__.clear()
            global_config.__pydantic_fields_set__.update(fresh_config.__pydantic_fields_set__)
        connector.__init__(global_config)
        connector.initialize()
        routes_strategy.current_status = StrategyStatus.IDLE

    _reset()
    yield
    _reset()
