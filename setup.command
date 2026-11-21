#!/bin/bash
# pdf2md 최초 설치 스크립트 (새 맥에서 한 번만 실행)
#  1) Python 3.10 이상 찾기   2) .venv 가상환경 만들기
#  3) 패키지 설치             4) Docling 모델 미리 받기
set -u
cd "$(dirname "$0")"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m[오류] %s\033[0m\n' "$*"; echo; read -r -p "엔터를 누르면 창을 닫습니다…" _; exit 1; }

say "pdf2md 설치를 시작합니다 ($(pwd))"

# --- 0. CPU 확인 -----------------------------------------------------------
if [ "$(uname -m)" != "arm64" ]; then
  echo "주의: 이 맥은 Intel 칩입니다. 최신 PyTorch는 Apple Silicon(M1 이후)만 지원하므로"
  echo "      설치가 실패할 수 있습니다. 계속 진행합니다."
fi

# --- 1. Python 찾기 ---------------------------------------------------------
PY=""
for cand in python3.15 python3.14 python3.13 python3.12 python3.11 python3.10 python3 \
            /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && \
     "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$cand")"; break
  fi
done
if [ -z "$PY" ]; then
  fail "Python 3.10 이상을 찾지 못했습니다.
   Homebrew가 있다면 터미널에서:  brew install python
   없다면 https://www.python.org/downloads/macos/ 에서 설치한 뒤 다시 실행하세요."
fi
say "1/4 Python: $PY ($("$PY" -V 2>&1))"

# --- 2. 가상환경 ------------------------------------------------------------
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys' 2>/dev/null; then
  say "2/4 기존 .venv 를 그대로 사용합니다"
else
  rm -rf .venv
  say "2/4 가상환경(.venv) 만드는 중…"
  "$PY" -m venv .venv || fail "가상환경을 만들지 못했습니다."
fi
.venv/bin/python -m pip install -q --upgrade pip || fail "pip 업그레이드 실패 (인터넷 연결을 확인하세요)."

# --- 3. 패키지 설치 ---------------------------------------------------------
say "3/4 패키지 설치 중… (처음엔 수 분 걸립니다, 약 1.5GB)"
if .venv/bin/python -m pip install -r requirements.lock.txt; then
  echo "→ 원본 맥과 같은 버전으로 설치했습니다."
else
  echo
  echo "→ 고정 버전 설치가 실패했습니다(Python 버전 차이 등). 호환 버전으로 다시 시도합니다."
  .venv/bin/python -m pip install -r requirements.txt || fail "패키지 설치에 실패했습니다. 위 오류 메시지를 확인하세요."
fi
.venv/bin/python -c "import docling, fastapi, uvicorn, multipart" || fail "설치 확인에 실패했습니다."

# --- 4. 모델 미리 받기 ------------------------------------------------------
say "4/4 Docling 모델 내려받는 중… (약 500MB, 한 번만)"
.venv/bin/python -m app.warmup 2>&1 | grep --line-buffered -E '^\s+- '
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  echo "주의: 모델을 미리 받지 못했습니다. 첫 변환 때 자동으로 받습니다(인터넷 필요)."
fi

chmod +x launch.command setup.command 2>/dev/null
say "설치 완료! 이제 launch.command 를 더블클릭해 실행하세요."
echo
read -r -p "엔터를 누르면 창을 닫습니다…" _
