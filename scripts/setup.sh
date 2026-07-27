#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -P -- "${script_dir}/.." && pwd)"
python_exe="${PYTHON_EXE:-python3}"
requested_home="${ADAPTIVE_STUDY_HOME:-adaptive-study-data}"

study_home="$(
  "${python_exe}" - "${repo_root}" "${requested_home}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve(strict=True)
candidate = Path(sys.argv[2])
if not candidate.is_absolute():
    candidate = root / candidate
resolved = candidate.resolve(strict=False)
if resolved == root or not resolved.is_relative_to(root):
    raise SystemExit("ADAPTIVE_STUDY_HOME must be a child of the repository")
print(resolved)
PY
)"

cache_root="${study_home}/cache"
export TMPDIR="${cache_root}/temp"
export PIP_CACHE_DIR="${cache_root}/pip"
export PYTHONPYCACHEPREFIX="${cache_root}/pycache"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONWARNINGS=ignore
export PIP_DISABLE_PIP_VERSION_CHECK=1
mkdir -p "${TMPDIR}" "${PIP_CACHE_DIR}" "${PYTHONPYCACHEPREFIX}"

venv_root="${study_home}/runtime/.venv"
venv_python="${venv_root}/bin/python"
if [[ ! -x "${venv_python}" ]]; then
  "${python_exe}" -m venv "${venv_root}"
fi
"${venv_python}" -m pip install --requirement "${repo_root}/requirements.txt"

launcher="${repo_root}/.agents/skills/adaptive-study-coach/scripts/run-study.sh"
if [[ "${1:-}" != "--skip-init" ]]; then
  health="$(bash "${launcher}" health)"
  initialized="$(
    "${venv_python}" -c 'import json,sys; print(str(bool(json.load(sys.stdin).get("initialized"))).lower())' \
      <<<"${health}"
  )"
  if [[ "${initialized}" != "true" ]]; then
    bash "${launcher}" init
  fi
fi

printf 'Adaptive Study Coach is ready.\nWorkspace: %s\nData home: %s\n' \
  "${repo_root}" "${study_home}"
