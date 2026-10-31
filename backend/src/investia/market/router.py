"""Routeur de sources : quel connecteur pour quel symbole et quel besoin ?"""

EUROPEAN_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".MC", ".LS", ".SW", ".HE")
FX_SYMBOLS = {"USD", "EUR", "GBP", "CHF", "JPY"}


def pick_source(symbol: str, kind: str = "quote") -> str:
    """Nom de la source compétente pour un symbole et un type de donnée.

    - quote : Europe -> yahoo (delayed), US -> finnhub, crypto/fx idem
    - history : Europe -> eodhd (EOD propre), US -> yahoo, crypto/fx idem
    - news : US -> finnhub (Europe payante -> erreur claire)
    """
    upper = symbol.upper()
    is_europe = upper.endswith(EUROPEAN_SUFFIXES)
    is_crypto = upper.endswith("-USD")
    is_fx = upper in FX_SYMBOLS or (len(upper) == 6 and upper.isalpha())

    if kind == "history":
        if is_europe:
            return "eodhd"
        if is_crypto:
            return "coingecko"
        if is_fx:
            return "frankfurter"
        return "yahoo"
    if kind == "news":
        return "finnhub"
    # quote
    if is_europe:
        return "yahoo"
    if is_crypto:
        return "coingecko"
    if is_fx:
        return "frankfurter"
    return "finnhub"
