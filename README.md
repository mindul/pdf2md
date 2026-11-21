# pdf2md

PDF를 Markdown으로 변환하는 로컬 웹 앱입니다. [Docling](https://github.com/docling-project/docling)으로 문서의 레이아웃과 표를 인식하고, 브라우저에서 파일을 올리면 변환된 `.md`를 바로 보거나 내려받을 수 있습니다. 모든 처리는 내 맥 안에서 이뤄지며 PDF가 외부로 전송되지 않습니다.

<img width="931" height="628" alt="pdf2md 실행 화면" src="https://github.com/user-attachments/assets/b75dc252-5fbc-4e8b-b583-cd693181d282" />

## 주요 기능

- **표·레이아웃 인식**: 제목, 문단, 목록, 표 구조를 살려 Markdown으로 변환
- **이미지 처리 방식 선택**
  - 생략: 이미지 자리에 `<!-- image -->`만 표시 (가장 빠름)
  - MD에 포함: 이미지를 base64로 넣어 파일 하나로 완결
  - 별도 파일 (ZIP): `.md`와 이미지 폴더를 ZIP으로 묶어 제공
- **OCR**: 스캔본 PDF는 OCR을 켜서 변환 (느려지므로 필요할 때만)
- **진행률·남은 시간 표시**, 변환 중지, 여러 파일 대기열 처리 (한 번에 하나씩)
- **로컬 폴더 PDF 목록**: 지정한 폴더의 PDF를 업로드 없이 바로 골라 변환

## 요구 사항

- macOS, Apple Silicon(M1 이후) 권장 — Intel 맥은 최신 PyTorch 미지원으로 설치가 실패할 수 있음
- Python 3.10 이상
- 디스크 여유 공간 약 2GB (패키지 약 1.5GB + 모델 약 500MB)
- 최초 설치 시 인터넷 연결

## 설치

새 맥에서 한 번만 실행합니다. Finder에서 `setup.command`를 더블클릭하거나 터미널에서:

```sh
./setup.command
```

스크립트가 다음을 차례로 처리합니다.

1. Python 3.10 이상 찾기
2. `.venv` 가상환경 만들기
3. 패키지 설치 (`requirements.lock.txt`의 고정 버전, 실패하면 `requirements.txt`로 재시도)
4. Docling 모델 미리 내려받기 (`python -m app.warmup`)

## 실행

`launch.command`를 더블클릭하면 서버가 뜨고 브라우저에서 <http://127.0.0.1:8000> 이 열립니다.

```sh
./launch.command

# 직접 실행
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
```

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | 웹 서버 포트 (`launch.command`) |
| `PDF_DIR` | 프로젝트 폴더 | "로컬 파일" 목록에 보여줄 PDF 폴더 |

업로드 파일은 최대 300MB까지 받습니다. 변환 결과는 임시 폴더에 저장되므로 필요한 파일은 내려받아 두세요.

## 다른 맥으로 옮기기

```sh
./make-package.command
```

`dist/pdf2md-transfer.zip`이 만들어집니다. `.venv`, PDF, 변환 결과 같은 개인 파일은 들어가지 않습니다. 새 맥에서 압축을 풀고 `setup.command` → `launch.command` 순서로 실행하면 됩니다.

## 프로젝트 구조

```
app/
  server.py       FastAPI 서버 (업로드, 작업 대기열, 결과 다운로드 API)
  worker.py       별도 프로세스에서 Docling 변환 수행 (중지 시 프로세스 재시작)
  warmup.py       설치 직후 모델을 미리 받기 위한 테스트 변환
  static/         웹 UI (index.html)
tools/
  build_manual.py MANUAL.md → MANUAL.html 변환
setup.command        최초 설치 스크립트
launch.command       실행 스크립트
make-package.command 이전용 패키지 생성 스크립트
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/jobs` | PDF 업로드 후 변환 작업 생성 |
| `GET` | `/api/local-files` | `PDF_DIR`의 PDF 목록 |
| `POST` | `/api/jobs/local` | 로컬 폴더의 PDF로 작업 생성 |
| `GET` | `/api/jobs/{id}` | 작업 상태·진행률 |
| `GET` | `/api/jobs/{id}/markdown` | 변환된 Markdown |
| `GET` | `/api/jobs/{id}/zip` | Markdown + 이미지 ZIP |
| `POST` | `/api/jobs/{id}/cancel` | 변환 중지 |
| `DELETE` | `/api/jobs/{id}` | 작업 삭제 |
