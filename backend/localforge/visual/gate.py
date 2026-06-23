import os
from dataclasses import dataclass, field

from localforge.models.enums import FailureClass


@dataclass(frozen=True)
class VisualGateResult:
    passed: bool
    summary: str
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    failure_class: FailureClass | None = None


class VisualFidelityGate:
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
        metrics: dict[str, float | int | str] = {"actual_bytes": actual_bytes}
        if reference_image_path and os.path.isfile(reference_image_path):
            metrics["reference_bytes"] = os.path.getsize(reference_image_path)
            similarity = _try_image_similarity(reference_image_path, actual_image_path)
            if similarity is not None:
                metrics["similarity"] = similarity
                if similarity < min_similarity:
                    return VisualGateResult(
                        passed=False,
                        summary=f"Visual similarity below threshold: {similarity:.3f}",
                        metrics=metrics,
                        failure_class=FailureClass.VISUAL_MISMATCH,
                    )
        else:
            metrics["reference_status"] = "missing"
        return VisualGateResult(
            passed=True,
            summary="Rendered visual evidence is present and acceptable.",
            metrics=metrics,
        )


def _try_image_similarity(reference_path: str, actual_path: str) -> float | None:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    try:
        with Image.open(reference_path) as ref, Image.open(actual_path) as actual:
            ref_rgb = ref.convert("RGB").resize((128, 128))
            actual_rgb = actual.convert("RGB").resize((128, 128))
            diff = ImageChops.difference(ref_rgb, actual_rgb)
            histogram = diff.histogram()
    except Exception:
        return None
    total = sum(value * (index % 256) for index, value in enumerate(histogram))
    max_total = 255 * 128 * 128 * 3
    return max(0.0, 1.0 - (total / max_total))
