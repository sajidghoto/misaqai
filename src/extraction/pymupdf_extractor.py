from collections import Counter

import fitz

from src.normalize.block_ir import NormalizedBlock


def _blocks_from_text_page(text_page: fitz.TextPage, page_number: int, method: str) -> list[NormalizedBlock]:
	blocks: list[NormalizedBlock] = []
	for block in text_page.extractDICT().get("blocks", []):
		if block.get("type") != 0:
			continue
		spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
		text = "".join(span.get("text", "") for span in spans).strip()
		if not text:
			continue
		font_sizes = [float(span["size"]) for span in spans if span.get("size") is not None]
		font_names = [span.get("font") for span in spans if span.get("font")]
		blocks.append(
			NormalizedBlock(
				text=text,
				page=page_number,
				bbox=tuple(float(value) for value in block["bbox"]),
				font_size=sum(font_sizes) / len(font_sizes) if font_sizes else None,
				font_name=Counter(font_names).most_common(1)[0][0] if font_names else None,
				extraction_method=method,
			)
		)
	return blocks


def extract_native_page(page: fitz.Page, page_number: int) -> list[NormalizedBlock]:
	return _blocks_from_text_page(page.get_textpage(), page_number, "native")
