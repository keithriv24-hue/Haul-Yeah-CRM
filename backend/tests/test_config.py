"""Shared test credentials — all values come from tests/.env.test (gitignored).
Copy tests/env.test.example to tests/.env.test and fill in real values.
No secrets are stored inline in test code."""
import os
from pathlib import Path

from dotenv import load_dotenv

_TESTS_DIR = Path(__file__).resolve().parent
load_dotenv(_TESTS_DIR / ".env.test")
load_dotenv(_TESTS_DIR.parent / ".env")  # backend env (SALES_PASSWORD fallback)


def _require(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        raise RuntimeError(
            f"Missing test credential {key}: copy backend/tests/env.test.example "
            "to backend/tests/.env.test and fill in real values.")
    return val


OWNER_EMAIL = _require("TEST_OWNER_EMAIL")
OWNER_PASSWORD = _require("TEST_OWNER_PASSWORD")
GHOST_PASSWORD = os.environ.get("TEST_GHOST_PASSWORD") or OWNER_PASSWORD
CREW1_EMAIL = _require("TEST_CREW1_EMAIL")
CREW1_PASSWORD = _require("TEST_CREW1_PASSWORD")
CREW2_EMAIL = _require("TEST_CREW2_EMAIL")
CREW2_PASSWORD = _require("TEST_CREW2_PASSWORD")
CREW2_INITIAL_PASSWORD = os.environ.get("TEST_CREW2_INITIAL_PASSWORD") or CREW2_PASSWORD
STARTING_PASSWORD = _require("TEST_STARTING_PASSWORD")
# legacy shared role passwords — default to the backend's own env values
SALES_LEGACY_PASSWORD = os.environ.get("TEST_SALES_LEGACY_PASSWORD") or _require("SALES_PASSWORD")
EMPLOYEE_LEGACY_PASSWORD = os.environ.get("TEST_EMPLOYEE_LEGACY_PASSWORD") or _require("EMPLOYEE_PASSWORD")
QA_TRACK_TOKEN = _require("QA_TRACK_TOKEN")
