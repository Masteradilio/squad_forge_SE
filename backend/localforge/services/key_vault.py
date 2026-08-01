"""Multi-Tenant Key Vault — AES-256-GCM Encrypted Key Storage for BYOK Pro Keys."""

import base64
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyVaultService:
    """Service to encrypt, decrypt, and manage user BYOK keys per tenant_id using AES-256-GCM."""

    def __init__(self, master_secret: Optional[str] = None):
        secret = master_secret or os.getenv("KEY_VAULT_SECRET", "forgeos_master_key_vault_secret_32b")
        # Ensure 256-bit (32 bytes) key
        raw_bytes = secret.encode("utf-8")
        if len(raw_bytes) < 32:
            raw_bytes = raw_bytes.ljust(32, b"0")
        else:
            raw_bytes = raw_bytes[:32]
        self.aesgcm = AESGCM(raw_bytes)

    def encrypt_key(self, tenant_id: str, provider_key: str) -> str:
        """Encrypt provider API key with tenant_id salt using AES-256-GCM."""
        nonce = os.urandom(12)
        aad = tenant_id.encode("utf-8")
        ciphertext = self.aesgcm.encrypt(nonce, provider_key.encode("utf-8"), aad)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("utf-8")

    def decrypt_key(self, tenant_id: str, encrypted_b64: str) -> str:
        """Decrypt provider API key with tenant_id salt using AES-256-GCM."""
        combined = base64.b64decode(encrypted_b64.encode("utf-8"))
        nonce = combined[:12]
        ciphertext = combined[12:]
        aad = tenant_id.encode("utf-8")
        decrypted_bytes = self.aesgcm.decrypt(nonce, ciphertext, aad)
        return decrypted_bytes.decode("utf-8")
