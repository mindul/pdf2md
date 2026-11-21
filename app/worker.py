"""별도 프로세스에서 Docling 변환을 수행하는 작업자.

변환을 중지할 때 메인 서버는 이 프로세스를 종료하고 새로 띄운다.
Docling에는 실행 중인 변환을 취소하는 API가 없기 때문이다.
메인 프로세스와는 multiprocessing 큐로만 통신한다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def run_worker(task_q, event_q) -> None:
    import pypdfium2
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.progress import (
        ConversionPhase,
        PageCompletedProgress,
        PhaseStartedProgress,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import ImageRefMode

    converters: dict[tuple[bool, bool], DocumentConverter] = {}

    def get_converter(do_ocr: bool, with_images: bool) -> DocumentConverter:
        key = (do_ocr, with_images)
        if key not in converters:
            opts = PdfPipelineOptions()
            opts.do_ocr = do_ocr
            opts.do_table_structure = True
            opts.generate_picture_images = with_images
            opts.images_scale = 2.0
            converters[key] = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
            )
        return converters[key]

    event_q.put(("ready", None))
    while True:
        task = task_q.get()
        if task is None:
            return
        job_id = task["id"]
        pdf_path = Path(task["pdf_path"])
        out_dir = Path(task["out_dir"])
        stem = task["stem"]
        image_mode = task["image_mode"]

        def emit(kind, *args):
            event_q.put((kind, job_id, *args))

        def on_progress(event) -> None:
            if isinstance(event, PhaseStartedProgress):
                if event.phase == ConversionPhase.BUILD:
                    emit("phase", "build")
                elif event.phase in (ConversionPhase.ASSEMBLE, ConversionPhase.ENRICH):
                    emit("phase", "assemble")
            elif isinstance(event, PageCompletedProgress):
                emit("page", event.completed_pages, event.total_pages)

        try:
            emit("phase", "initialize")
            try:
                # 시작 전에 전체 쪽수를 알려 주면 진행률이 0쪽부터 바로 보인다.
                pdf = pypdfium2.PdfDocument(pdf_path)
                emit("page", 0, len(pdf))
                pdf.close()
            except Exception:  # noqa: BLE001 - 쪽수를 모르면 진행 이벤트로 채운다
                pass

            converter = get_converter(task["do_ocr"], image_mode != "placeholder")
            doc = converter.convert(pdf_path, progress_callback=on_progress).document
            emit("phase", "write")

            md_path = out_dir / f"{stem}.md"
            if image_mode == "referenced":
                artifacts = out_dir / f"{stem}_artifacts"
                doc.save_as_markdown(md_path, artifacts_dir=artifacts,
                                     image_mode=ImageRefMode.REFERENCED)
                # 마크다운 안의 이미지 경로를 zip 내부 상대경로로 맞춘다.
                md = md_path.read_text(encoding="utf-8")
                md_path.write_text(md.replace(str(artifacts) + "/", f"{artifacts.name}/"),
                                   encoding="utf-8")
                with zipfile.ZipFile(out_dir / f"{stem}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(md_path, md_path.name)
                    if artifacts.exists():
                        for f in sorted(artifacts.iterdir()):
                            zf.write(f, f"{artifacts.name}/{f.name}")
            else:
                mode = (ImageRefMode.EMBEDDED if image_mode == "embedded"
                        else ImageRefMode.PLACEHOLDER)
                md_path.write_text(doc.export_to_markdown(image_mode=mode), encoding="utf-8")

            emit("done", len(doc.pages) if doc.pages else None)
        except Exception as exc:  # noqa: BLE001 - 사용자에게 오류를 그대로 보여준다
            emit("error", f"{type(exc).__name__}: {exc}")
        finally:
            pdf_path.unlink(missing_ok=True)
