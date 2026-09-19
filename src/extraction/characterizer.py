from dataclasses import dataclass

import fitz


@dataclass(frozen=True)
class PageCharacterization:
	page: int
	has_usable_text: bool
	extraction_method: str
	text_length: int


def has_usable_text(text: str) -> bool:
	normalized = " ".join(text.split())
	return len(normalized) >= 20 and any(character.isalnum() for character in normalized)


def characterize_document(document: fitz.Document) -> list[PageCharacterization]:
	decisions: list[PageCharacterization] = []
	for index, page in enumerate(document):
		text = page.get_text("text")
		usable = has_usable_text(text)
		decisions.append(
			PageCharacterization(
				page=index + 1,
				has_usable_text=usable,
				extraction_method="native" if usable else "ocr",
				text_length=len(" ".join(text.split())),
			)
		)
	return decisions
