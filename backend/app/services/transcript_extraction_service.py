"""
TranscriptExtractionService — plain-text extraction from an uploaded
transcript file (.txt, .docx, .pdf).

Must NOT:
  - Perform OCR. A PDF with no extractable text layer (scanned images
    only) raises a clear 422 instead of silently returning empty text.
  - Perform database operations, authorization, or persistence.

pdfplumber and python-docx are imported lazily (mirroring
GeminiService's google-genai import) so the application still starts
if either dependency is ever missing from the environment.
"""
from __future__ import annotations

import io
import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}


class TranscriptExtractionService:

    @staticmethod
    def get_extension(filename: str | None) -> str:
        if not filename or "." not in filename:
            return ""
        return "." + filename.rsplit(".", 1)[-1].lower()

    @staticmethod
    def extract_text(filename: str | None, content: bytes) -> str:
        """
        Dispatch to the extractor matching the filename's extension.
        Caller is expected to have already validated the extension is
        in SUPPORTED_EXTENSIONS; this raises 415 defensively if not.
        """
        extension = TranscriptExtractionService.get_extension(filename)

        if extension == ".txt":
            return TranscriptExtractionService._extract_txt(content)
        if extension == ".docx":
            return TranscriptExtractionService._extract_docx(content)
        if extension == ".pdf":
            return TranscriptExtractionService._extract_pdf(content)

        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type: {extension or 'unknown'!r}. "
                "Supported types: .txt, .pdf, .docx."
            ),
        )

    @staticmethod
    def _extract_txt(content: bytes) -> str:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Could not read the text file: it is not valid "
                    "UTF-8."
                ),
            )

    @staticmethod
    def _extract_docx(content: bytes) -> str:
        try:
            import docx  # python-docx
        except ImportError:
            logger.error("python-docx package is not installed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Transcript processing is unavailable (missing "
                    "dependency)."
                ),
            )

        try:
            document = docx.Document(io.BytesIO(content))
            paragraphs = [p.text for p in document.paragraphs]
        except Exception:
            # Intentionally not logging the underlying exception body -
            # it may reproduce transcript content.
            logger.error("Failed to parse DOCX transcript.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Could not read the DOCX file. It may be corrupted "
                    "or invalid."
                ),
            )

        return "\n".join(paragraphs)

    @staticmethod
    def _extract_pdf(content: bytes) -> str:
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber package is not installed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Transcript processing is unavailable (missing "
                    "dependency)."
                ),
            )

        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_text = [
                    page.extract_text() or "" for page in pdf.pages
                ]
        except Exception:
            # Intentionally not logging the underlying exception body -
            # it may reproduce transcript content.
            logger.error("Failed to parse PDF transcript.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Could not read the PDF file. It may be corrupted "
                    "or invalid."
                ),
            )

        text = "\n".join(pages_text)

        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "This PDF appears to contain only scanned images "
                    "with no extractable text. Scanned PDFs are not "
                    "supported - please upload a text-based PDF, DOCX, "
                    "or TXT file."
                ),
            )

        return text
