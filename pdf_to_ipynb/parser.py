"""
parser.py — PDF → list[Block]

Extracts raw blocks from a PDF using PyMuPDF. Does not classify block types;
that is handled by classifier.py.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import fitz  # PyMuPDF


class BlockType(Enum):
    HEADING1 = auto()
    HEADING2 = auto()
    HEADING3 = auto()
    BODY = auto()
    CODE = auto()
    IMAGE = auto()
    PAGE_BREAK = auto()


@dataclass
class Block:
    page_num: int
    block_type: BlockType
    text: str = ""
    image_data: bytes = b""  # PNG bytes for IMAGE blocks
    bbox: tuple = field(default_factory=tuple)
    font_size: float = 0.0
    flags: int = 0
    font_name: str = ""
    y0: float = 0.0
    y1: float = 0.0


def detect_fonts(doc: fitz.Document, scan_pages: int = 999) -> tuple[str, Optional[str]]:
    """
    Scan the first `scan_pages` text-heavy pages to identify body_font and code_font.
    The majority font (by span count) is the body font; any minority font is code.
    Returns (body_font, code_font). code_font may be None if only one font is found.
    """
    font_counter: Counter = Counter()
    pages_to_scan = min(scan_pages, len(doc))

    for page_num in range(pages_to_scan):
        page = doc[page_num]
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font = span.get("font", "")
                    text = span.get("text", "").strip()
                    if font and text:
                        font_counter[font] += len(text)

    if not font_counter:
        return ("", None)

    # Body font has the most characters; code font is anything else
    sorted_fonts = font_counter.most_common()
    body_font = sorted_fonts[0][0]
    code_font = sorted_fonts[1][0] if len(sorted_fonts) > 1 else None
    return (body_font, code_font)


def _is_cover_page(page: fitz.Page) -> bool:
    """True if the page has no text blocks and exactly one image block."""
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b["type"] == 0 and
                   any(span["text"].strip() for line in b["lines"] for span in line["spans"])]
    image_blocks = [b for b in blocks if b["type"] == 1]
    return len(text_blocks) == 0 and len(image_blocks) == 1


def _extract_image_png(page: fitz.Page, bbox: tuple) -> bytes:
    """Rasterise the image region to PNG bytes at 1.5× scale (~108 DPI)."""
    rect = fitz.Rect(bbox)
    mat = fitz.Matrix(1.5, 1.5)
    pixmap = page.get_pixmap(clip=rect, matrix=mat)
    return pixmap.tobytes("png")


def _line_style(line: dict) -> tuple[str, float, int]:
    """Return (font_name, font_size, flags) for the dominant span in a line."""
    best_font, best_size, best_flags, max_chars = "", 0.0, 0, 0
    for span in line["spans"]:
        n = len(span.get("text", "").strip())
        if n > max_chars:
            max_chars = n
            best_font = span.get("font", "")
            best_size = span.get("size", 0.0)
            best_flags = span.get("flags", 0)
    return best_font, best_size, best_flags


def _styles_differ(s1: tuple, s2: tuple) -> bool:
    """True if two line styles are meaningfully different (bold change or large size jump)."""
    font1, size1, flags1 = s1
    font2, size2, flags2 = s2
    bold1, bold2 = bool(flags1 & 16), bool(flags2 & 16)
    if bold1 != bold2:
        return True
    if font1 != font2:
        return True
    if abs(size1 - size2) > 1.0:
        return True
    return False


def _parse_text_block(raw_block: dict, page_num: int) -> list[Block]:
    """
    Convert a PyMuPDF text block dict into one or more Blocks.

    A single PDF block can contain a bold heading line followed by body text.
    We split at style boundaries so each homogeneous segment becomes its own Block.
    """
    lines = raw_block["lines"]
    if not lines:
        return []

    segments: list[tuple[list[str], str, float, int, float, float]] = []
    # Each segment: (line_texts, font, size, flags, y0, y1)

    current_lines: list[str] = []
    current_style = _line_style(lines[0])
    seg_y0 = lines[0]["bbox"][1]
    seg_y1 = lines[0]["bbox"][3]

    for line in lines:
        style = _line_style(line)
        line_text = "".join(span.get("text", "") for span in line["spans"])
        if current_lines and _styles_differ(current_style, style):
            segments.append((current_lines, *current_style, seg_y0, seg_y1))
            current_lines = []
            current_style = style
            seg_y0 = line["bbox"][1]
        current_lines.append(line_text)
        seg_y1 = line["bbox"][3]

    if current_lines:
        segments.append((current_lines, *current_style, seg_y0, seg_y1))

    full_bbox = tuple(raw_block["bbox"])
    result = []
    for line_texts, font, size, flags, y0, y1 in segments:
        text = "\n".join(line_texts).strip()
        if not text:
            continue
        result.append(Block(
            page_num=page_num,
            block_type=BlockType.BODY,  # reclassified by classifier.py
            text=text,
            bbox=full_bbox,
            font_size=size,
            flags=flags,
            font_name=font,
            y0=y0,
            y1=y1,
        ))
    return result


def parse_pdf(
    pdf_path: str,
    skip_cover: bool = True,
) -> tuple[list[Block], str, Optional[str]]:
    """
    Parse a PDF and return (blocks, body_font, code_font).

    blocks: ordered list of Block objects (unclassified, except IMAGE/PAGE_BREAK)
    body_font: font name for body/heading text
    code_font: font name for code snippets (may be None)
    """
    doc = fitz.open(pdf_path)
    body_font, code_font = detect_fonts(doc)

    blocks: list[Block] = []
    first_content_page = True

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Skip cover page if it's a full-page image
        if skip_cover and page_num == 0 and _is_cover_page(page):
            continue

        if not first_content_page:
            blocks.append(Block(page_num=page_num, block_type=BlockType.PAGE_BREAK))
        first_content_page = False

        raw_blocks = page.get_text("dict")["blocks"]
        # Sort by vertical position
        raw_blocks.sort(key=lambda b: b["bbox"][1])

        for rb in raw_blocks:
            if rb["type"] == 0:
                for b in _parse_text_block(rb, page_num):
                    blocks.append(b)
            elif rb["type"] == 1:
                # Image block
                bbox = tuple(rb["bbox"])
                image_data = _extract_image_png(page, bbox)
                blocks.append(Block(
                    page_num=page_num,
                    block_type=BlockType.IMAGE,
                    image_data=image_data,
                    bbox=bbox,
                    y0=bbox[1],
                    y1=bbox[3],
                ))

    return blocks, body_font, code_font
