"""Invite codes that are bound to the inviter who owns them.

``ReferralEvaluationRequest`` has always carried an ``invite_code``, and
nothing ever read it. The referral was attributed purely on the
``inviter_user_id`` the caller supplied alongside it, so any client could
claim any inviter by sending an arbitrary six-character string, and the
"precision-first" antifraud in ``app.fraud`` would see nothing wrong: the
device and payment signals it checks are about self-referral, not about
whether the code belongs to the person named.

A code is therefore derived from the inviter's id rather than stored:
``HMAC(secret, user_id)``, truncated to something a person can read out. That
keeps the whole thing stateless -- there is no registry to seed, migrate or
keep in sync with ``InMemoryStateRepository`` -- while making the code
unforgeable without the secret.

Scope, stated plainly: the secret defaults to a constant, because this is a
PoC with no authentication at all (``docs/technical-design.md`` §3 lists
production auth as a non-goal). With the default secret anyone reading this
file can mint a valid code. That is a smaller hole than the one it replaces --
"any string works" -- and it closes properly by setting ``REFERRAL_CODE_SECRET``
in the environment. It is not a substitute for authenticating the caller.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256

#: Overridable so a deployment can have codes that cannot be minted from a
#: reading of this source. See the module docstring on what the default does
#: and does not buy.
DEFAULT_SECRET = "x5-domovoi-poc-referral"

#: Length of the visible code. Eight base32-ish characters is 40 bits, which
#: is far past guessing at any plausible referral volume, and short enough to
#: read aloud or type from a screenshot.
CODE_LENGTH = 8

#: Digits and uppercase letters minus the pairs people mistype between
#: (0/O, 1/I/L) — a code exists to be retyped by a person.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _secret() -> bytes:
    return os.environ.get("REFERRAL_CODE_SECRET", DEFAULT_SECRET).encode("utf-8")


def generate_invite_code(user_id: str) -> str:
    """The one code that belongs to ``user_id``."""
    digest = hmac.new(_secret(), user_id.encode("utf-8"), sha256).digest()
    return "".join(_ALPHABET[byte % len(_ALPHABET)] for byte in digest[:CODE_LENGTH])


def verify_invite_code(code: str, inviter_user_id: str) -> bool:
    """Whether ``code`` is the code issued to ``inviter_user_id``.

    Compared with ``hmac.compare_digest`` rather than ``==``: the comparison is
    cheap to make constant-time and there is no reason to leak a prefix through
    timing.
    """
    expected = generate_invite_code(inviter_user_id)
    return hmac.compare_digest(code.strip().upper(), expected)
