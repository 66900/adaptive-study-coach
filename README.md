# Adaptive Study Coach

A repository-local Codex Skill for importing study material, running FSRS-based spaced
repetition, repairing wrong answers with same-concept variants, and conducting weekly or
monthly tests. It supports English vocabulary and other academic subjects.

The optional image pipeline performs deterministic document cleanup and local OCR before Codex
reads an image. It uses perspective correction, deskew, lighting normalization, conservative
sharpening, content-addressed caching, and confidence-based image routing.

## Privacy model

- Learning data stays in `<repository>\adaptive-study-data` by default.
- The repository ignores databases, imports, reports, backups, caches, virtual environments,
  and OCR models.
- Image OCR uses local RapidOCR/ONNX models. The runtime supplies local model paths and rejects
  missing or changed models instead of downloading them during a study session.
- Input files and the optional `ADAPTIVE_STUDY_HOME` must remain inside the repository
  workspace.
- The Skill does not create reminders, scheduled tasks, accounts, or global links.

## Requirements

- Windows 10/11 with PowerShell 5.1+, or Linux/macOS with Bash
- Python 3.10 or newer
- Codex with repository-local `.agents/skills` discovery

## Quick start

Clone or download the repository, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

`setup.ps1` and `run-study.ps1` are Windows-only and stop before making changes on other
operating systems. On Linux or macOS:

```bash
bash ./scripts/setup.sh
```

The setup script creates an isolated virtual environment and all caches under
`adaptive-study-data`. It does not install packages globally.

Open the repository root as the Codex workspace. Example prompts:

```text
$adaptive-study-coach import today's vocabulary
$adaptive-study-coach recognize and import this study photo
$adaptive-study-coach start today's review
$adaptive-study-coach start the weekly test
$adaptive-study-coach show my progress
```

中文示例：

```text
$adaptive-study-coach 导入今天背的单词
$adaptive-study-coach 识别并导入这张学习图片
$adaptive-study-coach 开始今天的复习
$adaptive-study-coach 开始周测
$adaptive-study-coach 查看学习进度
```

## Repository layout

```text
.agents/skills/adaptive-study-coach/   Codex Skill
.github/workflows/ci.yml               Windows/Linux tests and quality gates
scripts/setup.ps1 / scripts/setup.sh   Repository-local setup
scripts/validate_release.py            Privacy and release validation
code-review-standard.md                Required public review and merge policy
requirements.txt                       Pinned dependencies
```

Runtime data is created under `adaptive-study-data` and must not be committed.

## Validation

```powershell
python .\scripts\validate_release.py
python -m unittest discover `
  -s .\.agents\skills\adaptive-study-coach\scripts `
  -p "test_*.py" -v
```

The image tests generate synthetic blurred and perspective-distorted documents. They do not
contain user data.

Development checks and review requirements are defined in
[code-review-standard.md](code-review-standard.md).

## Accuracy limits

Image enhancement cannot recover strokes or symbols absent from the source. OCR confidence is
not proof of correctness. Low-confidence characters, formulas, units, tables, missing answers,
and unresolved conflicts must remain pending until a person verifies them.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Third-party components are
listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT License. See [LICENSE](LICENSE).
