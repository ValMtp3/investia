"""Tests TDD de l'outil read_pdf (Nutrient DWS API) — MockTransport, zéro réseau."""

import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from investia.tools.base import ToolError
from investia.tools.pdf import (
    MAX_PDF_BYTES,
    MAX_TEXT_CHARS,
    NutrientPdfReader,
    ReadPdfArgs,
    ReadPdfTool,
)

PDF_URL = "https://example.com/rapport-annuel.pdf"
FAKE_PDF = b"%PDF-1.4 fake bytes"


def make_reader(handler, api_key="nut-test"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return NutrientPdfReader(
        api_key=SecretStr(api_key) if api_key else None, http_client=http
    )


def nutrient_payload(pages_text: list[str]) -> dict:
    return {"data": {"pages": [{"plainText": t} for t in pages_text]}}


def handler_ok(pages_text: list[str], pdf_bytes: bytes = FAKE_PDF):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            return httpx.Response(200, json=nutrient_payload(pages_text))
        if str(request.url) == PDF_URL:
            return httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        return httpx.Response(404)

    return handler


async def test_sans_cle_raise_tool_error():
    reader = make_reader(handler_ok(["x"]), api_key=None)
    with pytest.raises(ToolError, match="clé"):
        await reader.extract_text(PDF_URL, max_pages=5)


async def test_url_non_pdf_vers_tool_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            return httpx.Response(200, json=nutrient_payload(["x"]))
        return httpx.Response(
            200,
            content=b"<html>pas un pdf</html>",
            headers={"content-type": "text/html"},
        )

    reader = make_reader(handler)
    with pytest.raises(ToolError, match="PDF"):
        await reader.extract_text("https://example.com/page", max_pages=5)


async def test_extension_pdf_suffit_sans_content_type():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            return httpx.Response(200, json=nutrient_payload(["texte"]))
        return httpx.Response(200, content=FAKE_PDF)  # pas de content-type

    reader = make_reader(handler)
    assert await reader.extract_text(PDF_URL, max_pages=1) == "texte"


async def test_telechargement_404_vers_tool_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    reader = make_reader(handler)
    with pytest.raises(ToolError, match="404"):
        await reader.extract_text(PDF_URL, max_pages=5)


async def test_pdf_trop_volumineux_vers_tool_error():
    big = b"x" * (MAX_PDF_BYTES + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            return httpx.Response(200, json=nutrient_payload(["x"]))
        return httpx.Response(
            200, content=big, headers={"content-type": "application/pdf"}
        )

    reader = make_reader(handler)
    with pytest.raises(ToolError, match="volumineux"):
        await reader.extract_text(PDF_URL, max_pages=5)


async def test_succes_envoie_multipart_build_et_retourne_texte():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = request.content
            seen["content_type"] = request.headers.get("content-type", "")
            return httpx.Response(200, json=nutrient_payload(["page un", "page deux"]))
        return httpx.Response(
            200, content=FAKE_PDF, headers={"content-type": "application/pdf"}
        )

    reader = make_reader(handler)
    text = await reader.extract_text(PDF_URL, max_pages=3)

    assert text == "page un\n\npage deux"
    assert seen["auth"] == "Bearer nut-test"
    assert "multipart/form-data" in seen["content_type"]
    body = seen["body"]
    # le fichier PDF est uploadé en binaire, pas l'URL (pas de fetch serveur / SSRF)
    assert FAKE_PDF in body
    assert PDF_URL.encode() not in body
    # instructions attendues, sérialisées comme le client officiel
    expected_instructions = {
        "parts": [{"file": "asset_0", "pages": {"start": 0, "end": 2}}],
        "output": {"type": "json-content", "plainText": True, "tables": False},
    }
    assert json.dumps(expected_instructions).encode() in body


async def test_texte_tronque_a_20000_caracteres():
    long_text = "a" * (MAX_TEXT_CHARS + 5000)
    reader = make_reader(handler_ok([long_text]))
    text = await reader.extract_text(PDF_URL, max_pages=20)
    assert len(text) == MAX_TEXT_CHARS


async def test_nutrient_500_vers_tool_error_lisible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/build":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200, content=FAKE_PDF, headers={"content-type": "application/pdf"}
        )

    reader = make_reader(handler)
    with pytest.raises(ToolError, match="500"):
        await reader.extract_text(PDF_URL, max_pages=5)


def test_args_valident_max_pages_1_a_20_et_url_http():
    with pytest.raises(ValidationError):
        ReadPdfArgs(url=PDF_URL, max_pages=0)
    with pytest.raises(ValidationError):
        ReadPdfArgs(url=PDF_URL, max_pages=21)
    with pytest.raises(ValidationError):
        ReadPdfArgs(url="file:///etc/passwd", max_pages=5)
    with pytest.raises(ValidationError):
        ReadPdfArgs(url="ftp://x/y.pdf", max_pages=5)
    assert ReadPdfArgs(url=PDF_URL, max_pages=20).max_pages == 20


async def test_tool_run_renvoie_source_timestamp_chars():
    tool = ReadPdfTool(make_reader(handler_ok(["contenu pdf"])))
    out = await tool.run(ReadPdfArgs(url=PDF_URL, max_pages=2))
    assert out["source"] == "nutrient"
    assert "timestamp" in out
    assert out["text"] == "contenu pdf"
    assert out["chars"] == len("contenu pdf")
    assert out["url"] == PDF_URL
