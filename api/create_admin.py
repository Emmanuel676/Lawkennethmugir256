"""Create an Admin account from PowerShell (Phase 12B). Use it for the first Admin; Admins add everyone else.

    .\\.venv\\Scripts\\python.exe -m api.create_admin
    .\\.venv\\Scripts\\python.exe -m api.create_admin --email admin@example.org

It asks for the email (unless given) and then for the password TWICE AT A HIDDEN PROMPT (getpass). The password is
never accepted as a command argument, never read from a file or an environment variable, and never printed,
logged or written anywhere: only its argon2 hash is stored, in <FAIRLEND_WEB_DATA>/app.db, or in the hosted
Postgres database when DATABASE_URL is set in this window (see docs/DEPLOY_FREE.md).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from api.accounts import AccountError, AccountStore
from api.appdb import DatabaseUnavailable, open_database
from api.security import load_secret
from api.settings import load_settings


def main(argv: list[str] | None = None, prompt=getpass.getpass, ask=input) -> int:
    parser = argparse.ArgumentParser(description="Create an Admin account. The password is asked at a hidden prompt.")
    parser.add_argument("--email", help="the Admin's email address (asked if left out)")
    args = parser.parse_args(argv)

    settings = load_settings()
    store = AccountStore(open_database(settings),
                         lambda: load_secret(settings.session_secret, settings.data_dir),
                         session_hours=settings.session_hours, max_attempts=settings.max_login_attempts,
                         lockout_minutes=settings.lockout_minutes,
                         password_min_length=settings.password_min_length)
    email = (args.email or ask("Admin email: ")).strip()
    print(f"Choose a password of at least {settings.password_min_length} characters. It is not shown as you type.")
    for attempt in range(3):
        first = prompt("Password: ")
        second = prompt("Password again: ")
        if first != second:
            print("The two passwords are different. Try again.")
            continue
        try:
            user = store.create_user(email, "admin", first, created_by="create_admin script")
        except DatabaseUnavailable as error:
            print(str(error))
            return 1
        except AccountError as error:
            print(str(error))
            if "already exists" in str(error) or "email" in str(error).lower():
                return 1
            continue
        finally:
            first = second = ""  # noqa: F841 - drop the references as soon as possible
        print(f"Admin account created for {user.email}. Sign in at the web app's Sign in page.")
        print("Stored in the hosted database (DATABASE_URL)." if settings.database_url
              else f"Users and sessions are stored in {settings.data_dir} (git-ignored).")
        return 0
    print("No account was created.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
