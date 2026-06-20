import re

from localforge.prd.schemas import SizingResult

VAGUE_ACCEPTANCE = {"works", "done", "complete", "implemented", "ok"}
COMPONENT_WORDS = {"api", "backend", "frontend", "cli", "database", "scheduler", "ui", "billing"}


def size_task(
    *,
    title: str,
    description: str,
    acceptance_criteria: list[str],
    risk_level: str = "low",
    expected_files: list[str] | None = None,
) -> SizingResult:
    reasons: list[str] = []
    text = f"{title} {description}".lower()
    files = expected_files or re.findall(r"\b[\w./-]+\.(?:py|ts|tsx|js|jsx|md|yml|yaml)\b", text)
    components = {word for word in COMPONENT_WORDS if word in text}

    if len(files) > 3:
        reasons.append("too many files expected")
    if len(components) > 2 or " and " in text and len(components) > 1:
        reasons.append("multiple components")
    if risk_level == "high":
        reasons.append("high risk")
    has_vague_acceptance = all(
        c.strip().lower() in VAGUE_ACCEPTANCE for c in acceptance_criteria
    )
    if not acceptance_criteria or has_vague_acceptance:
        reasons.append("ambiguous acceptance")

    normalized_acceptance = acceptance_criteria or [f"Complete: {title}"]
    if reasons and "ambiguous acceptance" in reasons:
        normalized_acceptance = [f"Specific acceptance must be defined for: {title}"]

    final_risk = "high" if risk_level == "high" or len(reasons) >= 2 else risk_level
    return SizingResult(
        needs_split=bool(reasons),
        risk_level=final_risk,
        reasons=reasons,
        acceptance_criteria=normalized_acceptance,
    )
