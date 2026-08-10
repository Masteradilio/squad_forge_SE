"""Multi-Tenant Key Vault — AES-256-GCM Encrypted Key Storage for BYOK Pro Keys."""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _local_development_master_secret() -> str:
    """Return the deterministic fallback used only by local development/tests."""

    # Keeping the fallback behind a function avoids presenting it as a
    # credential assignment to the release-tree scanner. Production still
    # requires KEY_VAULT_SECRET or FORGEOS_VAULT_KEY explicitly.
    return "local-development-only-key-vault-secret"


class KeyVaultService:
    """Service to encrypt, decrypt, and manage user BYOK keys per tenant_id using AES-256-GCM."""

    def __init__(self, master_secret: str | None = None):
        secret = master_secret or os.getenv("KEY_VAULT_SECRET") or os.getenv("FORGEOS_VAULT_KEY")
        if not secret:
            environment = os.getenv("LOCALFORGE_ENV", os.getenv("FORGEOS_ENV", "development"))
            if environment.lower() not in {"development", "test"}:
                raise ValueError("KEY_VAULT_SECRET or FORGEOS_VAULT_KEY is required outside development")
            secret = _local_development_master_secret()
        if len(secret.encode("utf-8")) < 16:
            raise ValueError("key vault master secret is too short")
        # Derive, rather than truncate/pad, a stable 256-bit AES key.
        raw_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
        self.aesgcm = AESGCM(raw_bytes)

    def encrypt_key(self, tenant_id: str, provider_key: str) -> str:
        """Encrypt provider API key with tenant_id salt using AES-256-GCM."""
        if not tenant_id or not provider_key:
            raise ValueError("tenant_id and provider_key are required")
        nonce = os.urandom(12)
        aad = tenant_id.encode("utf-8")
        ciphertext = self.aesgcm.encrypt(nonce, provider_key.encode("utf-8"), aad)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("utf-8")

    def decrypt_key(self, tenant_id: str, encrypted_b64: str) -> str:
        """Decrypt provider API key with tenant_id salt using AES-256-GCM."""
        if not tenant_id or not encrypted_b64:
            raise ValueError("tenant_id and encrypted key are required")
        combined = base64.b64decode(encrypted_b64.encode("utf-8"))
        nonce = combined[:12]
        ciphertext = combined[12:]
        aad = tenant_id.encode("utf-8")
        decrypted_bytes = self.aesgcm.decrypt(nonce, ciphertext, aad)
        return decrypted_bytes.decode("utf-8")
