---
name: photo-to-scan
description: Turn phone photos of paper documents (contracts, forms, receipts, stamped sheets) into flat, upright, deskewed scans — JPG/PNG pages or a single PDF, scanner-app style. Use when the user hands over a photo of a page and wants it "扫描件/扫描效果", automatically rotated upright, cropped, shadow-free and printed-looking, or wants a phone photo made readable for OCR/archiving.
---

# Photo to Scan

## Core Goal
- One phone photo of a sheet in, one flat scan-looking page out (JPG/PNG/PDF).
- Fixes, in this order: perspective → 90/180/270 → skew → cast shadow/border → crop → scan look.
- Keeps seals, red stamps and coloured pen: the ink layer is binarised, the colour layer is only whitened.

## Required Tools
- `scripts/photo_to_scan.py`.
- Hard dependencies: `numpy`, `scipy`, `Pillow`. Without them nothing runs.
- Recommended extras (the script degrades gracefully without them):
  - `opencv-python-headless` — four-corner perspective warp, convex page silhouette.
  - `rapidocr-onnxruntime` — decides 90° vs 270° from real OCR; without it that
    decision falls back to a weaker geometric heuristic and may need `--orient`.
  - `PyMuPDF` — writes multi-page PDFs at an exact page size.
- Install once:
  ```bash
  python -m pip install numpy scipy pillow opencv-python-headless rapidocr-onnxruntime pymupdf
  ```

## Quick Start
1. One photo:
   ```bash
   python scripts/photo_to_scan.py -i photo.jpg -o out/
   ```
2. A folder of photos plus one PDF, all modes:
   ```bash
   python scripts/photo_to_scan.py -i shots/ -o out/ --pdf out/book.pdf
   ```
3. Hard black-and-white copy (no colour at all):
   ```bash
   python scripts/photo_to_scan.py -i photo.jpg -o out/ --mode bw
   ```
4. Orientation came back with `confidence: low`:
   ```bash
   python scripts/photo_to_scan.py -i photo.jpg -o out/ --orient 270
   ```
5. See the four candidate rotations before committing:
   ```bash
   python scripts/photo_to_scan.py -i photo.jpg -o out/ --preview
   ```
   `<name>.preview.png` is a 2×2 sheet; the top-right tile is what `auto` picked.

## How orientation is decided (so you can trust or overrule it)
- Axis (0/180 vs 90/270): aspect ratio of OCR text-line boxes — about 5 means the
  text already runs left-to-right, about 0.2 means the page is lying on its side.
  OCR confidence is useless here (it rectifies every line), the box shape is not.
- Which way up: OCR quality with the 180° line classifier switched off — an
  upside-down recogniser collapses — else the median ink centroid inside each
  text line (upright glyphs sit slightly high).
- No OCR available: ink-profile peakiness picks the axis, the centroid decides the
  flip, and confidence drops. Verify with `--preview` and pass `--orient`.

## Behavior
- `--mode color` (default) keeps the red seal; `gray` flattens colour; `bw` hard
  binarises (smallest files, best for OCR of clean sheets).
- `--deskew auto` searches ±`--max-skew` degrees; `--deskew 0` leaves the page as is.
- `--orient auto` may be overridden with `0|90|180|270`.
- Blank/rotated/oversized photos: the long side is capped at `--max-side` (2600).
- Output is `<stem>.scan.jpg`, 300 DPI by default, with a 1.5 % white margin.
- `--json report.json` writes per-page orientation, skew, crop and output paths.

## Verify before handing over
1. Read the JSON line: `confidence` must be `high`/`medium`, `skew_deg` under ~5.
2. Look at the produced page. Checks that actually fail: signatures turned white
   (paper mask too aggressive), faint pencil lost (raise `--ink-k` to 0.30),
   table rules pale (that means the Sauvola layer did not engage; check `--paper`).
3. Anything wrong → re-run with `--orient` / `--ink-k` / `--mode`, never hand over
   an unchecked page.

## Limits
- Curved/bent pages (book gutters, wrinkled receipts) are only deskewed, not
  dewarped: this tool has no learned unwarping model. For that use
  `UVDoc`, `DocTr++` or `page-dewarp` (see `references/upstream-projects.md`).
- Handwriting is kept as ink, not recognised; this is not OCR.
- A sheet corner cut off by the camera becomes a small dark sliver; `--no-mask`
  keeps it honest instead of guessing.

## Script
- `scripts/photo_to_scan.py` — CLI, no third-party service, runs offline.
