"""Compiler Feedback Loop — Captures tsc/pyright error tracebacks for Bug Fixer self-correction."""

import re
from typing import Any, Dict, List
import pydantic


class CompilerErrorLocation(pydantic.BaseModel):
    filepath: str
    line_number: int
    column_number: int
    error_code: str
    message: str


class CompilerFeedbackLoop:
    """Parses compiler/type-checker output and feeds line-precise errors back to Bug Fixer."""

    def parse_typescript_errors(self, output: str) -> List[CompilerErrorLocation]:
        """Parse 'tsc --noEmit' output into structured error locations."""
        # e.g.: src/App.tsx(42,15): error TS2322: Type 'string' is not assignable to type 'number'.
        pattern = r"([^\s()]+\.[a-zA-Z0-9]+)\((\d+),(\d+)\):\s+error\s+([A-Z0-9]+):\s+(.*)"
        errors = []

        for line in output.splitlines():
            match = re.search(pattern, line)
            if match:
                errors.append(
                    CompilerErrorLocation(
                        filepath=match.group(1),
                        line_number=int(match.group(2)),
                        column_number=int(match.group(3)),
                        error_code=match.group(4),
                        message=match.group(5),
                    )
                )

        return errors
