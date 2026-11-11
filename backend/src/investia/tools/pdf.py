"""Outil read_pdf — extraction de texte d'un PDF distant via Nutrient DWS (étape 12f).

Lecture seule. Sans clé NUTRIENT_API_KEY -> ToolError clair, jamais de contenu inventé.
Le PDF est téléchargé localement (limite 20 Mo, vérification du type) puis uploadé
en multipart à POST {base}/build — contrat vérifié contre le client officiel
nutrient-dws-client-python (pspdfkit/nutrient-dws-client-python, src/nutrient_dws).
"""

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, SecretStr, field_validator

from investia.tools.base import BaseTool, ToolError

NUTRIENT_BASE_URL = "https://api.nutrient.io"
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 Mo
MAX_TEXT_CHARS = 20_000
DOWNLOAD_TIMEOUT = 30.0


class PdfReader(Protocol):
    async def extract_text(self, url: str, max_pages: int) -> str: ...


class ReadPdfArgs(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    max_pages: int = Field(5, ge=1, le=20)

    @field_validator("url")
    @classmethod
    def url_http_uniquement(cls, value: str) -> str:
        scheme = urlparse(value).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError("url http(s) uniquement")
        return value


def _is_pdf(url: str, content_type: str) -> bool:
    """Un PDF = content-type application/pdf OU extension .pdf dans l'URL."""
    return content_type.split(";")[0].strip().lower() == "application/pdf" or urlparse(
        url
    ).path.lower().endswith(".pdf")


class NutrientPdfReader:
    """Client Nutrient DWS (Processor API) — POST /build en multipart/form-data."""

    def __init__(
        self,
        api_key: SecretStr | None,
        base_url: str = NUTRIENT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def extract_text(self, url: str, max_pages: int) -> str:
        if self._api_key is None:
            raise ToolError(
                "read_pdf", "clé manquante : NUTRIENT_API_KEY non renseignée"
            )
        pdf_bytes = await self._download(url)
        instructions = {
            "parts": [{"file": "asset_0", "pages": {"start": 0, "end": max_pages - 1}}],
            "output": {"type": "json-content", "plainText": True, "tables": False},
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/build",
                headers={
                    "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    "Accept": "application/json",
                },
                data={"instructions": json.dumps(instructions)},
                files={"asset_0": ("document.pdf", pdf_bytes, "application/pdf")},
            )
        except httpx.HTTPError as error:
            raise ToolError("read_pdf", f"erreur réseau Nutrient : {error}") from error
        if response.status_code != 200:
            raise ToolError(
                "read_pdf",
                f"Nutrient HTTP {response.status_code} (quota ou clé invalide)",
            )
        data = response.json()
        pages = (data.get("data") or {}).get("pages") or []
        text = "\n\n".join(str(page.get("plainText", "")) for page in pages)
        return text[:MAX_TEXT_CHARS]

    async def _download(self, url: str) -> bytes:
        try:
            response = await self._client.get(
                url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True
            )
        except httpx.HTTPError as error:
            raise ToolError(
                "read_pdf", f"téléchargement impossible : {error}"
            ) from error
        if response.status_code != 200:
            raise ToolError(
                "read_pdf", f"téléchargement du PDF : HTTP {response.status_code}"
            )
        content_type = response.headers.get("content-type", "")
        if not _is_pdf(str(response.url), content_type):
            raise ToolError("read_pdf", "l'URL ne pointe pas vers un PDF")
        content_length = response.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_PDF_BYTES:
            raise ToolError(
                "read_pdf", f"PDF trop volumineux ({content_length} o > 20 Mo)"
            )
        content = response.content
        if len(content) > MAX_PDF_BYTES:
            raise ToolError(
                "read_pdf", f"PDF trop volumineux ({len(content)} o > 20 Mo)"
            )
        if not content:
            raise ToolError("read_pdf", "PDF vide")
        return content


class ReadPdfTool(BaseTool[ReadPdfArgs]):
    name = "read_pdf"
    description = (
        "Extrait le texte brut d'un PDF distant (rapport annuel, document officiel). "
        "Entrée : url (http/https), max_pages (1-20, défaut 5). "
        "Sortie : texte tronqué à 20 000 caractères, avec source et horodatage."
    )
    args_schema = ReadPdfArgs

    def __init__(self, reader: PdfReader) -> None:
        self._reader = reader

    async def run(self, args: ReadPdfArgs) -> dict[str, Any]:
        url = args.url.strip()
        if not url:
            raise ToolError(self.name, "url vide")
        try:
            text = await self._reader.extract_text(url, args.max_pages)
        except ToolError:
            raise
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {
            "url": url,
            "max_pages": args.max_pages,
            "text": text,
            "chars": len(text),
            "source": "nutrient",
            "timestamp": datetime.now(UTC).isoformat(),
        }
