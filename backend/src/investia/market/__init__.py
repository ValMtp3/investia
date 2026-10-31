"""Package market : connecteurs de données + cache + façade."""

from investia.config import Settings
from investia.market.coingecko import CoinGeckoConnector
from investia.market.eodhd import EodhdConnector
from investia.market.finnhub import FinnhubConnector
from investia.market.frankfurter import FrankfurterConnector
from investia.market.service import MarketService
from investia.market.yahoo import YahooConnector


def build_market_service(settings: Settings) -> MarketService:
    """Construit le service avec les vrais connecteurs depuis la configuration.

    Un connecteur n'est instancié que si sa clé API est présente : appeler une
    source sans clé lève une MarketDataError claire côté service.
    """
    connectors: dict = {
        "yahoo": YahooConnector(),
        "frankfurter": FrankfurterConnector(),
    }
    if settings.finnhub_api_key is not None:
        connectors["finnhub"] = FinnhubConnector(api_key=settings.finnhub_api_key)
    if settings.eodhd_api_key is not None:
        connectors["eodhd"] = EodhdConnector(api_key=settings.eodhd_api_key)
    if settings.coingecko_demo_api_key is not None:
        connectors["coingecko"] = CoinGeckoConnector(
            api_key=settings.coingecko_demo_api_key
        )
    return MarketService(connectors=connectors)
