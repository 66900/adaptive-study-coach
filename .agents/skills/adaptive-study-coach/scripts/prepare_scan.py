#!/usr/bin/env python3
"""Offline, device-adaptive scan cleanup and OCR for study material."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess  # nosec B404
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from path_guard import PathBoundaryError, resolve_inside

# Subprocess calls use a fixed executable, shell=False, and no user-controlled arguments.
DEPENDENCY_IMPORT_ERROR: Exception | None = None
try:
    import cv2
    import numpy as np
    from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError
    from rapidocr import RapidOCR
except Exception as exc:  # pragma: no cover - exercised by subprocess failure tests.
    DEPENDENCY_IMPORT_ERROR = exc


PIPELINE_VERSION = "1.1.0"
DEFAULT_HOME_NAME = "adaptive-study-data"
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
ALLOWED_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MODEL_HASHES = {
    # Public model checksums, not credentials.
    "PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",  # noqa: E501  # pragma: allowlist secret
    "PP-OCRv6_rec_small.onnx": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",  # noqa: E501  # pragma: allowlist secret
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",  # noqa: E501  # pragma: allowlist secret
}


class ScanError(RuntimeError):
    """A user-actionable image preparation error."""


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def atomic_write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix, image)
    if not ok:
        raise ScanError(f"无法编码图像：{path.name}")
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_bytes(encoded.tobytes())
    os.replace(temp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workspace_root_from_script() -> Path:
    resolved = Path(__file__).resolve()
    for parent in resolved.parents:
        if parent.name == ".agents":
            return parent.parent.resolve()
    raise ScanError("扫描模块不在工作区的 .agents\\skills 目录中。")


def resolve_paths(raw_home: str | None, raw_input: str) -> tuple[Path, Path, Path]:
    workspace = workspace_root_from_script()
    try:
        home = resolve_inside(
            workspace,
            raw_home if raw_home else workspace / DEFAULT_HOME_NAME,
            must_exist=False,
            allow_root=False,
            label="学习系统目录",
        )
        source = resolve_inside(
            workspace,
            raw_input,
            must_exist=True,
            allow_root=False,
            label="本地图像文件",
        )
    except PathBoundaryError as exc:
        raise ScanError(str(exc)) from exc
    if not source.is_file():
        raise ScanError(f"只接受普通图像文件：{source}")
    if source.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ScanError(f"不支持的图像格式：{source.suffix}")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ScanError("图像超过 50 MB 安全上限。")
    return workspace, home, source


def total_memory_gb() -> float:
    if platform.system() == "Windows":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.total_phys / (1024**3), 2)
    try:
        system_os: Any = os
        sysconf = system_os.sysconf
        page_size = sysconf("SC_PAGE_SIZE")
        pages = sysconf("SC_PHYS_PAGES")
        return round(page_size * pages / (1024**3), 2)
    except (AttributeError, OSError, ValueError):
        return 0.0


def detect_gpu() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            shell=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            name, _, memory = completed.stdout.splitlines()[0].partition(",")
            return {
                "available": True,
                "name": name.strip(),
                "memory_mb": int(float(memory.strip())) if memory.strip() else None,
            }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return {"available": False, "name": None, "memory_mb": None}


def detect_host_profile() -> dict[str, Any]:
    logical_cpus = os.cpu_count() or 1
    memory_gb = total_memory_gb()
    gpu = detect_gpu()
    if logical_cpus >= 8 and memory_gb >= 12:
        profile, workers, ocr_long_edge = "performance-smooth", 2, 2560
    elif logical_cpus >= 4 and memory_gb >= 7:
        profile, workers, ocr_long_edge = "balanced", 2, 2048
    else:
        profile, workers, ocr_long_edge = "lightweight", 1, 1600
    gpu_name = (gpu.get("name") or "").lower()
    if "laptop" in gpu_name:
        device_type = "laptop"
    elif gpu["available"]:
        device_type = "gpu-computer"
    else:
        device_type = "general-computer"
    return {
        "os": platform.system(),
        "architecture": platform.machine(),
        "device_type": device_type,
        "logical_cpus": logical_cpus,
        "memory_gb": memory_gb,
        "gpu": gpu,
        "profile": profile,
        "ocr_workers": workers,
        "ocr_long_edge": ocr_long_edge,
        "priority": "smoothness",
    }


def load_image(source: Path) -> tuple[np.ndarray, dict[str, Any]]:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(source) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ScanError("图像像素数超过 8000 万安全上限。")
            exif = opened.getexif()
            tags = {
                ExifTags.TAGS.get(key, str(key)): str(value)[:200]
                for key, value in exif.items()
                if value is not None
            }
            image = ImageOps.exif_transpose(opened).convert("RGB")
            file_format = opened.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ScanError(f"无法读取图像：{source.name}") from exc
    rgb = np.asarray(image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    capture = classify_capture(source, bgr.shape[1], bgr.shape[0], tags)
    capture["format"] = file_format
    return bgr, capture


def classify_capture(source: Path, width: int, height: int, tags: dict[str, str]) -> dict[str, Any]:
    make = tags.get("Make")
    model = tags.get("Model")
    software = tags.get("Software")
    descriptor = " ".join(value for value in (make, model, software) if value).lower()
    if make or model:
        capture_type = "camera-photo"
    elif "scanner" in descriptor or "scan" in descriptor:
        capture_type = "scanner"
    elif source.suffix.lower() == ".png" and not tags:
        capture_type = "screenshot-or-export"
    else:
        capture_type = "image-file"
    return {
        "capture_type": capture_type,
        "make": make,
        "model": model,
        "software": software,
        "original_width": width,
        "original_height": height,
    }


def order_points(points: np.ndarray) -> np.ndarray:
    points = points.astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def perspective_warp(image: np.ndarray, capture_type: str) -> tuple[np.ndarray, bool]:
    if capture_type == "screenshot-or-export":
        return image, False
    height, width = image.shape[:2]
    scale = min(1.0, 1200.0 / max(height, width))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = small.shape[0] * small.shape[1]
    document = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) == 4 and cv2.contourArea(polygon) >= image_area * 0.28:
            document = polygon.reshape(4, 2) / scale
            break
    if document is None:
        return image, False
    points = order_points(document)
    top_left, top_right, bottom_right, bottom_left = points
    out_width = int(
        max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left))
    )
    out_height = int(
        max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left))
    )
    if out_width < 200 or out_height < 200:
        return image, False
    destination = np.array(
        [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(points, destination)
    return cv2.warpPerspective(image, matrix, (out_width, out_height)), True


def estimate_skew(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    minimum = max(60, int(gray.shape[1] * 0.18))
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80, minLineLength=minimum, maxLineGap=20
    )
    if lines is None:
        return 0.0
    angles = []
    for line in np.asarray(lines).reshape(-1, 4):
        x1, y1, x2, y2 = line
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) <= 15:
            angles.append(angle)
    return float(np.median(angles)) if angles else 0.0


def deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    angle = estimate_skew(gray)
    if abs(angle) < 0.25:
        return image, 0.0
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    cosine, sine = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width = int(height * sine + width * cosine)
    new_height = int(height * cosine + width * sine)
    matrix[0, 2] += new_width / 2 - width / 2
    matrix[1, 2] += new_height / 2 - height / 2
    rotated = cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, round(angle, 3)


def enhance_for_text(image: np.ndarray, capture_type: str) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if capture_type == "screenshot-or-export":
        normalized = gray
    else:
        kernel = max(31, (min(gray.shape[:2]) // 24) | 1)
        background = cv2.GaussianBlur(gray, (kernel, kernel), 0)
        normalized = cv2.divide(gray, background, scale=235)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    contrast = clahe.apply(normalized)
    blurred = cv2.GaussianBlur(contrast, (0, 0), 1.0)
    sharpened = cv2.addWeighted(contrast, 1.35, blurred, -0.35, 0)
    binary = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        15,
    )
    return sharpened, binary


def crop_content(gray: np.ndarray, binary: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    ink = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)[1]
    points = cv2.findNonZero(ink)
    if points is None:
        return gray, binary, False
    x, y, width, height = cv2.boundingRect(points)
    full_height, full_width = gray.shape[:2]
    if width * height > full_width * full_height * 0.97:
        return gray, binary, False
    margin = max(12, int(min(full_width, full_height) * 0.015))
    x0, y0 = max(0, x - margin), max(0, y - margin)
    x1, y1 = min(full_width, x + width + margin), min(full_height, y + height + margin)
    return gray[y0:y1, x0:x1], binary[y0:y1, x0:x1], True


def resize_long_edge(image: np.ndarray, maximum: int) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= maximum:
        return image
    scale = maximum / longest
    return cv2.resize(
        image,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def image_quality(gray: np.ndarray) -> dict[str, float]:
    return {
        "blur_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
        "contrast_std": round(float(gray.std()), 2),
        "mean_brightness": round(float(gray.mean()), 2),
    }


def verify_models() -> dict[str, Path]:
    import rapidocr

    model_root = Path(rapidocr.__file__).resolve().parent / "models"
    models: dict[str, Path] = {}
    for name, expected_hash in MODEL_HASHES.items():
        path = model_root / name
        if not path.is_file():
            raise ScanError(f"本地 OCR 模型缺失，已停止以避免联网下载：{name}")
        actual_hash = sha256_file(path)
        if actual_hash.lower() != expected_hash:
            raise ScanError(f"OCR 模型哈希不匹配，已停止：{name}")
        models[name] = path
    return models


def run_ocr(
    image: np.ndarray, models: dict[str, Path], workers: int, max_side_len: int
) -> dict[str, Any]:
    params = {
        "Global.log_level": "error",
        "Global.max_side_len": max_side_len,
        "Det.model_path": str(models["PP-OCRv6_det_small.onnx"]),
        "Cls.model_path": str(models["ch_ppocr_mobile_v2.0_cls_mobile.onnx"]),
        "Rec.model_path": str(models["PP-OCRv6_rec_small.onnx"]),
        "EngineConfig.onnxruntime.intra_op_num_threads": workers,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }
    engine = RapidOCR(params=params)
    result = engine(image)
    texts = list(result.txts) if result.txts is not None else []
    scores = [float(value) for value in result.scores] if result.scores is not None else []
    boxes = result.boxes.tolist() if result.boxes is not None else []
    lines = []
    for index, text in enumerate(texts):
        lines.append(
            {
                "text": text,
                "score": round(scores[index], 6),
                "box": boxes[index] if index < len(boxes) else None,
            }
        )
    mean_score = float(np.mean(scores)) if scores else 0.0
    return {
        "lines": lines,
        "text": "\n".join(texts),
        "line_count": len(lines),
        "mean_score": round(mean_score, 6),
        "elapsed_seconds": round(float(getattr(result, "elapse", 0.0)), 4),
    }


def candidate_value(result: dict[str, Any]) -> float:
    return result["mean_score"] * 0.72 + min(result["line_count"] / 10, 1.0) * 0.28


def confidence_policy(result: dict[str, Any], quality: dict[str, float]) -> tuple[str, list[str]]:
    flags = []
    if result["line_count"] == 0:
        flags.append("no_text_detected")
    if result["mean_score"] < 0.75:
        flags.append("low_ocr_confidence")
    if quality["blur_variance"] < 35:
        flags.append("blurred_source")
    if quality["contrast_std"] < 25:
        flags.append("low_contrast")
    if result["line_count"] and result["mean_score"] >= 0.90 and not flags:
        level = "high"
    elif result["line_count"] and result["mean_score"] >= 0.75:
        level = "medium"
    else:
        level = "low"
    return level, flags


def make_retry_tiles(image: np.ndarray, result: dict[str, Any], out_dir: Path) -> list[str]:
    height, width = image.shape[:2]
    candidates = sorted(result["lines"], key=lambda item: item["score"])
    boxes = [item["box"] for item in candidates if item["score"] < 0.82 and item["box"]]
    crops: list[tuple[int, int, int, int]] = []
    for box in boxes[:4]:
        coordinates = np.asarray(box, dtype=np.float32)
        x0, y0 = coordinates.min(axis=0)
        x1, y1 = coordinates.max(axis=0)
        margin_x = max(80, int((x1 - x0) * 0.8))
        margin_y = max(60, int((y1 - y0) * 1.8))
        crops.append(
            (
                max(0, int(x0) - margin_x),
                max(0, int(y0) - margin_y),
                min(width, int(x1) + margin_x),
                min(height, int(y1) + margin_y),
            )
        )
    if not crops:
        overlap = 0.08
        mid_x, mid_y = width // 2, height // 2
        pad_x, pad_y = int(width * overlap), int(height * overlap)
        crops = [
            (0, 0, min(width, mid_x + pad_x), min(height, mid_y + pad_y)),
            (max(0, mid_x - pad_x), 0, width, min(height, mid_y + pad_y)),
            (0, max(0, mid_y - pad_y), min(width, mid_x + pad_x), height),
            (max(0, mid_x - pad_x), max(0, mid_y - pad_y), width, height),
        ]
    paths = []
    for index, (x0, y0, x1, y1) in enumerate(crops[:4], start=1):
        tile = image[y0:y1, x0:x1]
        if tile.size == 0:
            continue
        path = out_dir / f"retry-tile-{index}.png"
        atomic_write_image(path, tile)
        paths.append(str(path))
    return paths


def prepare_scan(raw_home: str | None, raw_input: str, force: bool = False) -> dict[str, Any]:
    if DEPENDENCY_IMPORT_ERROR is not None:
        raise ScanError(
            "图像处理依赖不可用；请执行仓库内 setup 脚本后重试。"
            f"（{type(DEPENDENCY_IMPORT_ERROR).__name__}）"
        )
    started = time.perf_counter()
    workspace, home, source = resolve_paths(raw_home, raw_input)
    (home / "imports" / "processed").mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)
    model_fingerprint = "".join(MODEL_HASHES.values())
    cache_key = hashlib.sha256(
        f"{source_hash}:{PIPELINE_VERSION}:{model_fingerprint}".encode("ascii")
    ).hexdigest()
    out_dir = home / "imports" / "processed" / cache_key[:2] / cache_key
    manifest_path = out_dir / "manifest.json"
    # Verify pinned models even on cache hits. A changed model is always fatal.
    models = verify_models()
    if manifest_path.is_file() and not force:
        cached = json.loads(manifest_path.read_text(encoding="utf-8"))
        if cached.get("source_sha256") != source_hash:
            raise ScanError("OCR 缓存来源哈希不匹配，已停止。")
        for cached_path in (
            cached.get("output_dir"),
            cached.get("ocr", {}).get("text_path"),
            cached.get("ocr", {}).get("json_path"),
            cached.get("token_strategy", {}).get("primary_image"),
            *cached.get("token_strategy", {}).get("retry_tiles", []),
        ):
            if not cached_path:
                continue
            try:
                resolve_inside(
                    home,
                    cached_path,
                    must_exist=True,
                    allow_root=False,
                    label="OCR 缓存文件",
                )
            except PathBoundaryError as exc:
                raise ScanError(str(exc)) from exc
        cached["cache_hit"] = True
        cached["cache_lookup_elapsed_seconds"] = round(time.perf_counter() - started, 4)
        cached["source"] = str(source)
        return cached

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir = resolve_inside(
            home,
            out_dir,
            must_exist=True,
            allow_root=False,
            label="OCR 输出目录",
        )
    except PathBoundaryError as exc:
        raise ScanError(str(exc)) from exc
    host = detect_host_profile()
    original, capture = load_image(source)
    quality_before = image_quality(cv2.cvtColor(original, cv2.COLOR_BGR2GRAY))
    corrected, perspective_corrected = perspective_warp(original, capture["capture_type"])
    corrected, deskew_angle = deskew(corrected)
    enhanced, binary = enhance_for_text(corrected, capture["capture_type"])
    enhanced, binary, content_cropped = crop_content(enhanced, binary)
    enhanced = resize_long_edge(enhanced, host["ocr_long_edge"])
    binary = resize_long_edge(binary, host["ocr_long_edge"])
    primary = resize_long_edge(enhanced, 2048)
    quality_after = image_quality(enhanced)

    grayscale_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    primary_result = run_ocr(grayscale_bgr, models, host["ocr_workers"], host["ocr_long_edge"])
    chosen_name = "enhanced-grayscale"
    chosen_result = primary_result
    secondary_result = None
    if primary_result["mean_score"] < 0.88 or primary_result["line_count"] == 0:
        binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        secondary_result = run_ocr(binary_bgr, models, host["ocr_workers"], host["ocr_long_edge"])
        if candidate_value(secondary_result) > candidate_value(primary_result):
            chosen_name = "adaptive-binary"
            chosen_result = secondary_result

    confidence_level, flags = confidence_policy(chosen_result, quality_before)
    primary_path = out_dir / "primary.png"
    binary_path = out_dir / "binary.png"
    atomic_write_image(primary_path, primary)
    atomic_write_image(binary_path, resize_long_edge(binary, 2048))
    ocr_path = out_dir / "ocr.json"
    ocr_text_path = out_dir / "ocr.txt"
    atomic_write_text(
        ocr_path,
        json.dumps(
            {
                "chosen_view": chosen_name,
                "confidence_level": confidence_level,
                "flags": flags,
                "result": chosen_result,
                "alternate_result": secondary_result,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    atomic_write_text(ocr_text_path, chosen_result["text"])

    retry_tiles = []
    if confidence_level != "high":
        retry_tiles = make_retry_tiles(primary, chosen_result, out_dir)
    # These are routing labels, not passwords.
    if confidence_level == "high":
        token_route = "ocr-text-only"  # nosec B105
    elif confidence_level == "medium":
        token_route = "ocr-text-then-primary-image-if-needed"  # nosec B105
    else:
        token_route = "ocr-text-then-only-relevant-retry-tiles"  # nosec B105

    original_pixels = int(capture["original_width"] * capture["original_height"])
    primary_pixels = int(primary.shape[0] * primary.shape[1])
    manifest = {
        "ok": True,
        "pipeline_version": PIPELINE_VERSION,
        "cache_hit": False,
        "source": str(source),
        "source_sha256": source_hash,
        "workspace": str(workspace),
        "output_dir": str(out_dir),
        "capture": capture,
        "host_profile": host,
        "processing": {
            "perspective_corrected": perspective_corrected,
            "deskew_angle_degrees": deskew_angle,
            "content_cropped": content_cropped,
            "quality_before": quality_before,
            "quality_after": quality_after,
        },
        "ocr": {
            "engine": "RapidOCR 3.9.1 / ONNX Runtime CPU",
            "network_used": False,
            "models_hash_verified": True,
            "confidence_level": confidence_level,
            "mean_score": chosen_result["mean_score"],
            "line_count": chosen_result["line_count"],
            "flags": flags,
            "text_path": str(ocr_text_path),
            "json_path": str(ocr_path),
        },
        "token_strategy": {
            "route": token_route,
            "primary_image": str(primary_path),
            "retry_tiles": retry_tiles,
            "original_pixels": original_pixels,
            "primary_pixels": primary_pixels,
            "pixel_reduction_percent": round(
                max(0.0, 1 - primary_pixels / max(1, original_pixels)) * 100, 2
            ),
            "rule": "先读 OCR 文本；仅在低置信或歧义处查看最小必要图块。",
        },
        "processing_elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    persistent_manifest = dict(manifest)
    persistent_manifest.pop("cache_hit")
    atomic_write_text(manifest_path, json.dumps(persistent_manifest, ensure_ascii=False, indent=2))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线扫描增强、OCR 与低 Token 图像路由")
    parser.add_argument("--home", help="学习系统目录")
    parser.add_argument("--input", required=True, help="仓库工作区中的图像")
    parser.add_argument("--force", action="store_true", help="忽略已有缓存并重新处理")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prepare_scan(args.home, args.input, args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ScanError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "图像处理发生未预期错误，已停止且未继续 OCR。",
                    "error_type": type(exc).__name__,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
