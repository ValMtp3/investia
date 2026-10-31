"""Routeur de sources : quel connecteur pour quel symbole ?"""

EUROPEAN_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".MC", ".LS", ".SW", ".HE")
FX_SYMBOLS = {"USD", "EUR", "GBP", "CHF", "JPY"}


def pick_source(symbol: str) -> str:
    """Nom de la source compétente pour un symbole.

    - suffixe européen (.DE, .PA, ...) -> yahoo (P8)
    - crypto (BTC-USD) -> coingecko
    - devise seule ou paire 6 lettres (EURUSD) -> frankfurter
    - sinon (US) -> finnhub
    """
    upper = symbol.upper()
    if upper.endswith(EUROPEAN_SUFFIXES):
        return "yahoo"
    if upper.endswith("-USD"):
        return "coingecko"
    if upper in FX_SYMBOLS or (len(upper) == 6 and upper.isalpha()):
        return "frankfurter"
    return "finnhub"
