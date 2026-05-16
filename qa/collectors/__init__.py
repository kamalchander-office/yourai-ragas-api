"""Response collectors for different API backends."""

from qa.collectors.mock_collector import collect_with_mock_api
from qa.collectors.yourai_collector import collect_with_yourai_api

__all__ = ["collect_with_mock_api", "collect_with_yourai_api"]
