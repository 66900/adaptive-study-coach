# Third-party notices

Pinned versions are listed in `requirements.txt`. Direct runtime components include:

| Component | License | Purpose |
|---|---|---|
| [Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs) | MIT | Adaptive scheduling |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | Apache-2.0 | Local Chinese/English OCR and bundled ONNX models |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | OCR model inference |
| [OpenCV](https://github.com/opencv/opencv) | Apache-2.0 | Perspective, deskew, contrast, thresholding |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU | Image decoding and EXIF orientation |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause and additional bundled notices | Numerical arrays |
| [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | MIT | Excel import |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | Text PDF import |

RapidOCR contains optional URL-loading and model-download helpers. This project does not call
those paths during study sessions. It decodes a workspace-local file, passes a NumPy array, sets
three explicit model paths, and verifies fixed SHA-256 hashes before engine construction.

OCRmyPDF, PaddleOCR, Microsoft MarkItDown, tutor-skills, memory-retrieval-learning, and
Skill-Anything informed design research but are not copied, bundled, imported, or executed by
this repository.

Each dependency remains subject to its own license and bundled notices.
