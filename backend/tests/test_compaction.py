"""Tests 16c — compaction du contexte dans run_agent (sliding window + résumé
untrusted + memory flush), et fonctions pures de agent/compaction.py."""

from datetime import UTC, datetime

from test_agent_loop import (
    FINAL_WITH_PRICE,
    FakeLlm,
    FakeMarket,
    make_response,
    quote_tool_call,
)
from test_memory_temporal import FakeTemporalMemoryStore
from test_sse import FakeTraceStore

from investia.agent import run_agent
from investia.agent.compaction import (
    compact_messages,
    estimate_tokens,
    parse_memoires,
)
from investia.agent.prompts import SYSTEM_PROMPT
from investia.market.base import MarketData
from investia.tools import build_tools

QUESTION = "Quel est le prix de AAPL ?"

QUOTE = MarketData(
    value=344.63,
    currency="USD",
    source="finnhub",
    timestamp=datetime(2026, 10, 31, tzinfo=UTC),
)


# --- fonctions pures ----------------------------------------------------------


def test_estimate_tokens_uses_chars_over_4():
    messages = [{"role": "user", "content": "a" * 400}]
    assert estimate_tokens(messages) == 100
    assert estimate_tokens([]) == 0


def test_parse_memoires_extracts_memoir_lines():
    text = (
        "Résumé du run.\nMEMOIRE: l'utilisateur préfère un profil prudent\n"
        "fin\nMEMOIRE: horizon 10 ans\n"
    )
    assert parse_memoires(text) == [
        "l'utilisateur préfère un profil prudent",
        "horizon 10 ans",
    ]
    assert parse_memoires("rien") == []


async def test_compact_messages_keeps_head_and_last_turns_and_marks_summary_untrusted():
    llm = FakeLlm([make_response(content="RÉSUMÉ DU MILIEU\nMEMOIRE: fait durable")])
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "tour1"},
        {"role": "tool", "content": "résultat1"},
        {"role": "assistant", "content": "tour2"},
        {"role": "tool", "content": "résultat2"},
        {"role": "assistant", "content": "tour3"},
    ]
    new_messages, meta = await compact_messages(
        messages, llm=llm, model_key="m", max_tokens=1, keep_last_turns=1
    )
    assert meta["compacted"] is True
    assert meta["dropped_messages"] == 4  # blocs tour1+r1 et tour2+r2 lâchés
    # head conservé, puis le résumé marqué NON FIABLE, puis le dernier tour intact
    assert new_messages[0] == {"role": "system", "content": "SYS"}
    assert new_messages[1] == {"role": "user", "content": "Q"}
    assert new_messages[2]["role"] == "system"
    assert "NON FIABLE" in new_messages[2]["content"]
    assert "RÉSUMÉ DU MILIEU" in new_messages[2]["content"]
    assert new_messages[3] == {"role": "assistant", "content": "tour3"}
    assert meta["summary"].startswith("RÉSUMÉ")


async def test_compact_messages_noop_when_under_threshold():
    llm = FakeLlm([make_response(content="inutile")])
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}]
    new_messages, meta = await compact_messages(
        messages, llm=llm, model_key="m", max_tokens=10_000, keep_last_turns=4
    )
    assert meta["compacted"] is False
    assert new_messages == messages
    assert llm.calls == []  # pas d'appel LLM si pas de compaction


# --- run_agent : déclenchement, event, memory flush ----------------------------


async def test_run_agent_compacts_when_over_threshold_and_flushes_memory():
    # Seuil juste au-dessus du contexte initial : la compaction se déclenche au tour 2.
    base = estimate_tokens(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ]
    )
    long_turn1 = "analyse intermédiaire " * 50  # le tour 1 fait dépasser le seuil
    summary = "Résumé du run.\nMEMOIRE: l'utilisateur a un profil prudent"
    llm = FakeLlm(
        [
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content=summary),  # appel de résumé (compaction, tour 3)
            make_response(content=FINAL_WITH_PRICE),  # réponse finale du tour 3
        ]
    )
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    memory = FakeTemporalMemoryStore()
    result = await run_agent(
        QUESTION,
        llm,
        build_tools(FakeMarket(quote=QUOTE)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        context_max_tokens=base + 10,
        keep_last_turns=1,
        memory_store=memory,
    )
    assert result.status == "ok"
    assert result.compactions == 1
    kinds = [k for k, _ in events]
    assert "compaction" in kinds
    compaction = next(p for k, p in events if k == "compaction")
    assert compaction["dropped_messages"] > 0
    # memory flush : le fait MEMOIRE: du résumé est sauvé (dédup 16a)
    saved = [r["content"] for r in memory.rows.values()]
    assert any("profil prudent" in c for c in saved)
    # le 4e appel LLM (tour 3 réel, après la compaction) reçoit le résumé untrusted
    turn3_messages = llm.calls[3]["messages"]
    system_msgs = [m for m in turn3_messages if m["role"] == "system"]
    assert any("NON FIABLE" in m["content"] for m in system_msgs)
    assert turn3_messages[0]["content"] == SYSTEM_PROMPT
    assert turn3_messages[1] == {"role": "user", "content": QUESTION}


# --- 17d : working set verbatim + stamp + hook PreCompact ----------------------


async def test_compact_messages_keeps_user_and_tool_errors_verbatim_in_working_set():
    llm = FakeLlm([make_response(content="RÉSUMÉ DU MILIEU")])
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "tour1"},
        {"role": "user", "content": "Q2 au milieu"},  # user dans un bloc lâché
        {
            "role": "tool",
            "content": "ToolError: sandbox indisponible pour /tmp/x.py",
            "is_error": True,
        },
        {"role": "assistant", "content": "tour2"},
        {"role": "tool", "content": "ok"},
        {"role": "assistant", "content": "tour3"},
    ]
    new_messages, meta = await compact_messages(
        messages, llm=llm, model_key="m", max_tokens=1, keep_last_turns=1
    )
    assert meta["compacted"] is True
    # working set verbatim : distinct du résumé, contient user + erreur exacts
    ws = [
        m
        for m in new_messages
        if m["role"] == "system" and "working set" in str(m["content"]).lower()
    ]
    assert len(ws) == 1
    assert "Q2 au milieu" in ws[0]["content"]
    assert "ToolError: sandbox indisponible pour /tmp/x.py" in ws[0]["content"]
    # le résumé reste NON FIABLE, distinct du working set, et horodaté (stamp)
    summary = next(m for m in new_messages if "NON FIABLE" in str(m.get("content", "")))
    assert "RÉSUMÉ DU MILIEU" in summary["content"]
    assert "compacté le" in summary["content"]
    assert meta["compacted_at"]
    datetime.fromisoformat(meta["compacted_at"])  # ISO 8601 valide


async def test_compact_messages_no_working_set_message_when_nothing_to_keep():
    # zéro régression 16c : si aucun user/erreur dans les blocs lâchés,
    # aucun message working set n'est inséré (layout identique à 16c)
    llm = FakeLlm([make_response(content="RÉSUMÉ")])
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "tour1"},
        {"role": "tool", "content": "résultat1"},
        {"role": "assistant", "content": "tour2"},
    ]
    new_messages, meta = await compact_messages(
        messages, llm=llm, model_key="m", max_tokens=1, keep_last_turns=1
    )
    assert meta["compacted"] is True
    assert all(
        "working set" not in str(m.get("content", "")).lower() for m in new_messages
    )
    assert new_messages[-1] == {"role": "assistant", "content": "tour2"}


async def test_run_agent_pre_compact_veto_skips_compaction():
    base = estimate_tokens(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ]
    )
    long_turn1 = "analyse intermédiaire " * 50
    llm = FakeLlm(
        [
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    calls_seen: list[int] = []

    async def pre_compact(messages, estimated_tokens, context_max_tokens):
        calls_seen.append(estimated_tokens)
        assert estimated_tokens > context_max_tokens
        return False  # veto

    result = await run_agent(
        QUESTION,
        llm,
        build_tools(FakeMarket(quote=QUOTE)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        context_max_tokens=base + 10,
        keep_last_turns=1,
        pre_compact=pre_compact,
    )
    assert result.status == "ok"
    assert result.compactions == 0
    kinds = [k for k, _ in events]
    assert "compaction_vetoed" in kinds
    assert "compaction" not in kinds
    assert calls_seen  # le hook a bien été appelé
    # aucun résumé inséré : le dernier appel LLM a vu tout l'historique
    assert all(
        "NON FIABLE" not in str(m.get("content", "")) for m in llm.calls[-1]["messages"]
    )


async def test_run_agent_pre_compact_allow_compacts_normally():
    base = estimate_tokens(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ]
    )
    long_turn1 = "analyse intermédiaire " * 50
    llm = FakeLlm(
        [
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content=long_turn1, tool_calls=quote_tool_call()),
            make_response(content="Résumé."),  # appel de résumé (compaction)
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    def pre_compact(messages, estimated_tokens, context_max_tokens):
        return True  # hook synchrone accepté aussi

    result = await run_agent(
        QUESTION,
        llm,
        build_tools(FakeMarket(quote=QUOTE)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        context_max_tokens=base + 10,
        keep_last_turns=1,
        pre_compact=pre_compact,
    )
    assert result.status == "ok"
    assert result.compactions == 1
    kinds = [k for k, _ in events]
    assert "compaction" in kinds
    assert "compaction_vetoed" not in kinds


async def test_run_agent_without_threshold_never_compacts():
    llm = FakeLlm(
        [
            make_response(content="x", tool_calls=quote_tool_call()),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    result = await run_agent(
        QUESTION,
        llm,
        build_tools(FakeMarket(quote=QUOTE)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        context_max_tokens=None,  # défaut : désactivé
    )
    assert result.status == "ok"
    assert result.compactions == 0
    assert "compaction" not in [k for k, _ in events]
    # le 2e appel LLM a vu tout l'historique (aucun résumé inséré)
    assert all(
        "NON FIABLE" not in str(m.get("content", "")) for m in llm.calls[1]["messages"]
    )
