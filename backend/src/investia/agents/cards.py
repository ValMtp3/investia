"""Agent cards A2A v1.0 des 3 agents spécialisés (étape 6.1).

15b : les cards peuvent être signées (JWS, `a2a.utils.signing`) quand une clé
est configurée — voir make_card_signer / verify_agent_card (imports lazy :
PyJWT n'est requis qu'avec la clé).
"""

from collections.abc import Callable

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

AGENT_NAMES = ("analyste", "risque", "redacteur")

DESCRIPTIONS = {
    "analyste": (
        "Analyse les données de marché (cours, historique, indicateurs, actualités) "
        "et l'état du portefeuille simulé, via les outils Investia. Produit une "
        "analyse brute sourcée."
    ),
    "risque": (
        "Vérifie une analyse avec les garde-fous Investia (format, chiffres sourcés, "
        "langage interdit, disclaimer). Renvoie ok ou la liste des échecs."
    ),
    "redacteur": (
        "Rédige la réponse finale structurée (thèse, risques, confiance, sources, "
        "disclaimer « Simulation — pas un conseil en investissement ») à partir de "
        "l'analyse et du verdict du risque."
    ),
}


CardSigner = Callable[[AgentCard], AgentCard]


def make_card_signer(
    signing_key: str, kid: str = "investia-2026", alg: str = "ES256"
) -> CardSigner:
    """Signer de cards (JWS) — import lazy : PyJWT requis seulement ici (15b)."""
    from a2a.utils.signing import ProtectedHeader, create_agent_card_signer

    protected_header: ProtectedHeader = {
        "alg": alg,
        "kid": kid,
        "jku": None,
        "typ": "JOSE",
    }
    return create_agent_card_signer(
        signing_key,
        protected_header=protected_header,
    )


def verify_agent_card(
    card: AgentCard, key: str, algorithms: list[str] | None = None
) -> None:
    """Vérifie les signatures d'une card ; lève si aucune n'est valide (15b)."""
    from a2a.utils.signing import create_signature_verifier

    verifier = create_signature_verifier(
        key_provider=lambda _kid, _jku: key,
        algorithms=algorithms or ["ES256"],
    )
    verifier(card)


def build_agent_card(
    name: str, base_url: str = "", signer: CardSigner | None = None
) -> AgentCard:
    """Card A2A v1.0 de l'agent `name`, servie sous /api/agents/<name>/.

    L'interface annonce l'URL absolue du endpoint JSON-RPC (les clients A2A
    envoient leurs requêtes directement à cette URL). Si `signer` est fourni,
    la card est signée (JWS, 15b).
    """
    base = base_url or ""
    url = f"{base}/api/agents/{name}/jsonrpc"
    description = DESCRIPTIONS[name]
    card = AgentCard(
        name=name,
        description=description,
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0"),
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=name,
                name=name,
                description=description,
                tags=["investia", "simulation"],
            )
        ],
    )
    if signer is not None:
        card = signer(card)
    return card
