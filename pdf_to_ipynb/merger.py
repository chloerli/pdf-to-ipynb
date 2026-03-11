"""
merger.py — merge adjacent same-type Blocks into single Blocks.

Rules:
  - IMAGE blocks are never merged (each stays its own cell).
  - HEADING* blocks are never merged (each heading is its own section).
  - PAGE_BREAK: if page_breaks=True, insert a "---" BODY block; otherwise drop.
  - BODY blocks merge with "\n\n" separator if y-gap is large, else "\n".
  - CODE blocks merge with "\n" separator.
  - IMAGE immediately after CODE (small y-gap, same page) → OCR the image and
    fold the text into the code block (requires tesseract / pytesseract).
"""

from __future__ import annotations

import copy
import io
from dataclasses import replace

from .parser import Block, BlockType

try:
    import pytesseract
    from PIL import Image as PilImage
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

_NO_MERGE_TYPES = {BlockType.IMAGE}
_HEADING_TYPES = {BlockType.HEADING1, BlockType.HEADING2, BlockType.HEADING3}
_GAP_MULTIPLIER = 1.5  # if gap > this × line_height → paragraph break


def _y_gap_is_large(b1: Block, b2: Block) -> bool:
    line_height = b1.y1 - b1.y0
    if line_height <= 0:
        return False
    gap = b2.y0 - b1.y1
    return gap > line_height * _GAP_MULTIPLIER


def _separator(b1: Block, b2: Block) -> str:
    if b1.block_type == BlockType.CODE:
        return "\n"
    return "\n\n" if _y_gap_is_large(b1, b2) else "\n"


_OCR_GAP_MULTIPLIER = 3.0  # looser threshold for code+image stitching


def _preprocess_for_ocr(img: "PilImage.Image") -> "PilImage.Image":
    """Upscale and sharpen an image for better OCR accuracy on code text."""
    w, h = img.size
    img = img.resize((w * 3, h * 3), PilImage.LANCZOS)
    img = img.convert("L")  # grayscale — keeps anti-aliasing for LSTM engine
    return img


def _ocr_with_indent(img: "PilImage.Image") -> str:
    """
    OCR the image and reconstruct per-line indentation from word x-positions.

    Tesseract strips leading whitespace, so we recover it by:
      1. Getting bounding boxes for every word.
      2. Finding the leftmost x across all words (= column 0).
      3. Estimating char width from the median word width / word length.
      4. Prepending int((word_x - left_x) / char_w) spaces to each line.
    """
    import re
    data = pytesseract.image_to_data(
        img,
        config="--psm 6 --oem 1",
        output_type=pytesseract.Output.DICT,
    )

    # Group words into lines keyed by (block_num, par_num, line_num)
    lines: dict[tuple, list[dict]] = {}
    char_widths: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word or int(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        entry = {
            "word": word,
            "x": data["left"][i],
            "y": data["top"][i],
            "w": data["width"][i],
        }
        lines.setdefault(key, []).append(entry)
        if len(word) > 1:
            char_widths.append(data["width"][i] / len(word))

    if not lines:
        return ""

    # Estimate a single character width (median of sampled words)
    char_widths.sort()
    char_w = char_widths[len(char_widths) // 2] if char_widths else 8.0
    char_w = max(char_w, 1.0)

    # Left-most x across all words = indentation baseline
    left_x = min(w["x"] for words in lines.values() for w in words)

    # Reconstruct lines sorted by y position
    result_lines = []
    for key in sorted(lines, key=lambda k: lines[k][0]["y"]):
        words = sorted(lines[key], key=lambda w: w["x"])
        first_x = words[0]["x"]
        indent = max(0, round((first_x - left_x) / char_w))
        line_text = " ".join(w["word"] for w in words)
        result_lines.append(" " * indent + line_text)

    text = "\n".join(result_lines)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _ocr_image_block(block: Block) -> str | None:
    """OCR an IMAGE block and return the extracted text, or None on failure."""
    if not _OCR_AVAILABLE or not block.image_data:
        return None
    try:
        img = PilImage.open(io.BytesIO(block.image_data))
        img = _preprocess_for_ocr(img)
        return _ocr_with_indent(img) or None
    except Exception:
        return None


def _is_adjacent_code_image(code_block: Block, img_block: Block) -> bool:
    """True if img_block is an image on the same page immediately below code_block."""
    if img_block.block_type != BlockType.IMAGE:
        return False
    if img_block.page_num != code_block.page_num:
        return False
    line_height = code_block.y1 - code_block.y0
    if line_height <= 0:
        return True  # can't tell, assume adjacent
    gap = img_block.y0 - code_block.y1
    return gap <= line_height * _OCR_GAP_MULTIPLIER


def merge_blocks(blocks: list[Block], page_breaks: bool = False) -> list[Block]:
    """Merge adjacent same-type blocks. Returns a new list."""
    result: list[Block] = []
    current: Block | None = None

    for block in blocks:
        if block.block_type == BlockType.PAGE_BREAK:
            if current is not None:
                result.append(current)
                current = None
            if page_breaks:
                result.append(Block(
                    page_num=block.page_num,
                    block_type=BlockType.BODY,
                    text="---",
                ))
            continue

        if current is None:
            current = copy.copy(block)
            continue

        # IMAGE directly below a CODE block → try OCR and stitch into code
        if (
            current.block_type == BlockType.CODE
            and _is_adjacent_code_image(current, block)
        ):
            ocr_text = _ocr_image_block(block)
            if ocr_text:
                current.text = current.text + "\n" + ocr_text
                current.y1 = block.y1
                continue
            # OCR unavailable or empty — fall through to normal handling

        same_heading = (
            block.block_type == current.block_type
            and block.block_type in _HEADING_TYPES
            and not _y_gap_is_large(current, block)
        )
        can_merge = (
            block.block_type == current.block_type
            and block.block_type not in _NO_MERGE_TYPES
            and block.block_type not in _HEADING_TYPES
        ) or same_heading

        if can_merge:
            sep = " " if same_heading else _separator(current, block)
            current.text = current.text + sep + block.text
            current.y1 = block.y1
        else:
            result.append(current)
            current = copy.copy(block)

    if current is not None:
        result.append(current)

    return result
