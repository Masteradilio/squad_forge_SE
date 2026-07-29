import hashlib
import re
from typing import Any

from localforge.models import domain
from localforge.models.enums import ProgressSignal


def normalize_error_message(raw_error: str) -> str:
    r"""Normalize raw error traces/messages into a stable, deterministic string.

    Strips out:
    - Hexadecimal memory addresses (e.g. 0x7f9a8c001230)
    - ISO timestamps & datetime strings
    - Absolute file paths (e.g. C:\Users\... or /tmp/...)
    - Volatile thread IDs and process IDs
    """

    if not raw_error:
        return "UnknownError"

    text = raw_error

    # Strip memory addresses: 0x10a9b8c...
    text = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", text)

    # Strip ISO timestamps: 2026-07-28T01:23:45.678901Z
    text = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "TIMESTAMP", text)

    # Strip Windows & Unix absolute file paths
    text = re.sub(r"[a-zA-Z]:\\[^\s:,\"\']+", "FILE_PATH", text)
    text = re.sub(r"/(?:[^\s:,\"\']+/)+[^\s:,\"\']*", "FILE_PATH", text)

    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def generate_error_fingerprint(
    error_type: str,
    raw_message: str,
    file_location: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> domain.FailureFingerprint:
    """Create a deterministic FailureFingerprint object and SHA-256 hash."""
    norm_msg = normalize_error_message(raw_message)

    clean_loc = normalize_error_message(file_location) if file_location else ""

    fingerprint_raw = f"type:{error_type}|loc:{clean_loc}|msg:{norm_msg}"
    fingerprint_hash = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()[:16]

    return domain.FailureFingerprint(
        error_type=error_type,
        normalized_message=norm_msg,
        fingerprint_hash=fingerprint_hash,
        file_location=clean_loc or None,
        metadata=metadata or {},
    )


def compute_test_signature(test_results: list[dict[str, Any]] | dict[str, Any] | str) -> str:
    """Hash test results into a stable signature.

    Takes passed/failed test names and statuses.
    """
    if isinstance(test_results, str):
        content = test_results
    else:
        content = str(
            sorted(test_results.items()) if isinstance(test_results, dict) else test_results
        )

    norm_content = normalize_error_message(content)
    return hashlib.sha256(norm_content.encode("utf-8")).hexdigest()[:16]


def compute_diff_signature(diff_content: str) -> str:
    """Hash unified diff patch content into a stable signature ignoring whitespace changes."""
    if not diff_content:
        return "EMPTY_DIFF"

    lines = [
        line.strip()
        for line in diff_content.splitlines()
        if line.strip() and not line.startswith("@@")
    ]
    normalized = "\n".join(lines)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def compute_artifact_signature(artifacts: list[dict[str, Any]] | str) -> str:
    """Hash produced artifact list/paths into a stable signature."""
    if isinstance(artifacts, str):
        content = artifacts
    else:
        content = str(artifacts)

    norm = normalize_error_message(content)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def evaluate_attempt_progress(
    previous_attempt: domain.AttemptProgressRecord | None,
    current_attempt_num: int,
    current_test_sig: str,
    current_diff_sig: str,
    current_artifact_sig: str,
    current_fingerprint_hash: str | None = None,
    failed_test_count: int = 0,
    previous_failed_test_count: int = 0,
) -> domain.AttemptProgressRecord:
    """Evaluate progress signal comparing previous and current attempt signatures.

    Signals:
    - REPEATED_FAILURE: exact same error fingerprint hash repeated
    - REGRESSION: number of failed tests increased
    - PROGRESS: failed tests decreased or diff/test signatures improved
    - STAGNATION: no change in test or diff signature
    """
    if not previous_attempt:
        signal = ProgressSignal.PROGRESS if failed_test_count == 0 else ProgressSignal.STAGNATION
    elif current_fingerprint_hash and previous_attempt.fingerprint_hash == current_fingerprint_hash:
        signal = ProgressSignal.REPEATED_FAILURE
    elif failed_test_count > previous_failed_test_count:
        signal = ProgressSignal.REGRESSION
    elif failed_test_count < previous_failed_test_count:
        signal = ProgressSignal.PROGRESS
    elif (
        current_test_sig == previous_attempt.test_signature
        and current_diff_sig == previous_attempt.diff_signature
    ):
        signal = ProgressSignal.STAGNATION
    else:
        signal = ProgressSignal.PROGRESS

    return domain.AttemptProgressRecord(
        attempt_number=current_attempt_num,
        test_signature=current_test_sig,
        diff_signature=current_diff_sig,
        artifact_signature=current_artifact_sig,
        signal=signal,
        fingerprint_hash=current_fingerprint_hash,
    )
