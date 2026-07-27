#!/usr/bin/env bash
set -u

emit_error() {
  local message="$1"
  local error_type="${2:-LauncherError}"
  python3 - "${message}" "${error_type}" <<'PY'
import json
import sys
print(json.dumps({
    "ok": False,
    "error": sys.argv[1],
    "error_type": sys.argv[2],
    "action": "Run the repository setup script.",
}, ensure_ascii=False))
PY
}

script_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd -P -- "${script_dir}/../../../.." && pwd)"
requested_home="${ADAPTIVE_STUDY_HOME:-adaptive-study-data}"

if ! study_home="$(
  python3 - "${workspace_root}" "${requested_home}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve(strict=True)
candidate = Path(sys.argv[2])
if not candidate.is_absolute():
    candidate = root / candidate
resolved = candidate.resolve(strict=False)
if resolved == root or not resolved.is_relative_to(root):
    raise SystemExit(2)
print(resolved)
PY
)"; then
  emit_error "ADAPTIVE_STUDY_HOME escapes the repository workspace." "PathBoundaryError"
  exit 2
fi

cache_root="${study_home}/cache"
export TMPDIR="${cache_root}/temp"
export PIP_CACHE_DIR="${cache_root}/pip"
export PYTHONPYCACHEPREFIX="${cache_root}/pycache"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONWARNINGS=ignore
export PIP_DISABLE_PIP_VERSION_CHECK=1

venv_python="${study_home}/runtime/.venv/bin/python"
manager="${script_dir}/study_coach.py"
if [[ ! -x "${venv_python}" ]]; then
  emit_error "Local Python runtime is missing: ${venv_python}" "RuntimeMissing"
  exit 2
fi

if ! mkdir -p "${TMPDIR}" "${PIP_CACHE_DIR}" "${PYTHONPYCACHEPREFIX}"; then
  emit_error "Unable to create repository-local cache directories." "FilesystemError"
  exit 2
fi

exec "${venv_python}" "${manager}" --home "${study_home}" "$@"
