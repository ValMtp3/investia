"""Générateur garak custom : la cible scannée est notre harness complet (23j).

Chaque prompt de sonde garak passe par `run_agent` (boucle + outils + garde-fous
en code + canary 23b + redaction secrets), comme en production. Le LLM utilisé
est soit injecté (tests), soit construit depuis l'environnement (VPS, vraies
clés via LiteLLM — jamais commitées).
"""

import asyncio
from typing import Any

from garak.attempt import Conversation, Message
from garak.generators.base import Generator


class InvestiaGenerator(Generator):
    """Cible garak = run_agent Investia (harness maison, défenses actives)."""

    generator_family_name = "investia"
    DEFAULT_PARAMS = Generator.DEFAULT_PARAMS | {
        "temperature": 0.0,  # scan déterministe
    }

    def __init__(
        self, name: str = "harness", llm: Any | None = None, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._llm = llm

    def _build_llm(self) -> Any:
        if self._llm is not None:
            return self._llm
        from investia.config import Settings
        from investia.llm import build_llm_client

        return build_llm_client(Settings())

    def _call_model(
        self, prompt: Conversation, generations_this_call: int = 1
    ) -> list[Message | None]:
        last = prompt.last_message()
        text = last.text if last is not None and last.text else ""
        from investia.agent import run_agent
        from investia.evals.runner import MockMarket
        from investia.tools import build_tools

        llm = self._build_llm()
        tools = build_tools(MockMarket())
        result = asyncio.run(run_agent(text, llm, tools))
        answer = result.answer or ""
        return [Message(text=answer) for _ in range(generations_this_call)]
