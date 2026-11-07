"""Agent cards A2A v1.0 des 3 agents spécialisés (étape 6.1)."""

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


def build_agent_card(name: str, base_url: str = "") -> AgentCard:
    """Card A2A v1.0 de l'agent `name`, servie sous /api/agents/<name>/.

    L'interface annonce l'URL absolue du endpoint JSON-RPC (les clients A2A
    envoient leurs requêtes directement à cette URL).
    """
    base = base_url or ""
    url = f"{base}/api/agents/{name}/jsonrpc"
    description = DESCRIPTIONS[name]
    return AgentCard(
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
