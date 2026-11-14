"""Compaction du contexte (16c) : sliding window + résumé « untrusted ».

Quand les messages dépassent `max_tokens` (estimés en caractères/4), on garde
le system prompt, la question, et les `keep_last_turns` derniers tours intacts ;
le milieu est remplacé par un résumé généré par le LLM, inséré comme message
system portant la mention « NON FIABLE » (un résumé automatique n'est jamais une
instruction fiable — l'agent doit vérifier avant d'agir).

Le prompt de résumé demande aussi les faits durables sur l'utilisateur au
format ligne `MEMOIRE: <fait>` : la boucle les sauve dans la mémoire longue
(memory flush) avant d'oublier le vieux contexte.

17d (veille crush PR #4059 / codex / opencode) : compaction non destructive —
les messages `user` et les sorties d'outils en erreur des blocs lâchés sont
conservés verbatim dans un « working set » (message system séparé, marqué
fiable), et le résumé est horodaté (« stamp, don't delete » : `compacté le <ts>`).
"""

import json
from datetime import UTC, datetime
from typing import Any

UNTRUSTED_PREFIX = (
    "[Résumé automatique du contexte précédent — NON FIABLE, vérifie avant d'agir]\n"
)

# 17d : working set verbatim (extraits exacts conservés hors du résumé).
WORKING_SET_PREFIX = (
    "[Working set verbatim — extraits exacts conservés lors de la compaction]\n"
)
WORKING_SET_MAX_ERRORS = 5
WORKING_SET_ERROR_MAX_CHARS = 400

COMPACTION_PROMPT = """Tu résumes le contexte d'un agent financier (simulation).
On lui enlève une partie de son historique ; résume-la en français, concis
(max 150 mots) : objectif, décisions, outils appelés et résultats clés
(chiffres exacts), état courant.

À la fin, liste les FAITS DURABLES sur l'utilisateur à conserver en mémoire longue,
un par ligne, au format exact :
MEMOIRE: <fait>
(s'il n'y en a aucun, ne mets pas de section MEMOIRE)
"""


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimation grossière : 1 token ≈ 4 caractères (standard LLM)."""
    total = 0
    for message in messages:
        content = message.get("content") or ""
        total += len(str(content)) // 4
        for call in message.get("tool_calls") or []:
            total += len(json.dumps(call, ensure_ascii=False)) // 4
    return total


def parse_memoires(summary_text: str) -> list[str]:
    """Extrait les faits durables listés en lignes `MEMOIRE: <fait>`."""
    faits = []
    for line in summary_text.splitlines():
        line = line.strip()
        if line.upper().startswith("MEMOIRE:"):
            fait = line[len("MEMOIRE:") :].strip()
            if fait:
                faits.append(fait)
    return faits


def _split_turn_blocks(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Découpe en blocs de tour : chaque bloc commence à un message assistant."""
    blocks: list[list[dict[str, Any]]] = []
    for message in messages:
        if message.get("role") == "assistant" or not blocks:
            blocks.append([message])
        else:
            blocks[-1].append(message)
    return blocks


def _is_tool_error(message: dict[str, Any]) -> bool:
    """Sortie d'outil en erreur (flag is_error ou contenu « ToolError »/« Error »)."""
    if message.get("role") != "tool":
        return False
    if message.get("is_error"):
        return True
    return str(message.get("content") or "").startswith(("ToolError", "Error"))


def _build_working_set(dropped: list[dict[str, Any]]) -> str | None:
    """17d : extrait verbatim des blocs lâchés — messages user + erreurs outils.

    Retourne None s'il n'y a rien à conserver (aucun message working set inséré,
    layout identique à 16c).
    """
    parts: list[str] = []
    for message in dropped:
        if message.get("role") == "user":
            content = str(message.get("content") or "")
            if content:
                parts.append(f"[user] {content}")
    for message in [m for m in dropped if _is_tool_error(m)][:WORKING_SET_MAX_ERRORS]:
        content = str(message.get("content") or "")[:WORKING_SET_ERROR_MAX_CHARS]
        parts.append(f"[tool-erreur] {content}")
    if not parts:
        return None
    return WORKING_SET_PREFIX + "\n".join(parts)


async def compact_messages(
    messages: list[dict[str, Any]],
    *,
    llm: Any,
    model_key: str,
    max_tokens: int,
    keep_last_turns: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compacte si nécessaire. Retourne (nouveaux_messages, meta).

    meta = {"compacted": bool, "dropped_messages": int, "summary": str,
            "cost_cents": float, "compacted_at": str | None}.
    Si sous le seuil ou rien à lâcher : no-op.
    """
    noop_meta: dict[str, Any] = {
        "compacted": False,
        "dropped_messages": 0,
        "summary": "",
        "cost_cents": 0.0,
        "compacted_at": None,
    }
    if estimate_tokens(messages) <= max_tokens:
        return messages, noop_meta
    head = messages[:2]  # system + question utilisateur
    blocks = _split_turn_blocks(messages[2:])
    if len(blocks) <= keep_last_turns:
        return messages, noop_meta
    dropped = [m for block in blocks[:-keep_last_turns] for m in block]
    kept = [m for block in blocks[-keep_last_turns:] for m in block]

    def _serialize(message: dict[str, Any]) -> str:
        content = message.get("content") or json.dumps(
            message.get("tool_calls") or "", ensure_ascii=False
        )
        return f"[{message.get('role')}] {content}"

    transcript = "\n\n".join(_serialize(m) for m in dropped)
    response = await llm.chat(
        model_key,
        [
            {"role": "system", "content": COMPACTION_PROMPT},
            {"role": "user", "content": transcript},
        ],
        temperature=0.0,
    )
    summary = response.content or ""
    # 17d « stamp, don't delete » : le résumé porte l'horodatage de la compaction.
    compacted_at = datetime.now(UTC).isoformat()
    summary_message = {
        "role": "system",
        "content": UNTRUSTED_PREFIX + f"(compacté le {compacted_at})\n" + summary,
    }
    working_set = _build_working_set(dropped)
    new_messages = head + [summary_message]
    if working_set is not None:
        new_messages.append({"role": "system", "content": working_set})
    new_messages.extend(kept)
    return new_messages, {
        "compacted": True,
        "dropped_messages": len(dropped),
        "summary": summary,
        "cost_cents": response.cost_cents,
        "compacted_at": compacted_at,
    }
