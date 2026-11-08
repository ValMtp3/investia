"""Spans OpenTelemetry GenAI (`gen_ai.*`) — étape 9, D38.

Un span par appel LLM (`gen_ai.chat`) et par appel d'outil (`tool.call`), exporté
vers PostgreSQL (table `otel_spans`) via un exporter OTel custom. Le `run_id`
courant est propagé par un ContextVar posé par la boucle d'agent.

Sans init (tests, CLI hors run) : tout est no-op, zéro régression.
"""

import contextvars
import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "investia_run_id", default=None
)

_TRACER: trace.Tracer | None = None


def _span_to_dict(span: Any) -> dict[str, Any]:
    """Sérialise un ReadableSpan pour l'export (attributs gen_ai.* + run_id)."""
    attrs = {str(k): v for k, v in (span.attributes or {}).items()}
    return {
        "span_id": span.context.span_id,
        "trace_id": span.context.trace_id,
        "parent_span_id": span.parent.span_id if span.parent else None,
        "name": span.name,
        "run_id": current_run_id.get(),
        "start": span.start_time,
        "end": span.end_time,
        "duration_ms": (
            (span.end_time - span.start_time) / 1e6 if span.end_time else None
        ),
        "attributes": attrs,
        "status": span.status.status_code.name,
        "error": attrs.get("error.type"),
    }


class InMemorySpanExporter(SpanExporter):
    """Exporter de test : collecte les spans en mémoire."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []

    def export(self, spans: Any) -> SpanExportResult:
        self.spans.extend(_span_to_dict(s) for s in spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None: ...


class PgSpanExporter(SpanExporter):
    """Exporte chaque span dans la table `otel_spans` (une requête par span)."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def export(self, spans: Any) -> SpanExportResult:
        import asyncio

        async def _write() -> None:
            for span in spans:
                data = _span_to_dict(span)
                async with self._session_factory() as session:
                    await session.execute(
                        __import__("sqlalchemy").text(
                            "INSERT INTO otel_spans "
                            "(span_id, trace_id, parent_span_id, run_id, name, "
                            "start_ts, end_ts, attributes, status, error) "
                            "VALUES (:span_id, :trace_id, :parent_span_id, :run_id, "
                            ":name, :start_ts, :end_ts, :attributes, :status, :error)"
                        ),
                        {
                            "span_id": str(data["span_id"]),
                            "trace_id": str(data["trace_id"]),
                            "parent_span_id": (
                                str(data["parent_span_id"])
                                if data["parent_span_id"]
                                else None
                            ),
                            "run_id": (
                                UUID(data["run_id"]) if data["run_id"] else None
                            ),
                            "name": data["name"],
                            "start_ts": datetime.fromtimestamp(
                                data["start"] / 1e9, tz=UTC
                            ),
                            "end_ts": (
                                datetime.fromtimestamp(data["end"] / 1e9, tz=UTC)
                                if data["end"]
                                else None
                            ),
                            "attributes": json.dumps(
                                data["attributes"], default=str, ensure_ascii=False
                            ),
                            "status": data["status"],
                            "error": data["error"],
                        },
                    )
                    await session.commit()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_write())
        except Exception:
            logger.exception("otel: export PostgreSQL échoué")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None: ...


class _Dispatcher(SpanProcessor):
    """Processor unique : dispatch vers l'exporter courant (remplaçable à chaud).

    Évite trace.set_tracer_provider (interdit après le 1er appel) : un seul
    provider local, l'exporter se branche/débranche via init_otel/reset_otel.
    """

    current: SpanExporter | None = None

    def on_start(self, span: Any, parent_context: Any = None) -> None: ...

    def on_end(self, span: Any) -> None:
        if _Dispatcher.current is not None:
            _Dispatcher.current.export([span])

    def shutdown(self) -> None: ...

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_PROVIDER: TracerProvider | None = None


def init_otel(
    exporter: SpanExporter | None = None, session_factory: Any = None
) -> None:
    """Branche l'exporter OTel. Sans exporter ni session_factory : no-op.

    Appelable plusieurs fois (tests) : remplace juste l'exporter courant.
    """
    global _PROVIDER, _TRACER
    if _PROVIDER is None:
        _PROVIDER = TracerProvider()
        _PROVIDER.add_span_processor(_Dispatcher())
    if _TRACER is None:
        _TRACER = _PROVIDER.get_tracer("investia", "1.0.0")
    if exporter is not None:
        _Dispatcher.current = exporter
    elif session_factory is not None:
        _Dispatcher.current = PgSpanExporter(session_factory)
    else:
        _Dispatcher.current = None


def reset_otel() -> None:
    """Débranche l'exporter (tests) : les spans redeviennent no-op.

    Le provider/tracer restent en place (set_tracer_provider est à usage unique) ;
    c'est `_Dispatcher.current = None` qui rend les spans no-op.
    """
    _Dispatcher.current = None


def _tracer() -> trace.Tracer | None:
    return _TRACER


@asynccontextmanager
async def start_chat_span(model: str, model_key: str):
    """Span `gen_ai.chat` autour d'un appel LLM. Yield un dict d'attributs à
    compléter (usage tokens, coût) ; l'erreur éventuelle marque le span ERROR."""
    tracer = _tracer()
    if tracer is None:
        yield {}
        return
    with tracer.start_as_current_span("gen_ai.chat") as span:
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": "litellm",
            "gen_ai.request.model": model,
        }
        span.set_attributes(attrs)
        try:
            yield attrs
        except Exception as error:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("error.type", type(error).__name__)
            raise
        else:
            span.set_status(Status(StatusCode.OK))
        finally:
            for key, value in attrs.items():
                if key not in ("gen_ai.operation.name", "gen_ai.system"):
                    span.set_attribute(key, value)


@asynccontextmanager
async def start_tool_span(name: str, arguments: dict[str, Any] | None = None):
    """Span `tool.call` autour d'un appel d'outil (arguments tronqués à 200 car.)."""
    tracer = _tracer()
    if tracer is None:
        yield {}
        return
    with tracer.start_as_current_span("tool.call") as span:
        attrs: dict[str, Any] = {"gen_ai.tool.name": name}
        if arguments is not None:
            attrs["gen_ai.tool.arguments"] = json.dumps(
                arguments, default=str, ensure_ascii=False
            )[:200]
        span.set_attributes(attrs)
        try:
            yield attrs
        except Exception as error:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("error.type", type(error).__name__)
            attrs["tool.ok"] = False
            raise
        else:
            span.set_status(Status(StatusCode.OK))
            attrs["tool.ok"] = True
        finally:
            for key, value in attrs.items():
                if key != "gen_ai.tool.name":
                    span.set_attribute(key, value)
