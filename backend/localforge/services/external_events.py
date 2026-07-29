import hashlib
import hmac
import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

_SAFE_PROVIDER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PROMPT_INJECTION_RE = re.compile(
    r"(?i)\b(system override|ignore previous instructions|elevate autonomy|developer message)\b"
)


@dataclass(frozen=True)
class ExternalEventEnvelope:
    provider: str
    event_id: str
    timestamp: datetime
    payload: dict[str, Any]
    idempotency_key: str


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sanitize_untrusted_payload(value: Any, *, max_string_length: int = 1024) -> Any:
    """Recursively normalize provider data before it reaches triage/model context."""
    if isinstance(value, str):
        scrubbed = _CONTROL_CHARS_RE.sub("", value)
        scrubbed = _PROMPT_INJECTION_RE.sub("[removed external instruction]", scrubbed)
        return html.escape(scrubbed[:max_string_length], quote=False)
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    if isinstance(value, list):
        return [sanitize_untrusted_payload(item, max_string_length=max_string_length) for item in value[:50]]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            clean_key = str(sanitize_untrusted_payload(str(key), max_string_length=128))
            clean[clean_key] = sanitize_untrusted_payload(
                item,
                max_string_length=max_string_length,
            )
        return clean
    return html.escape(str(value)[:max_string_length], quote=False)


def validate_external_event_envelope(
    *,
    loop_id: int,
    provider: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    safety_policy: dict[str, Any],
    now: datetime | None = None,
) -> ExternalEventEnvelope:
    if not _SAFE_PROVIDER_RE.fullmatch(provider):
        raise ValueError("External trigger provider must be a safe stable identifier.")

    provider_policy = _provider_policy(safety_policy, provider)
    secret = str(provider_policy.get("secret") or "")
    auth_token = str(provider_policy.get("auth_token") or "")
    if not secret and not auth_token:
        raise ValueError("External trigger requires a configured secret or auth token.")

    normalized_headers = {key.lower(): value for key, value in headers.items()}
    event_id = normalized_headers.get("x-localforge-event-id", "").strip()
    if not event_id or len(event_id) > 128:
        raise ValueError("External trigger requires a stable provider event id.")

    event_time = _parse_event_timestamp(normalized_headers.get("x-localforge-timestamp"))
    current_time = now or datetime.now(UTC)
    replay_window = int(provider_policy.get("replay_window_seconds") or 300)
    if abs((current_time - event_time).total_seconds()) > replay_window:
        raise ValueError("External trigger timestamp is outside the replay window.")

    max_payload_bytes = int(provider_policy.get("max_payload_bytes") or 8192)
    if len(canonical_payload_bytes(payload)) > max_payload_bytes:
        raise ValueError("External trigger payload exceeds the configured size limit.")

    if auth_token:
        token = normalized_headers.get("authorization", "")
        if not hmac.compare_digest(token, f"Bearer {auth_token}"):
            raise ValueError("External trigger bearer credential is invalid.")
    if secret:
        signature = normalized_headers.get("x-localforge-signature", "")
        expected = sign_external_event(
            secret=secret,
            timestamp=event_time,
            payload=payload,
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("External trigger signature is invalid.")

    clean_payload = sanitize_untrusted_payload(payload)
    if not isinstance(clean_payload, dict):
        clean_payload = {"value": clean_payload}
    clean_payload["_external_trigger_verified"] = True
    clean_payload["_external_provider"] = provider
    clean_payload["_external_event_id"] = event_id

    return ExternalEventEnvelope(
        provider=provider,
        event_id=event_id,
        timestamp=event_time,
        payload=clean_payload,
        idempotency_key=f"external:{loop_id}:{provider}:{event_id}",
    )


def sign_external_event(*, secret: str, timestamp: datetime, payload: dict[str, Any]) -> str:
    signed = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z").encode("utf-8")
    signed += b"."
    signed += canonical_payload_bytes(payload)
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _provider_policy(safety_policy: dict[str, Any], provider: str) -> dict[str, Any]:
    external = safety_policy.get("external_triggers")
    if isinstance(external, dict):
        provider_policy = external.get(provider)
        if isinstance(provider_policy, dict):
            return provider_policy
    return safety_policy


def _parse_event_timestamp(raw: str | None) -> datetime:
    if not raw:
        raise ValueError("External trigger requires a timestamp.")
    try:
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw), tz=UTC)
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise ValueError("External trigger timestamp is invalid.") from exc


def window_start(now: datetime | None, seconds: int) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(seconds=seconds)
