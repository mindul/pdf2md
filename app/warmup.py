"""설치 직후 Docling 모델을 미리 내려받기 위한 짧은 테스트 변환.

웹 앱과 같은 설정으로 1쪽짜리 PDF를 변환해, 앱이 실제로 쓰는 모델
(레이아웃·표 인식, OCR)이 ~/.cache 에 받아지도록 한다.

실행: .venv/bin/python -m app.warmup
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    import pypdfium2
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "warmup.pdf"
        pdf = pypdfium2.PdfDocument.new()
        pdf.new_page(595, 842)  # 빈 A4 한 쪽
        pdf.save(pdf_path)
        pdf.close()

        for do_ocr, label in ((False, "레이아웃·표 인식 모델"), (True, "OCR 모델")):
            print(f"  - {label} 준비 중…", flush=True)
            opts = PdfPipelineOptions()
            opts.do_ocr = do_ocr
            opts.do_table_structure = True
            if do_ocr:
                opts.ocr_options.force_full_page_ocr = True  # 빈 페이지에도 OCR 모델을 불러오게
            DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
            ).convert(pdf_path)
    print("  - 모델 준비 완료", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
