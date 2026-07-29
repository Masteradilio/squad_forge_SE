"""Cross-platform file checksum helpers."""

import hashlib
from pathlib import Path


def stable_file_sha256(path: Path) -> str:
    """Hash file content with platform-stable line endings for UTF-8 text."""
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(content).hexdigest()
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()
