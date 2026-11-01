"""Routeur de sources : quel connecteur pour quel symbole et quel besoin ?"""

EUROPEAN_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".MC", ".LS", ".SW", ".HE")
FX_SYMBOLS = {"USD", "EUR", "GBP", "CHF", "JPY"}
US_HISTORY_CASCADE = ("yahoo", "eodhd", "twelvedata", "massive")


def pick_sources(symbol: str, kind: str = "quote") -> list[str]:
    """Sources compétentes pour un symbole et un type de donnée, dans l'ordre d'essai.

    - quote : Europe -> yahoo (delayed), US -> finnhub, crypto/fx idem
    - history : Europe -> eodhd (EOD propre), crypto/fx idem ; US -> cascade
      yahoo, puis eodhd, twelvedata, massive (plan B, plan C, plan D : spec 4.4d)
    - news : US -> finnhub (Europe payante -> erreur claire)
    """
    upper = symbol.upper()
    is_europe = upper.endswith(EUROPEAN_SUFFIXES)
    is_crypto = upper.endswith("-USD")
    is_fx = upper in FX_SYMBOLS or (len(upper) == 6 and upper.isalpha())

    if kind == "history":
        if is_europe:
            return ["eodhd"]
        if is_crypto:
            return ["coingecko"]
        if is_fx:
            return ["frankfurter"]
        return list(US_HISTORY_CASCADE)
    if kind == "news":
        return ["finnhub"]
    # quote
    if is_europe:
        return ["yahoo"]
    if is_crypto:
        return ["coingecko"]
    if is_fx:
        return ["frankfurter"]
    return ["finnhub"]


def pick_source(symbol: str, kind: str = "quote") -> str:
    """Première source de la liste (source principale) pour un symbole."""
    return pick_sources(symbol, kind)[0]
