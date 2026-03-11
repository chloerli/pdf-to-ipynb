"""
converter.py — Blocks → nbformat.NotebookNode

Mapping:
  HEADING1  → markdown cell  "# text"
  HEADING2  → markdown cell  "## text"
  HEADING3  → markdown cell  "### text"
  BODY      → markdown cell  raw text
  CODE      → code cell      raw text
  IMAGE     → markdown cell  base64 data URI  (or file path if save_images=True)

Strategy: accumulate consecutive markdown-class blocks into a single markdown
cell; flush to a new cell whenever a CODE block appears or an IMAGE appears
(images always get their own cell to avoid oversized single cells).
"""

from __future__ import annotations

import base64
import os

import nbformat

from .parser import Block, BlockType

_HEADING_PREFIX = {
    BlockType.HEADING1: "# ",
    BlockType.HEADING2: "## ",
    BlockType.HEADING3: "### ",
}


def build_notebook(
    blocks: list[Block],
    save_images: bool = False,
    images_dir: str = "images",
) -> nbformat.NotebookNode:
    """
    Convert classified+merged Blocks into a Jupyter notebook.

    Args:
        blocks: output of merge_blocks()
        save_images: if True, write PNG files to images_dir instead of embedding base64
        images_dir: directory to write PNG files into (only used when save_images=True)
    """
    nb = nbformat.v4.new_notebook()
    cells = []
    md_buffer: list[str] = []
    image_counter = 0

    if save_images and not os.path.exists(images_dir):
        os.makedirs(images_dir, exist_ok=True)

    def flush_md() -> None:
        if md_buffer:
            cells.append(nbformat.v4.new_markdown_cell("\n\n".join(md_buffer)))
            md_buffer.clear()

    for block in blocks:
        if block.block_type == BlockType.CODE:
            flush_md()
            cells.append(nbformat.v4.new_code_cell(block.text))

        elif block.block_type == BlockType.IMAGE:
            # Images always get their own markdown cell
            flush_md()
            if save_images:
                img_filename = f"image_{image_counter:03d}.png"
                img_path = os.path.join(images_dir, img_filename)
                with open(img_path, "wb") as f:
                    f.write(block.image_data)
                md = f"![image]({img_path})"
            else:
                img_b64 = base64.b64encode(block.image_data).decode("ascii")
                md = f"![image](data:image/png;base64,{img_b64})"
            cells.append(nbformat.v4.new_markdown_cell(md))
            image_counter += 1

        elif block.block_type in _HEADING_PREFIX:
            # Each heading gets its own markdown cell
            flush_md()
            prefix = _HEADING_PREFIX[block.block_type]
            cells.append(nbformat.v4.new_markdown_cell(prefix + block.text))

        else:
            # BODY text accumulates
            md_buffer.append(block.text)

    flush_md()
    nb.cells = cells
    return nb
