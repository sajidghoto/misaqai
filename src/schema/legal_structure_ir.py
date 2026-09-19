from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
	model_config = ConfigDict(extra="forbid")

	page: int = Field(ge=1)
	bbox: tuple[float, float, float, float]
	extraction_method: Literal["native", "ocr"]


class ActMeta(BaseModel):
	model_config = ConfigDict(extra="forbid")

	jurisdiction: str
	enacting_authority: str
	assent_authority: str | None = None
	long_title: str = ""
	short_title: str = ""
	commencement_date: str | None = None


class Proviso(BaseModel):
	model_config = ConfigDict(extra="forbid")

	text: str


class Explanation(BaseModel):
	model_config = ConfigDict(extra="forbid")

	text: str


class Subclause(BaseModel):
	model_config = ConfigDict(extra="forbid")

	subclause_id: str
	text: str


class Clause(BaseModel):
	model_config = ConfigDict(extra="forbid")

	clause_id: str
	text: str
	subclauses: list[Subclause] = Field(default_factory=list)
	provisos: list[Proviso] = Field(default_factory=list)
	explanations: list[Explanation] = Field(default_factory=list)


class Subsection(BaseModel):
	model_config = ConfigDict(extra="forbid")

	subsection_number: str
	text: str
	clauses: list[Clause] = Field(default_factory=list)
	provisos: list[Proviso] = Field(default_factory=list)
	explanations: list[Explanation] = Field(default_factory=list)


class Section(BaseModel):
	model_config = ConfigDict(extra="forbid")

	section_number: str
	marginal_note: str | None = None
	text: str
	ocr_raw: str | None = None
	subsections: list[Subsection] = Field(default_factory=list)
	provisos: list[Proviso] = Field(default_factory=list)
	explanations: list[Explanation] = Field(default_factory=list)
	schedule_refs: list[str] = Field(default_factory=list)
	amendment_history: list[str] = Field(default_factory=list)
	provenance: list[Provenance] = Field(default_factory=list)


class Part(BaseModel):
	model_config = ConfigDict(extra="forbid")

	part_number: str
	part_title: str
	sections: list[Section] = Field(default_factory=list)


class Chapter(BaseModel):
	model_config = ConfigDict(extra="forbid")

	chapter_number: str
	chapter_title: str
	parts: list[Part] = Field(default_factory=list)
	sections: list[Section] = Field(default_factory=list)


class Schedule(BaseModel):
	model_config = ConfigDict(extra="forbid")

	schedule_name: str
	schedule_title: str
	content: str


class Flag(BaseModel):
	model_config = ConfigDict(extra="forbid")

	location: str
	issue_type: Literal[
		"ambiguous_boundary",
		"ocr_uncertainty",
		"unresolved_reference",
		"missing_expected_field",
		"other",
	]
	snippet: str
	note: str


class Act(BaseModel):
	model_config = ConfigDict(extra="forbid")

	meta: ActMeta
	preamble: str = ""
	definitions: list[str] = Field(default_factory=list)
	chapters: list[Chapter] = Field(default_factory=list)
	sections: list[Section] = Field(default_factory=list)
	schedules: list[Schedule] = Field(default_factory=list)
	flags: list[Flag] = Field(default_factory=list)
