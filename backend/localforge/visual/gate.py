import os
import re
from dataclasses import dataclass, field
from typing import cast

from localforge.models.enums import FailureClass


@dataclass(frozen=True)
class VisualGateResult:
    passed: bool
    summary: str
    metrics: dict[str, object] = field(default_factory=dict)
    failure_class: FailureClass | None = None


class VisualFidelityGate:
    """Evaluates visual fidelity of a rendered output against a reference image.

    NOTE: The RGB histogram metric acts as a structural baseline check to detect
    major layout, spacing, and color differences. It does not perform micro-layout
    OCR or label parsing, and should be combined with layout checks where possible.
    """

    def evaluate(
        self,
        *,
        reference_image_path: str | None,
        actual_image_path: str | None,
        task_is_visual: bool,
        min_similarity: float = 0.90,
    ) -> VisualGateResult:
        if not task_is_visual:
            return VisualGateResult(
                passed=True,
                summary="Task is not visual; visual gate skipped.",
            )
        if not actual_image_path or not os.path.isfile(actual_image_path):
            return VisualGateResult(
                passed=False,
                summary="Rendered visual evidence is missing.",
                failure_class=FailureClass.VISUAL_MISMATCH,
            )
        actual_bytes = os.path.getsize(actual_image_path)
        if actual_bytes <= 0:
            return VisualGateResult(
                passed=False,
                summary="Rendered visual evidence is empty.",
                metrics={"actual_bytes": actual_bytes},
                failure_class=FailureClass.VISUAL_MISMATCH,
            )

        metrics: dict[str, object] = {"actual_bytes": actual_bytes}

        if reference_image_path and os.path.isfile(reference_image_path):
            metrics["reference_bytes"] = os.path.getsize(reference_image_path)

            # 1. Verify aspect ratio
            aspect_diff = _verify_aspect_ratio(reference_image_path, actual_image_path, metrics)
            if aspect_diff is not None and aspect_diff > 0.15:
                return VisualGateResult(
                    passed=False,
                    summary=f"Visual aspect ratio mismatch. Difference is {aspect_diff:.2%}",
                    metrics=metrics,
                    failure_class=FailureClass.VISUAL_MISMATCH,
                )

            # 2. Verify perceptual similarity. A small blur makes the metric
            # tolerant of photographic texture and browser antialiasing while
            # the opt-in HTML structure rules keep geometry explicit.
            raw_similarity = _try_image_similarity(
                reference_image_path, actual_image_path, sample_size=128
            )
            similarity = _try_image_similarity(
                reference_image_path,
                actual_image_path,
                sample_size=64,
                blur_radius=4.0,
            )
            if similarity is not None:
                metrics["raw_similarity"] = raw_similarity
                metrics["similarity"] = similarity
                metrics["perceptual_sample_size"] = 64
                metrics["perceptual_blur_radius"] = 4.0
                metrics.update(_visual_distribution_metrics(reference_image_path, actual_image_path))
                if similarity < min_similarity:
                    return VisualGateResult(
                        passed=False,
                        summary=(
                            f"Visual similarity below threshold: {similarity:.3f} "
                            f"(raw {raw_similarity:.3f} ; required: {min_similarity:.2f})"
                        ),
                        metrics=metrics,
                        failure_class=FailureClass.VISUAL_MISMATCH,
                    )
            elif task_is_visual:
                metrics["similarity_status"] = "unavailable"
                return VisualGateResult(
                    passed=False,
                    summary="Visual similarity could not be calculated.",
                    metrics=metrics,
                    failure_class=FailureClass.VISUAL_MISMATCH,
                )
        else:
            metrics["reference_status"] = "missing"
            if task_is_visual:
                return VisualGateResult(
                    passed=False,
                    summary="Visual reference image is missing.",
                    metrics=metrics,
                    failure_class=FailureClass.VISUAL_MISMATCH,
                )

        return VisualGateResult(
            passed=True,
            summary="Rendered visual evidence is present and acceptable.",
            metrics=metrics,
        )


def validate_visual_html_structure(
    html_path: str, *, structure_rules: list[str] | None
) -> list[str]:
    """Return deterministic structural findings before an expensive screenshot."""
    if not structure_rules or not os.path.isfile(html_path):
        return []
    try:
        with open(html_path, encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeError) as exc:
        return [f"Could not inspect visual HTML structure: {exc}"]

    findings: list[str] = []
    normalized = re.sub(r"\s+", " ", content.lower())
    if "single_parent_keypad_grid" in structure_rules:
        has_parent_grid = "key-grid" in normalized or "keypad-grid" in normalized
        nested_row_grids = len(re.findall(r"key-row", normalized)) >= 2
        if nested_row_grids and not has_parent_grid:
            findings.append(
                "Keypad uses multiple nested row grids; use one parent keypad grid "
                "with direct child keys so spanning keys can cross rows."
            )
        if not re.search(r"grid-template-columns\s*:\s*repeat\(\s*10\b", normalized):
            findings.append("Keypad parent grid must declare ten columns.")
        if not re.search(r"grid-template-rows\s*:\s*repeat\(\s*4\b", normalized):
            findings.append("Keypad parent grid must declare four rows.")
    if "spanning_enter_key" in structure_rules:
        enter_block = re.search(
            r"\.[a-z0-9_-]*enter[a-z0-9_-]*\s*\{(?P<body>[^}]*)\}",
            normalized,
        )
        body = enter_block.group("body") if enter_block else ""
        if not re.search(r"grid-column\s*:\s*6\b", body):
            findings.append("Spanning ENTER key must explicitly use grid-column: 6.")
        if not re.search(r"grid-row\s*:\s*3\s*/\s*5\b", body):
            findings.append("Spanning ENTER key must explicitly use grid-row: 3 / 5.")
    if "full_frame_physical_body" in structure_rules:
        restrictive_widths = [
            int(value)
            for value in re.findall(r"max-width\s*:\s*(\d+)px", normalized)
            if value.isdigit()
        ]
        has_contract_override = bool(
            re.search(r"max-width\s*:\s*none\b", normalized)
        )
        if any(value < 1100 for value in restrictive_widths) and not has_contract_override:
            findings.append(
                "Calculator body must fill the 1280px capture; remove restrictive "
                "max-width values below 1100px."
            )
    if "lcd_left_aligned" in structure_rules:
        lcd_blocks = [
            match.group("body")
            for match in re.finditer(
                r"\.(?:lcd-container|lcd-area|lcd-wrap)\s*\{(?P<body>[^}]*)\}",
                normalized,
            )
        ]
        has_centered_lcd = any(
            re.search(r"justify-content\s*:\s*center\b", body) for body in lcd_blocks
        )
        has_left_override = any(
            re.search(r"margin-left\s*:\s*(?:[1-9]|[1-9]\d)%", body)
            or re.search(r"justify-content\s*:\s*flex-start\b", body)
            for body in lcd_blocks
        )
        if has_centered_lcd and not has_left_override:
            findings.append(
                "LCD container must be left-aligned after the model label, not centered."
            )
    if "rectangular_hp_badge" in structure_rules:
        badge_blocks = [
            match.group("body")
            for match in re.finditer(r"\.hp-badge\s*\{(?P<body>[^}]*)\}", normalized)
        ]
        has_round_badge = any(
            re.search(r"border-radius\s*:\s*50%", body) for body in badge_blocks
        )
        has_rectangular_override = any(
            re.search(r"border-radius\s*:\s*(?:[0-9]+(?:\.[0-9]+)?px|0)", body)
            for body in badge_blocks
        )
        if has_round_badge and not has_rectangular_override:
            findings.append(
                "HP badge must be a small rectangular reference badge, not a circular badge."
            )
    return findings


def _verify_aspect_ratio(
    ref_path: str, actual_path: str, metrics: dict[str, object]
) -> float | None:
    try:
        from PIL import Image

        with Image.open(ref_path) as ref, Image.open(actual_path) as actual:
            ref_w, ref_h = ref.size
            act_w, act_h = actual.size
            ref_ratio = ref_w / ref_h
            act_ratio = act_w / act_h
            metrics["ref_dimensions"] = f"{ref_w}x{ref_h}"
            metrics["actual_dimensions"] = f"{act_w}x{act_h}"
            metrics["ref_aspect_ratio"] = round(ref_ratio, 3)
            metrics["actual_aspect_ratio"] = round(act_ratio, 3)
            return abs(ref_ratio - act_ratio) / ref_ratio
    except Exception:
        return None


def _try_image_similarity(
    reference_path: str,
    actual_path: str,
    *,
    sample_size: int = 128,
    blur_radius: float = 0.0,
) -> float | None:
    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError:
        return None
    try:
        with Image.open(reference_path) as ref, Image.open(actual_path) as actual:
            ref_rgb = ref.convert("RGB").resize((sample_size, sample_size))
            actual_rgb = actual.convert("RGB").resize((sample_size, sample_size))
            if blur_radius > 0:
                ref_rgb = ref_rgb.filter(ImageFilter.GaussianBlur(blur_radius))
                actual_rgb = actual_rgb.filter(ImageFilter.GaussianBlur(blur_radius))
            diff = ImageChops.difference(ref_rgb, actual_rgb)
            histogram = diff.histogram()
    except Exception:
        return None
    total = sum(value * (index % 256) for index, value in enumerate(histogram))
    max_total = 255 * sample_size * sample_size * 3
    return max(0.0, 1.0 - (total / max_total))


def _visual_distribution_metrics(reference_path: str, actual_path: str) -> dict[str, object]:
    """Expose compact color-distribution evidence to the repair agent."""
    try:
        from PIL import Image

        result: dict[str, object] = {}
        for label, path in (("reference", reference_path), ("actual", actual_path)):
            with Image.open(path) as image:
                sampled = image.convert("RGB").resize((128, 128))
                pixels: list[tuple[int, int, int]] = []
                for y in range(128):
                    for x in range(128):
                        pixels.append(cast(tuple[int, int, int], sampled.getpixel((x, y))))
                sampled.close()
            count = len(pixels)
            mean = tuple(round(sum(pixel[index] for pixel in pixels) / count, 1) for index in range(3))
            result[f"{label}_mean_rgb"] = mean
            result[f"{label}_dark_pixel_ratio"] = round(
                sum(1 for pixel in pixels if sum(pixel) / 3 < 60) / count, 3
            )
            result[f"{label}_light_pixel_ratio"] = round(
                sum(1 for pixel in pixels if sum(pixel) / 3 > 180) / count, 3
            )
        return result
    except Exception:
        return {}
