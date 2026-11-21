"""PDF → Markdown 변환 웹 앱 (Docling 기반).

실행: .venv/bin/python -m uvicorn app.server:app --port 8000
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from app.worker import run_worker

BASE_DIR = Path(__file__).parent
WORK_DIR = Path(tempfile.mkdtemp(prefix="pdf2md_"))
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
IMAGE_MODES = {"placeholder", "embedded", "referenced"}
# 목록으로 보여줄 PDF 폴더 (기본: 프로젝트 폴더). PDF_DIR 환경변수로 변경 가능.
PDF_DIR = Path(os.environ.get("PDF_DIR", BASE_DIR.parent)).expanduser().resolve()

# 변환 대기열. Docling 변환은 CPU/메모리를 많이 쓰므로 한 번에 하나씩 처리한다.
_pending: queue.Queue[str] = queue.Queue()


@dataclass
class Job:
    id: str
    filename: str
    stem: str
    image_mode: str
    do_ocr: bool
    status: str = "queued"  # queued | running | done | error | cancelled
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    pages: int | None = None
    # 진행 상황: queued → initialize → build(페이지) → assemble → write → done
    phase: str = "queued"
    done_pages: int = 0
    build_started: float | None = None
    cancel_requested: bool = False

    @property
    def dir(self) -> Path:
        return WORK_DIR / self.id

    @property
    def md_path(self) -> Path:
        return self.dir / f"{self.stem}.md"

    @property
    def zip_path(self) -> Path:
        return self.dir / f"{self.stem}.zip"

    def progress(self) -> float:
        """0~1 사이 전체 진행률. 페이지 분석이 대부분의 시간을 차지하므로 90%를 배정."""
        if self.status == "done":
            return 1.0
        if self.phase == "build" and self.pages:
            return 0.03 + 0.87 * min(self.done_pages / self.pages, 1)
        return {"queued": 0.0, "initialize": 0.01, "assemble": 0.92, "write": 0.97}.get(self.phase, 0.0)

    def eta(self) -> float | None:
        """페이지 처리 속도로 추정한 남은 시간(초)."""
        if self.phase != "build" or not self.pages or self.done_pages < 2 or not self.build_started:
            return None
        per_page = (time.time() - self.build_started) / self.done_pages
        remaining = per_page * (self.pages - self.done_pages)
        return round(remaining * 1.1 + 2, 0)  # 조립·저장 시간을 약간 더한다

    def to_dict(self) -> dict:
        now = time.time()
        elapsed = None
        if self.started:
            elapsed = round((self.finished or now) - self.started, 1)
        queue_ahead = None
        if self.status == "queued":
            queue_ahead = sum(1 for j in _jobs.values()
                              if j.status in ("queued", "running") and j.created < self.created)
        return {
            "phase": self.phase,
            "done_pages": self.done_pages,
            "progress": round(self.progress(), 4),
            "eta": self.eta(),
            "queue_ahead": queue_ahead,
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "error": self.error,
            "image_mode": self.image_mode,
            "do_ocr": self.do_ocr,
            "pages": self.pages,
            "elapsed": elapsed,
            "has_zip": self.status == "done" and self.zip_path.exists(),
        }


_jobs: dict[str, Job] = {}


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")
    return stem[:150] or "document"


class _Worker:
    """Docling을 실행하는 자식 프로세스. 중지할 때는 프로세스째 종료하고 새로 띄운다."""

    _ctx = mp.get_context("spawn")

    def __init__(self) -> None:
        self.start()

    def start(self) -> None:
        self.task_q = self._ctx.Queue()
        self.event_q = self._ctx.Queue()
        self.proc = self._ctx.Process(target=run_worker, args=(self.task_q, self.event_q),
                                      daemon=True, name="pdf2md-worker")
        self.proc.start()

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.join(3)
        if self.proc.is_alive():
            self.proc.kill()
            self.proc.join()

    def restart(self) -> None:
        self.stop()
        self.start()


_worker: _Worker | None = None


def _run_on_worker(worker: _Worker, job: Job) -> str:
    """작업 하나를 작업자에게 맡기고 끝날 때까지 진행 이벤트를 반영한다. 최종 상태를 돌려준다."""
    worker.task_q.put({
        "id": job.id, "pdf_path": str(job.dir / "input.pdf"), "out_dir": str(job.dir),
        "stem": job.stem, "image_mode": job.image_mode, "do_ocr": job.do_ocr,
    })
    while True:
        if job.cancel_requested:
            worker.restart()
            return "cancelled"
        if not worker.proc.is_alive():
            job.error = "변환 프로세스가 비정상 종료되었습니다 (메모리 부족일 수 있습니다)."
            worker.restart()
            return "error"
        try:
            kind, job_id, *args = worker.event_q.get(timeout=0.25)
        except queue.Empty:
            continue
        if job_id != job.id:
            continue
        if kind == "phase":
            job.phase = args[0]
            if job.phase == "build":
                job.build_started = job.build_started or time.time()
        elif kind == "page":
            done, total = args
            job.pages = total
            job.done_pages = done
            if done and job.phase != "build":
                job.phase = "build"
                job.build_started = job.build_started or time.time()
        elif kind == "done":
            job.pages = args[0] or job.pages
            job.phase = "done"
            return "done"
        elif kind == "error":
            job.error = args[0]
            return "error"


def _dispatch_loop() -> None:
    while True:
        job = _jobs.get(_pending.get())
        if job is None or job.status != "queued":
            continue  # 대기 중에 중지·삭제된 작업
        job.status = "running"
        job.phase = "initialize"
        job.started = time.time()
        try:
            job.status = _run_on_worker(_worker, job)
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
        job.finished = time.time()
        if job.status == "cancelled":
            # 중간에 남은 입력·부분 결과물은 지운다.
            shutil.rmtree(job.dir, ignore_errors=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _worker
    _worker = _Worker()
    threading.Thread(target=_dispatch_loop, daemon=True, name="pdf2md-dispatch").start()
    yield
    _worker.stop()


app = FastAPI(title="pdf2md", lifespan=lifespan)


def _job_or_404(job_id: str) -> Job:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


def _new_job(filename: str, image_mode: str, do_ocr: bool) -> Job:
    if image_mode not in IMAGE_MODES:
        raise HTTPException(400, "image_mode 값이 올바르지 않습니다.")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 변환할 수 있습니다.")
    job = Job(id=uuid.uuid4().hex, filename=filename, stem=_safe_stem(filename),
              image_mode=image_mode, do_ocr=do_ocr)
    job.dir.mkdir(parents=True)
    return job


def _submit(job: Job) -> dict:
    pdf_path = job.dir / "input.pdf"
    with pdf_path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            shutil.rmtree(job.dir, ignore_errors=True)
            raise HTTPException(400, "올바른 PDF 파일이 아닙니다.")
    _jobs[job.id] = job
    _pending.put(job.id)
    return job.to_dict()


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    image_mode: str = Form("placeholder"),
    do_ocr: bool = Form(False),
) -> dict:
    job = _new_job(file.filename or "document.pdf", image_mode, do_ocr)
    size = 0
    with (job.dir / "input.pdf").open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                shutil.rmtree(job.dir, ignore_errors=True)
                raise HTTPException(413, "파일이 너무 큽니다 (최대 300MB).")
            out.write(chunk)
    return _submit(job)


def _local_pdfs() -> list[Path]:
    if not PDF_DIR.is_dir():
        return []
    return sorted((p for p in PDF_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


@app.get("/api/local-files")
def list_local_files() -> dict:
    files = [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
             for p in _local_pdfs()]
    return {"dir": str(PDF_DIR), "files": files}


@app.post("/api/jobs/local")
def create_local_job(
    name: str = Form(...),
    image_mode: str = Form("placeholder"),
    do_ocr: bool = Form(False),
) -> dict:
    # 목록에 있는 파일 이름만 허용 (경로 조작 방지)
    # macOS 파일명은 NFD(자모 분리)일 수 있으므로 정규화해서 비교한다.
    want = unicodedata.normalize("NFC", name)
    src = next((p for p in _local_pdfs() if unicodedata.normalize("NFC", p.name) == want), None)
    if src is None:
        raise HTTPException(404, "폴더에서 해당 PDF를 찾을 수 없습니다.")
    job = _new_job(src.name, image_mode, do_ocr)
    shutil.copyfile(src, job.dir / "input.pdf")  # 원본은 건드리지 않는다
    return _submit(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _job_or_404(job_id).to_dict()


@app.get("/api/jobs/{job_id}/markdown")
def get_markdown(job_id: str, download: bool = False):
    job = _job_or_404(job_id)
    if job.status != "done":
        raise HTTPException(409, "아직 변환이 끝나지 않았습니다.")
    if download:
        return FileResponse(job.md_path, media_type="text/markdown; charset=utf-8",
                            filename=job.md_path.name)
    return PlainTextResponse(job.md_path.read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/zip")
def get_zip(job_id: str):
    job = _job_or_404(job_id)
    if job.status != "done" or not job.zip_path.exists():
        raise HTTPException(404, "ZIP 파일이 없습니다.")
    return FileResponse(job.zip_path, media_type="application/zip", filename=job.zip_path.name)


@app.get("/api/jobs/{job_id}/artifacts/{name}")
def get_artifact(job_id: str, name: str):
    """미리보기에서 참조 이미지(referenced 모드)를 보여주기 위한 엔드포인트."""
    job = _job_or_404(job_id)
    artifacts = (job.dir / f"{job.stem}_artifacts").resolve()
    path = (artifacts / name).resolve()
    if path.parent != artifacts or not path.is_file():
        raise HTTPException(404, "파일이 없습니다.")
    return FileResponse(path)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if job.status == "queued":
        job.status = "cancelled"
        job.finished = time.time()
        shutil.rmtree(job.dir, ignore_errors=True)
    elif job.status == "running":
        job.cancel_requested = True  # 디스패처가 작업자 프로세스를 종료한다
    else:
        raise HTTPException(409, "이미 끝난 작업입니다.")
    return job.to_dict()


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if job.status in ("queued", "running"):
        raise HTTPException(409, "변환 중인 작업은 삭제할 수 없습니다.")
    shutil.rmtree(job.dir, ignore_errors=True)
    del _jobs[job_id]
    return {"ok": True}
