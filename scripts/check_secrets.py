#!/usr/bin/env python3
"""Fail CI when detect-secrets reports an unallowlisted finding."""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

# The subprocess is a fixed module invocation with shell disabled.
REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--all-files",
            "--exclude-files",
            (
                r"(^|[\\/])("
                r"\.git|adaptive-study-data|\.mypy_cache|\.ruff_cache|"
                r"\.pytest_cache|__pycache__|\.venv|venv"
                r")([\\/]|$)"
            ),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        print(f"detect-secrets returned invalid JSON: {exc}", file=sys.stderr)
        return 2
    findings = report.get("results", {})
    if findings:
        print(json.dumps(findings, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print("detect-secrets: no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
