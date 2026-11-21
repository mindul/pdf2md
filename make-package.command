#!/bin/bash
# 다른 맥으로 옮길 패키지(dist/pdf2md-transfer.zip)를 만든다.
# .venv, PDF, 변환 결과 같은 개인 파일은 넣지 않는다.
set -euo pipefail
cd "$(dirname "$0")"

FILES=(app launch.command setup.command requirements.txt requirements.lock.txt MANUAL.md MANUAL.html)

echo "1) 패키지 버전 목록 갱신"
{ echo "# 원본 맥($(uname -m), $(.venv/bin/python -V 2>&1))에서 동작 확인된 전체 패키지 버전 고정 목록"
  .venv/bin/python -m pip freeze; } > requirements.lock.txt

echo "2) MANUAL.md → MANUAL.html"
.venv/bin/python tools/build_manual.py >/dev/null

echo "3) 압축"
STAGE="$(mktemp -d)/pdf2md"
mkdir -p "$STAGE"
rsync -a --exclude '__pycache__' --exclude '.DS_Store' "${FILES[@]}" "$STAGE"/
chmod +x "$STAGE"/*.command
mkdir -p dist
rm -f dist/pdf2md-transfer.zip
# ditto: macOS 권한(실행 비트)을 보존하는 압축
ditto -c -k --keepParent "$STAGE" dist/pdf2md-transfer.zip
rm -rf "$(dirname "$STAGE")"

echo
echo "완료: $(pwd)/dist/pdf2md-transfer.zip ($(du -h dist/pdf2md-transfer.zip | cut -f1))"
zipinfo -1 dist/pdf2md-transfer.zip | grep -v '/$' | sed 's/^/  /'
