from enum import StrEnum


class FailureClass(StrEnum):
    TEST_ASSERTION_FAILURE = "TEST_ASSERTION_FAILURE"
    TYPECHECK_FAILURE = "TYPECHECK_FAILURE"
    LINT_FAILURE = "LINT_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    IMPORT_ERROR = "IMPORT_ERROR"
    RUNTIME_EXCEPTION = "RUNTIME_EXCEPTION"
    MODEL_BAD_EDIT = "MODEL_BAD_EDIT"
    CONFLICTING_REQUIREMENT = "CONFLICTING_REQUIREMENT"
    AMBIGUOUS_REQUIREMENT = "AMBIGUOUS_REQUIREMENT"
    COMMAND_BLOCKED_BY_POLICY = "COMMAND_BLOCKED_BY_POLICY"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_FORMAT_ERROR = "MODEL_FORMAT_ERROR"
    GIT_CONFLICT = "GIT_CONFLICT"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureClassifier:
    def classify(self, command: str, stdout: str, stderr: str) -> FailureClass:
        text = f"{command}\n{stdout}\n{stderr}".lower()
        if "action denied by safety kernel" in text or "command_blocked_by_policy" in text:
            return FailureClass.COMMAND_BLOCKED_BY_POLICY
        if "modulenotfounderror" in text or "importerror" in text:
            return FailureClass.IMPORT_ERROR
        if "no module named" in text:
            return FailureClass.DEPENDENCY_MISSING
        if "mypy" in text or "incompatible types" in text or "has no attribute" in text:
            return FailureClass.TYPECHECK_FAILURE
        if "ruff" in text or "f401" in text or "e501" in text or "i001" in text:
            return FailureClass.LINT_FAILURE
        if "assertionerror" in text or "failed" in text and "pytest" in text:
            return FailureClass.TEST_ASSERTION_FAILURE
        if "syntaxerror" in text or "traceback" in text:
            return FailureClass.RUNTIME_EXCEPTION
        if "merge conflict" in text or "<<<<<<<" in text:
            return FailureClass.GIT_CONFLICT
        if "timed out" in text or "timeout" in text:
            return FailureClass.MODEL_TIMEOUT
        if "invalid json" in text or "schema validation" in text:
            return FailureClass.MODEL_FORMAT_ERROR
        if "build failed" in text or "npm err!" in text:
            return FailureClass.BUILD_FAILURE
        if "sandbox" in text and "failed" in text:
            return FailureClass.SANDBOX_FAILURE
        return FailureClass.UNKNOWN_FAILURE
