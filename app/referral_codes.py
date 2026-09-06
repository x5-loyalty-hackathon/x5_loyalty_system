"""Deterministic inviter-bound codes for the PoC (source: ML fix 70f3af5).

The default secret is public so synthetic demos can issue reproducible codes.
Set REFERRAL_CODE_SECRET to use a private secret; changing it invalidates old
codes. This checks code ownership and does not authenticate the caller. No
code registry, production authentication, or HTTP issuance endpoint is added.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256


DEFAULT_SECRET = "x5-domovoi-poc-referral"
CODE_LENGTH = 8
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def issue_invite_code(user_id: str) -> str:
    """Return the code for this inviter using the server's configured secret."""
    secret = os.environ.get("REFERRAL_CODE_SECRET", DEFAULT_SECRET).encode("utf-8")
    digest = hmac.new(secret, user_id.encode("utf-8"), sha256).digest()
    return "".join(_ALPHABET[byte % len(_ALPHABET)] for byte in digest[:CODE_LENGTH])


# Preserve the helper name used by the source ML branch and its examples.
generate_invite_code = issue_invite_code


def verify_invite_code(code: str, inviter_user_id: str) -> bool:
    """Match a human-entered code without raising on non-ASCII API input."""
    normalized = code.strip().upper()
    if len(normalized) != CODE_LENGTH or any(
        character not in _ALPHABET for character in normalized
    ):
        return False
    return hmac.compare_digest(normalized, issue_invite_code(inviter_user_id))
