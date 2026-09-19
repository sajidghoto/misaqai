import fitz

from src.extraction.pymupdf_extractor import _blocks_from_text_page
from src.normalize.block_ir import NormalizedBlock


def extract_ocr_page(page: fitz.Page, page_number: int, language: str = "eng", dpi: int = 300) -> list[NormalizedBlock]:
	try:
		text_page = page.get_textpage_ocr(language=language, dpi=dpi)
	except Exception as error:
		raise RuntimeError(
			"OCR was requested but PyMuPDF could not invoke Tesseract. "
			"Install Tesseract OCR and ensure its executable and traineddata are available."
		) from error
	return _blocks_from_text_page(text_page, page_number, "ocr")
