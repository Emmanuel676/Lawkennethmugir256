"""Browser-test setup only: create viewer@, importer@ and admin@example.org in the throwaway e2e data folder.

The password comes from the E2E_PASSWORD environment variable of this one test run (random per run, never on a
command line, never written to a file). The folder comes from FAIRLEND_WEB_DATA, which the test config points at a
new temporary folder: this never touches data\\web.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.accounts import AccountStore  # noqa: E402
from api.appdb import AppDatabase  # noqa: E402
from api.security import load_secret  # noqa: E402
from api.settings import load_settings  # noqa: E402

settings = load_settings()
if "fairlend-e2e-" not in str(settings.data_dir):
    sys.exit("Refusing to seed test users outside a fairlend-e2e- temporary folder.")
store = AccountStore(AppDatabase(settings.data_dir / "app.db"),
                     lambda: load_secret(settings.session_secret, settings.data_dir), session_hours=8,
                     max_attempts=5, lockout_minutes=10, password_min_length=10)
for role in ("viewer", "importer", "admin"):
    store.create_user(f"{role}@example.org", role, os.environ["E2E_PASSWORD"], created_by="browser tests")
print("browser-test users created")
