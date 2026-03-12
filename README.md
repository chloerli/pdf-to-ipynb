# pdf-to-ipynb

Turn any PDF into a Jupyter notebook with one command.

Headings, body text, diagrams, and code snippets are all preserved — automatically structured into the right notebook cells. Code that's baked into screenshots is extracted via OCR.

---

## Before you start

**Python 3.10+** — check with `python3 --version`

**Tesseract** (reads text from images):
```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr

# Windows — download the installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
```

---

## Quick start

```bash
git clone https://github.com/chloerli/pdf-to-ipynb
cd pdf-to-ipynb
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

```bash
pdf-to-ipynb document.pdf
```

The output file (`document.ipynb`) is saved in the **same folder as the PDF**.

---

## Preview

PDF on the left, generated notebook on the right:

![demo](demo.png)

---

## Use cases

**Study from a textbook**
Convert a coding or system design book into a notebook so you can run examples, add your own notes, and annotate diagrams right next to the text.

**Build a personal reference**
Turn dense technical PDFs (API docs, whitepapers, research papers) into searchable, executable notebooks you can revisit and extend.

**Interview prep**
Convert system design or algorithms books into notebooks and add your own code experiments below each concept as you study.

**Share annotated reading notes**
Convert a PDF, add your commentary in new cells, and share the notebook with teammates or study groups.

---

## Options

To pick a different output location:
```bash
pdf-to-ipynb document.pdf -o ~/Desktop/notebook.ipynb
```

| Flag | What it does |
|---|---|
| `-o path/to/output.ipynb` | Save the notebook somewhere specific |
| `--page-breaks` | Add a `---` separator between each page |
| `--save-images` | Save figures as PNG files instead of embedding them |
| `--no-skip-cover` | Include the cover page (skipped by default if it's a full-page image) |
| `--verbose` | Print every block and its detected type while converting |

---

## How it works

The converter runs in four steps:

1. **Parse** — reads every page and pulls out text blocks and images. Detects which font is body text and which is code by counting character frequency.

2. **Classify** — labels each block: large bold text → heading, monospace font → code, everything else → body.

3. **Merge** — joins adjacent blocks of the same type. If an image sits directly below a code line (common when PDFs bake code into screenshots), it OCRs the image and attaches the text to the code block.

4. **Convert** — turns the labeled blocks into notebook cells and writes the `.ipynb` file.

---

## Project structure

```
pdf-to-ipynb/
├── main.py                  # entry point
├── pyproject.toml
└── pdf_to_ipynb/
    ├── parser.py            # step 1 — PDF → blocks
    ├── classifier.py        # step 2 — label each block
    ├── merger.py            # step 3 — merge + OCR
    ├── converter.py         # step 4 — blocks → .ipynb
    └── cli.py               # command-line wiring
```
