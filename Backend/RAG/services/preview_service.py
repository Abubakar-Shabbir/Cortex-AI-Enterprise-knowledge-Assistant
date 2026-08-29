"""
Document Preview - extracted-text preview for PDF/DOCX/TXT, reusing
the exact same text_extractor.extract_text() the upload pipeline
already uses. No new dependency, no native-format rendering - a
truncated plain-text excerpt is enough to let someone confirm "is this
the right document" without opening it elsewhere.
"""

import logging

from .text_extractor import extract_text

logger = logging.getLogger(__name__)

MAX_PREVIEW_CHARS = 10000


def get_document_preview_text(document, max_chars=MAX_PREVIEW_CHARS):
    """
    Returns {"text": ..., "truncated": bool} or {"error": "..."} -
    never raises, matching the never-raise contract every other
    best-effort service in this project follows.
    """

    if not document.file:
        return {"error": "This document has no file to preview."}

    try:
        text = extract_text(document.file.path)
    except Exception:
        logger.exception("Preview extraction failed for document %s", document.id)
        return {"error": "Couldn't generate a preview for this document."}

    text = text.strip()

    if not text:
        return {"error": "This document has no extractable text."}

    truncated = len(text) > max_chars

    return {"text": text[:max_chars], "truncated": truncated}
