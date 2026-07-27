#!/usr/bin/env python3
"""Validate that a repository candidate contains only portable, publishable source."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "adaptive-study-coach"
REQUIRED_FILES = {
    REPO_ROOT / "README.md",
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "THIRD_PARTY_NOTICES.md",
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "requirements-dev.txt",
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "code-review-standard.md",
    REPO_ROOT / "scripts" / "setup.sh",
    REPO_ROOT / "scripts" / "path-guard.ps1",
    REPO_ROOT / "scripts" / "test-path-guard.ps1",
    REPO_ROOT / "scripts" / "check_secrets.py",
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "agents" / "openai.yaml",
    SKILL_ROOT / "scripts" / "run-study.sh",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".onnx", ".pyc", ".pyo"}
FORBIDDEN_PARTS = {
    ".adaptive-study-data",
    "adaptive-study-data",
    "__pycache__",
    ".venv",
    "backups",
    "imports",
    "reports",
    "学习系统",
}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".gitignore",
    ".gitattributes",
}
HARD_CODED_PATHS = (
    re.compile(re.escape("D:" + "\\" + "\u5b66\u4e60"), re.IGNORECASE),
    re.compile(
        re.escape("C:" + "\\" + "Users" + "\\") + r"[^\\\s]+",
        re.IGNORECASE,
    ),
    re.compile("/" + "Users" + r"/[^/\s]+"),
    re.compile("/" + "home" + r"/[^/\s]+"),
)


def validate_frontmatter(skill_path: Path) -> list[str]:
    errors = []
    text = skill_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ["SKILL.md must start with YAML frontmatter."]
    try:
        _, frontmatter, _ = text.split("---", 2)
    except ValueError:
        return ["SKILL.md frontmatter is not closed."]
    fields = {}
    for line in frontmatter.strip().splitlines():
        if ":" not in line:
            errors.append(f"Invalid SKILL.md frontmatter line: {line}")
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"}:
        errors.append("SKILL.md frontmatter must contain only name and description.")
    if fields.get("name") != "adaptive-study-coach":
        errors.append("SKILL.md name must be adaptive-study-coach.")
    if len(fields.get("description", "")) < 40:
        errors.append("SKILL.md description is unexpectedly short.")
    return errors


def main() -> int:
    errors = []
    for required in sorted(REQUIRED_FILES):
        if not required.is_file():
            errors.append(f"Missing required file: {required.relative_to(REPO_ROOT)}")

    for path in REPO_ROOT.rglob("*"):
        if ".git" in path.parts or path == REPO_ROOT:
            continue
        relative = path.relative_to(REPO_ROOT)
        if path.is_symlink():
            errors.append(f"Symlink is not allowed in release source: {relative}")
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            errors.append(f"Generated/private path found: {relative}")
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"Generated/private file found: {relative}")
        if path.stat().st_size > 2 * 1024 * 1024:
            errors.append(f"Unexpected file larger than 2 MB: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore", ".gitattributes"}:
            text = path.read_text(encoding="utf-8")
            for pattern in HARD_CODED_PATHS:
                if pattern.search(text):
                    errors.append(f"Machine-specific absolute path found in: {relative}")
                    break

    if (SKILL_ROOT / "SKILL.md").is_file():
        errors.extend(validate_frontmatter(SKILL_ROOT / "SKILL.md"))

    result = {
        "ok": not errors,
        "repository": str(REPO_ROOT),
        "skill": str(SKILL_ROOT),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
