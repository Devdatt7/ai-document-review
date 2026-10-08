"""Load source documents (plain text or text-based PDF) into the Source model.

Everything is read locally. Nothing is sent to any API.
"""

import pymupdf

from models import Source, SourcePage


def load_text_source(source_id: str, text: str) -> Source:
    """A plain text source is one 'page' with no page number."""
    return Source(source_id=source_id, pages=[SourcePage(page=None, text=text)])


def load_pdf_source(source_id: str, pdf_bytes: bytes) -> Source:
    """Read a text-based PDF. Each PDF page keeps its (1-based) page number."""
    try:
        pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        raise ValueError("Could not open this file as a PDF.") from None

    pages = []
    with pdf:
        for page in pdf:
            # "blocks" gives paragraph-like pieces of text; sort=True = reading order.
            blocks = page.get_text("blocks", sort=True)
            # block[6] == 0 means a text block (1 would be an image).
            paragraphs = [b[4].strip() for b in blocks if b[6] == 0 and b[4].strip()]
            if paragraphs:
                pages.append(SourcePage(page=page.number + 1, text="\n\n".join(paragraphs)))

    if not pages:
        raise ValueError("No text found in this PDF. Scanned PDFs need OCR, which is not supported.")
    return Source(source_id=source_id, pages=pages)
