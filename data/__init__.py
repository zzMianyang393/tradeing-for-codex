from .funding_rate import FundingRate, add_funding_features
from .open_interest import OpenInterest, add_oi_features
from .trades_flow import TradesFlow, add_flow_features

try:
    from .fetcher import DataFetcher
except ImportError:
    DataFetcher = None  # ccxt not installed

try:
    from .storage import DataStorage
except ImportError:
    DataStorage = None  # pandas/loguru not installed

try:
    from .hot_coins import HotCoinSelector
except ImportError:
    HotCoinSelector = None  # ccxt/loguru not installed

__all__ = [
    "DataFetcher", "DataStorage", "HotCoinSelector",
    "FundingRate", "add_funding_features",
    "OpenInterest", "add_oi_features",
    "TradesFlow", "add_flow_features",
]
