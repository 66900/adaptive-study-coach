"""End-to-end tests for offline image cleanup, OCR, caching, and routing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import prepare_scan as scan


class PrepareScanTests(unittest.TestCase):
    def setUp(self) -> None:
        workspace = scan.workspace_root_from_script()
        temp_parent = workspace / scan.DEFAULT_HOME_NAME / "cache" / "temp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temp_parent)
        self.root = Path(self.temporary.name)
        self.home = self.root / "study-home"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_perspective_fixture(self) -> Path:
        page = np.full((1100, 760, 3), 255, np.uint8)
        cv2.putText(
            page,
            "ENGLISH VOCABULARY",
            (55, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.25,
            (20, 20, 20),
            3,
            cv2.LINE_AA,
        )
        lines = [
            "lucid - clear and easy to understand",
            "abate - become less intense",
            "derive - obtain from a source",
            "mitosis - cell division",
        ]
        for index, line in enumerate(lines):
            cv2.putText(
                page,
                line,
                (55, 230 + index * 145),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (25, 25, 25),
                2,
                cv2.LINE_AA,
            )
        cv2.rectangle(page, (20, 20), (740, 1080), (40, 40, 40), 3)
        canvas = np.full((1350, 1100, 3), 70, np.uint8)
        source = np.asarray([[0, 0], [759, 0], [759, 1099], [0, 1099]], dtype=np.float32)
        target = np.asarray([[165, 90], [900, 145], [850, 1240], [90, 1160]], dtype=np.float32)
        transform = cv2.getPerspectiveTransform(source, target)
        warped = cv2.warpPerspective(page, transform, (1100, 1350), borderValue=(70, 70, 70))
        mask = cv2.warpPerspective(np.full((1100, 760), 255, np.uint8), transform, (1100, 1350))
        canvas[mask > 0] = warped[mask > 0]
        lighting = np.linspace(0.82, 1.06, 1350, dtype=np.float32)[:, None, None]
        canvas = np.clip(canvas.astype(np.float32) * lighting, 0, 255).astype(np.uint8)
        canvas = cv2.GaussianBlur(canvas, (3, 3), 0.8)
        path = self.root / "blurred-photo.jpg"
        scan.atomic_write_image(path, canvas)
        return path

    def test_perspective_ocr_and_cache(self) -> None:
        fixture = self.make_perspective_fixture()
        result = scan.prepare_scan(str(self.home), str(fixture))
        self.assertTrue(result["ok"])
        self.assertTrue(result["processing"]["perspective_corrected"])
        self.assertTrue(result["ocr"]["models_hash_verified"])
        self.assertFalse(result["ocr"]["network_used"])
        self.assertGreaterEqual(result["ocr"]["mean_score"], 0.85)
        text = Path(result["ocr"]["text_path"]).read_text(encoding="utf-8").lower()
        self.assertIn("lucid", text)
        self.assertIn("abate", text)
        self.assertEqual(result["host_profile"]["priority"], "smoothness")

        cached = scan.prepare_scan(str(self.home), str(fixture))
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(cached["output_dir"], result["output_dir"])

    def test_blank_image_uses_low_confidence_tiles(self) -> None:
        fixture = self.root / "blank.png"
        blank = np.full((600, 900, 3), 245, np.uint8)
        scan.atomic_write_image(fixture, blank)
        result = scan.prepare_scan(str(self.home), str(fixture))
        self.assertEqual(result["ocr"]["confidence_level"], "low")
        self.assertIn("no_text_detected", result["ocr"]["flags"])
        self.assertEqual(
            result["token_strategy"]["route"], "ocr-text-then-only-relevant-retry-tiles"
        )
        self.assertGreaterEqual(len(result["token_strategy"]["retry_tiles"]), 1)

    def test_rejects_non_image(self) -> None:
        source = self.root / "notes.txt"
        source.write_text("not an image", encoding="utf-8")
        with self.assertRaises(scan.ScanError):
            scan.resolve_paths(str(self.home), str(source))

    def test_rejects_outside_and_linked_images(self) -> None:
        workspace = scan.workspace_root_from_script()
        with tempfile.TemporaryDirectory(dir=workspace.parent) as temporary:
            outside = Path(temporary) / "outside.png"
            scan.atomic_write_image(outside, np.full((20, 20, 3), 255, dtype=np.uint8))
            with self.assertRaises(scan.ScanError):
                scan.resolve_paths(str(self.home), str(outside))
            link = self.root / "linked.png"
            try:
                link.symlink_to(outside)
            except OSError:
                return
            with self.assertRaises(scan.ScanError):
                scan.resolve_paths(str(self.home), str(link))

    def test_model_hash_mismatch_aborts_before_ocr(self) -> None:
        fixture = self.make_perspective_fixture()
        original_hashes = dict(scan.MODEL_HASHES)
        first_model = next(iter(scan.MODEL_HASHES))
        scan.MODEL_HASHES[first_model] = "0" * 64
        try:
            with mock.patch.object(
                scan, "run_ocr", side_effect=AssertionError("OCR must not start")
            ):
                with self.assertRaises(scan.ScanError):
                    scan.prepare_scan(str(self.home), str(fixture), force=True)
        finally:
            scan.MODEL_HASHES.clear()
            scan.MODEL_HASHES.update(original_hashes)


if __name__ == "__main__":
    unittest.main()
