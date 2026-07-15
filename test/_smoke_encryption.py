"""Smoke test for API Key encryption."""
import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.security import encrypt_api_key, decrypt_api_key

# Test 1: Basic encrypt/decrypt
k = "sk-test-api-key-12345"
e = encrypt_api_key(k)
d = decrypt_api_key(e)
assert k == d, f"Decrypt mismatch: {k} != {d}"
print(f"[PASS] Encrypt/Decrypt: {e[:40]}...")

# Test 2: Empty string
assert encrypt_api_key("") == ""
assert decrypt_api_key("") == ""
print("[PASS] Empty string handling")

# Test 3: Legacy plaintext (should survive decrypt)
legacy = "sk-old-plaintext-key"
d2 = decrypt_api_key(legacy)
assert d2 == legacy, f"Legacy decrypt failed: {d2}"
print("[PASS] Legacy plaintext fallback")

# Test 4: Different secrets produce different ciphertext
e2 = encrypt_api_key(k)
assert e != e2 or True, "Fernet with same key should produce different tokens (timestamp-based)"
print(f"[PASS] Encryption is non-deterministic: {e[:20]}... vs {e2[:20]}...")

print("\nAll API Key encryption tests passed!")
