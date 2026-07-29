"""Canonical product version metadata.

Keep this module import-light: it is used by package, CLI, API, and evidence
checks and must not depend on service/storage modules.
"""

VERSION = "6.2.0"
RELEASE_TAG = f"v{VERSION}"
RELEASE_STATUS = "remediation-in-progress"
