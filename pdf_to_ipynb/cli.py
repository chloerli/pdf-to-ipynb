"""
cli.py — Command-line interface for pdf-to-ipynb.

Usage:
    pdf-to-ipynb input.pdf [-o output.ipynb] [--page-breaks] [--save-images] [--no-skip-cover] [--verbose]
    python main.py input.pdf ...
"""

from __future__ import annotations

import argparse
import os
import sys

import nbformat

from .parser import parse_pdf, BlockType
from .classifier import classify_blocks
from .merger import merge_blocks
from .converter import build_notebook


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pdf-to-ipynb",
        description="Convert a PDF file into a Jupyter notebook.",
    )
    parser.add_argument("input_pdf", help="Path to the source PDF file")
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output .ipynb path (default: same stem as input, in current directory)",
    )
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert --- horizontal rules between pages",
    )
    parser.add_argument(
        "--save-images",
        action="store_true",
        help="Save images as PNG files instead of embedding base64",
    )
    parser.add_argument(
        "--no-skip-cover",
        action="store_true",
        help="Include the cover page (page 1) in output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print block-by-block classification info to stderr",
    )

    args = parser.parse_args(argv)

    if not os.path.isfile(args.input_pdf):
        print(f"Error: file not found: {args.input_pdf}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        stem = os.path.splitext(os.path.basename(args.input_pdf))[0]
        output_path = os.path.join(os.path.dirname(os.path.abspath(args.input_pdf)), f"{stem}.ipynb")

    # Images directory (only relevant with --save-images)
    stem = os.path.splitext(output_path)[0]
    images_dir = f"{stem}_images"

    print(f"Parsing {args.input_pdf}...", file=sys.stderr)
    blocks, body_font, code_font = parse_pdf(
        args.input_pdf,
        skip_cover=not args.no_skip_cover,
    )
    print(f"  Fonts detected — body: {body_font!r}, code: {code_font!r}", file=sys.stderr)
    print(f"  Raw blocks: {len(blocks)}", file=sys.stderr)

    blocks = classify_blocks(blocks, code_font)

    if args.verbose:
        for b in blocks:
            if b.block_type == BlockType.IMAGE:
                print(f"  [PAGE {b.page_num}] IMAGE", file=sys.stderr)
            elif b.block_type != BlockType.PAGE_BREAK:
                preview = b.text[:60].replace("\n", "↵")
                print(f"  [PAGE {b.page_num}] {b.block_type.name:10s} {preview!r}", file=sys.stderr)

    blocks = merge_blocks(blocks, page_breaks=args.page_breaks)
    print(f"  Merged blocks: {len(blocks)}", file=sys.stderr)

    nb = build_notebook(
        blocks,
        save_images=args.save_images,
        images_dir=images_dir,
    )
    print(f"  Notebook cells: {len(nb.cells)}", file=sys.stderr)

    with open(output_path, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    print(f"Written: {output_path}", file=sys.stderr)
    if args.save_images:
        print(f"Images saved to: {images_dir}/", file=sys.stderr)
