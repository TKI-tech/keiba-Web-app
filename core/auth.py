"""パスワードのハッシュ化・検証。

外部ライブラリを増やさないため標準ライブラリのみで実装している(PBKDF2-HMAC-SHA256、
ユーザーごとのランダムなsalt、OWASP推奨に沿った十分な反復回数)。平文パスワードは
一切保存しない。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "sha256"
_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hex_digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), hex_digest)
