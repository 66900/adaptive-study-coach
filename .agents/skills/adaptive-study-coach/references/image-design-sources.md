# Image/OCR design sources and decisions

## Internal skills reviewed

- `screenshot-clarity-enhancer`: reused the conservative Lanczos/unsharp principle and its rule
  against generative reconstruction of factual text. It did not provide scan perspective
  correction or OCR, so it was not copied as a dependency.
- `markitdown-skill`: reviewed for document normalization. Its image route requires either a
  separate Tesseract installation or an LLM vision client, so it was not used for offline OCR.
- `cross-platform-domain-learner`: reused hardware profiling, progressive disclosure,
  content-addressed cache, and “context pack before full source” ideas.

## Primary repositories reviewed

- OpenCV: <https://github.com/opencv/opencv> — document geometry, deskew, contrast, thresholding,
  and deterministic image processing. Apache-2.0.
- RapidOCR: <https://github.com/RapidAI/RapidOCR> — local multilingual OCR via ONNX Runtime.
  Apache-2.0.
- OCRmyPDF: <https://github.com/ocrmypdf/OCRmyPDF> — useful rotate/deskew/clean workflow, but not
  installed because it requires external Ghostscript and Tesseract programs.
- PaddleOCR: <https://github.com/PaddlePaddle/PaddleOCR> — orientation and document-unwarping
  design reference; the full package was not installed because it is much heavier than needed.
- Microsoft MarkItDown: <https://github.com/microsoft/markitdown> — format normalization
  reference; its OCR plugin was not installed because it delegates image recognition to an LLM
  client rather than a bundled local OCR engine.

## Security decision

RapidOCR 3.9.1 includes optional URL-image loading and model-download helpers. Its pinned wheel
contains the selected Chinese/English detection, classification, and recognition models.
The adaptive study image pipeline never supplies a string URL: it decodes the local file itself
and passes a NumPy image. It explicitly supplies all model paths and verifies fixed SHA-256
hashes before constructing the engine. A missing or changed model causes a hard failure instead
of a download.

ONNX Runtime and OpenCV contain native binaries, so complete source-only inspection is not
possible from their wheels. They were pinned to exact versions from their official projects and
are confined to the repository-local virtual environment.
