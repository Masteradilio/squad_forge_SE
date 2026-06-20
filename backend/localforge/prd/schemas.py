from pydantic import BaseModel, Field


class ExtractedEpic(BaseModel):
    title: str
    summary: str
    acceptance_summary: str | None = None
    priority: int = 1


class ExtractedTask(BaseModel):
    epic_title: str | None = None
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    expected_files: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ExtractedPlan(BaseModel):
    epics: list[ExtractedEpic] = Field(default_factory=list)
    tasks: list[ExtractedTask] = Field(default_factory=list)


class SizingResult(BaseModel):
    needs_split: bool
    risk_level: str
    reasons: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
