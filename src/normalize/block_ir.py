from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NormalizedBlock(BaseModel):
	model_config = ConfigDict(extra="forbid")

	text: str = Field(min_length=1)
	page: int = Field(ge=1)
	bbox: tuple[float, float, float, float]
	font_size: float | None = Field(default=None, ge=0)
	font_name: str | None = None
	extraction_method: Literal["native", "ocr"]


class NormalizedDocument(BaseModel):
	model_config = ConfigDict(extra="forbid")

	source_file: str
	page_count: int = Field(ge=1)
	page_methods: list[Literal["native", "ocr"]]
	blocks: list[NormalizedBlock]
