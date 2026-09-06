"""Small real-PDF builders used only by rebaseline tests."""

from __future__ import annotations

from pathlib import Path

import fitz


def make_pdf(path: Path, pages: list[list[tuple[float, float, str]]], *, rotations: list[int] | None = None, cropboxes: list[tuple[float, float, float, float] | None] | None = None, images: set[int] | None = None, fontfile: Path | None = None) -> Path:
    document = fitz.open()
    image_pages = images or set()
    for index, entries in enumerate(pages):
        page = document.new_page(width=595, height=842)
        if fontfile:
            page.insert_font(fontname="rebaseline_unicode", fontfile=str(fontfile))
        if rotations:
            page.set_rotation(rotations[index])
        for x, y, text in entries:
            page.insert_text((x, y), text, fontsize=11, fontname="rebaseline_unicode" if fontfile else "helv")
        if cropboxes and cropboxes[index] is not None:
            page.set_cropbox(fitz.Rect(cropboxes[index]))
        if index in image_pages:
            pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 10, 10), False)
            page.insert_image(fitz.Rect(500, 10, 510, 20), pixmap=pixmap)
    document.save(path)
    document.close()
    return path
