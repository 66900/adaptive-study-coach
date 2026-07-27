# Image ingestion protocol

## Goal

Recover the most reliable visible study text from a screenshot, phone photo, or scan while
keeping all created files inside the repository workspace and minimizing image tokens. This
improves recognition but does not guarantee recovery of information absent from the source.

## Deterministic preparation

Run the manager command `image-prepare --file <path>`. The source must be a local BMP, JPEG,
PNG, TIFF, or WebP file inside the repository workspace.

The offline pipeline performs:

1. EXIF orientation and capture-source classification.
2. Document quadrilateral detection and perspective correction for photo-like inputs.
3. Small-angle deskew.
4. Illumination normalization, CLAHE contrast enhancement, and mild unsharp masking.
5. A secondary adaptive-binary OCR view when the primary OCR is weak.
6. Local RapidOCR inference using three bundled, SHA-256-pinned ONNX files.
7. Content-addressed caching and a token-routing manifest.

Do not use generative super-resolution for text, formulas, tables, or diagrams. It can invent
strokes, punctuation, digits, and symbols. Enhancement must remain deterministic.

## Token route

Read `manifest.json`, then obey `token_strategy.route`:

- `ocr-text-only`: read `ocr.txt`; do not open an image unless meaning remains ambiguous.
- `ocr-text-then-primary-image-if-needed`: read `ocr.txt`, then inspect `primary.png` only for
  unresolved lines.
- `ocr-text-then-only-relevant-retry-tiles`: read `ocr.txt`, then open only the smallest retry
  tile containing the unclear material.

Never load the original, primary, binary, and all tiles together. The primary image is capped at
a 2048-pixel long edge. Duplicate source bytes reuse the cached result.

`cache_hit` and `cache_lookup_elapsed_seconds` describe the current manager call and appear in
the returned JSON. The persistent content manifest deliberately omits that one-call state;
`processing_elapsed_seconds` records only the original image-processing run.

## Device adaptation

The manifest records the capture device metadata when EXIF provides it and detects the host OS,
architecture, logical CPU count, RAM, NVIDIA GPU, and laptop/general-computer type. Runtime
profiles prioritize smoothness:

- lightweight: 1 OCR worker, 1600-pixel OCR edge;
- balanced: 2 workers, 2048 pixels;
- performance-smooth: 2 workers, 2560 pixels.

GPU details inform the profile report, but this package intentionally uses ONNX Runtime CPU so
it does not need a large CUDA runtime. Do not exceed two OCR workers on the current laptop.

## Accuracy gate

OCR scores are not truth. Treat a line as unresolved when it contains an unclear character,
conflicting primary/binary reading, formula, table relationship, or missing answer. Compare only
the affected region with the primary image or retry tile. If uncertainty remains, create a
pending entry instead of importing it as learned material.

For English vocabulary, preserve spelling exactly and verify word/meaning alignment. For
mathematics and science, visually verify subscripts, superscripts, minus signs, decimal points,
units, arrows, and inequality symbols even when the overall OCR score is high.
