# -*- coding: utf-8 -*-
"""OCR для сканированных PDF (фрахтовые AWB и т.п.).

Движок — rapidocr-onnxruntime (CPU, без системных зависимостей).
Рендер страниц — pypdfium2. Движок создаётся лениво и кэшируется.
"""
from __future__ import annotations
import warnings

warnings.filterwarnings("ignore")

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import pypdfium2             # noqa: F401
        return True
    except Exception:
        return False


def ocr_pdf(path: str, dpi: int = 220, max_pages: int = 4) -> str:
    """Возвращает распознанный текст всех страниц (или '' при неудаче)."""
    import numpy as np
    import pypdfium2 as pdfium
    eng = _get_engine()
    out = []
    pdf = pdfium.PdfDocument(path)
    try:
        n = min(len(pdf), max_pages)
        for i in range(n):
            page = pdf[i]
            arr = np.array(page.render(scale=dpi / 72).to_pil())
            res, _ = eng(arr)
            if res:
                out.extend(t for _, t, _ in res)
    finally:
        pdf.close()
    return "\n".join(out)
