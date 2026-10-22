"""Reset a user's password from the server console.

There is no self-service reset: a password account has no verified mobile number
or email, so nothing online can prove that the caller owns the account. Until an
OTP or email channel is enabled, an operator resets the password after verifying
the person through the usual offline means (in person or by phone).

Usage:
    python -m app.scripts.reset_password 9876543210
    python -m app.scripts.reset_password 9876543210 --password 'new-secret'

The password is read with ``getpass`` unless ``--password`` is given. The flag
exists for automation; it can end up in shell history, so prefer the prompt.
Every reset signs the account out on all devices.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.schemas.validators import is_valid_mobile, normalise_mobile
from app.services.auth import revoke_all_for_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set a new password for an account (operator use)."
    )
    parser.add_argument("mobile", help="the account's 10-digit mobile number")
    parser.add_argument(
        "--password",
        help="new password (omit to be prompted; the prompt keeps it out of history)",
    )
    args = parser.parse_args(argv)

    mobile = normalise_mobile(args.mobile)
    if not is_valid_mobile(mobile):
        print("That is not a valid Indian mobile number.", file=sys.stderr)
        return 2

    password = args.password
    if password is None:
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Repeat the new password: "):
            print("The passwords do not match. Nothing changed.", file=sys.stderr)
            return 2

    minimum = get_settings().password_min_length
    if len(password) < minimum:
        print(f"Use at least {minimum} characters.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.mobile == mobile))
        if user is None:
            print("No account uses that mobile number.", file=sys.stderr)
            return 1
        if user.deleted_at is not None:
            print("That account has been deleted.", file=sys.stderr)
            return 1

        user.password_hash = hash_password(password)
        revoke_all_for_user(db, user.id)
        db.commit()
        print(f"Password reset for user {user.id}. Every session was signed out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
