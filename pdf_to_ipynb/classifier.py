"""
classifier.py — assign BlockType to each Block based on font/size/flags.

Rules (in priority order):
  1. IMAGE / PAGE_BREAK → unchanged
  2. code_font          → CODE
  3. bold + size > 13.5 → HEADING1
  4. bold + size > 11.0 → HEADING2
  5. bold               → HEADING3
  6. else               → BODY
"""

from __future__ import annotations

from typing import Optional

from .parser import Block, BlockType

_SIZE_H1 = 13.5
_SIZE_H2 = 11.0
_BOLD_FLAG = 16  # bit 4 in PyMuPDF span flags


def classify_blocks(
    blocks: list[Block],
    code_font: Optional[str],
) -> list[Block]:
    """Return a new list of Blocks with block_type correctly assigned."""
    result = []
    for block in blocks:
        result.append(_classify(block, code_font))
    return result


def _classify(block: Block, code_font: Optional[str]) -> Block:
    # IMAGE and PAGE_BREAK are already correct from the parser
    if block.block_type in (BlockType.IMAGE, BlockType.PAGE_BREAK):
        return block

    is_bold = bool(block.flags & _BOLD_FLAG)
    size = block.font_size

    if code_font and block.font_name == code_font:
        block.block_type = BlockType.CODE
    elif is_bold and size > _SIZE_H1:
        block.block_type = BlockType.HEADING1
    elif is_bold and size > _SIZE_H2:
        block.block_type = BlockType.HEADING2
    elif is_bold:
        block.block_type = BlockType.HEADING3
    else:
        block.block_type = BlockType.BODY

    return block
