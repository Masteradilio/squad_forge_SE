from __future__ import annotations

import os

_OVERRIDE_MARKER = 'id="localforge-visual-contract-overrides"'


def apply_visual_contract_normalization(
    html_path: str, *, structure_rules: list[str]
) -> bool:
    """Apply only deterministic layout overrides explicitly required by a contract."""
    if not structure_rules or not os.path.isfile(html_path):
        return False
    overrides: list[str] = []
    if "full_frame_physical_body" in structure_rules:
        overrides.append(
            "html, body { width: 100%; min-width: 1100px; }"
            ".calculator, .calculator-body, .calculator-container, "
            ".calculator-wrapper, .calculator-shell {"
            "width: calc(100vw - 40px) !important; "
            "max-width: none !important; margin-left: 20px !important; "
            "margin-right: 20px !important; }"
        )
    if "lcd_left_aligned" in structure_rules:
        overrides.append(
            ".lcd-container, .lcd-area, .lcd-wrap {"
            "justify-content: flex-start !important; margin-left: 1% !important; }"
        )
    if "rectangular_brand_badge" in structure_rules:
        overrides.append(".brand-badge { border-radius: 6px !important; }")
    if not overrides:
        return False
    try:
        with open(html_path, encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeError):
        return False
    if _OVERRIDE_MARKER in content:
        return False
    style = (
        f'<style {_OVERRIDE_MARKER}>\n'
        "/* Deterministic, contract-scoped visual corrections. */\n"
        + "\n".join(overrides)
        + "\n</style>\n"
    )
    marker = "</head>"
    updated = content.replace(marker, style + marker, 1)
    if updated == content:
        updated = content + "\n" + style
    try:
        with open(html_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
    except OSError:
        return False
    return True
