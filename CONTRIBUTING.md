# Contributing

Contributions should preserve the Skill's core behavior: repository-local data, deterministic
FSRS scheduling, first-attempt scoring, remediation without overwriting the first rating, local
OCR, and confidence-gated imports.

## Development setup

Run the repository-local setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Use `bash ./scripts/setup.sh` on Linux or macOS.

## Before opening a pull request

Run:

```powershell
.\adaptive-study-data\runtime\.venv\Scripts\python.exe .\scripts\validate_release.py
.\adaptive-study-data\runtime\.venv\Scripts\python.exe -m unittest discover `
  -s .\.agents\skills\adaptive-study-coach\scripts `
  -p "test_*.py" -v
```

Also run the lint, formatting, type, secret, SAST, and coverage commands enforced by CI. Follow
[code-review-standard.md](code-review-standard.md), including L3 review for security, database,
dependency, public-interface, OCR hash, and backup changes.

Keep pull requests focused. Add or update tests for behavior changes. Do not include generated
databases, imports, reports, backups, caches, OCR models, virtual environments, screenshots of
private study material, access tokens, or machine-specific absolute paths.

## Skill structure

Keep procedural instructions concise in `SKILL.md`. Put optional detail in a directly linked
file under `references`. Keep deterministic repeated operations in `scripts`.

By contributing, you agree that your contribution is licensed under the repository's MIT
License.
