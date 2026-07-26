"""Shared test credentials — override via environment, no secrets inline in test files."""
import os

OWNER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "HaulYeahAdmin")
OWNER_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "HaulYeah2026!")
GHOST_PASSWORD = os.environ.get("TEST_GHOST_PASSWORD", OWNER_PASSWORD)
JAVANTE_EMAIL = os.environ.get("TEST_JAVANTE_EMAIL", "javante@haulyeahmoves.com")
JAVANTE_PASSWORD = os.environ.get("TEST_JAVANTE_PASSWORD", "JavCrew2026!")
JUNIOR_EMAIL = os.environ.get("TEST_JUNIOR_EMAIL", "junior@haulyeahmoves.com")
JUNIOR_PASSWORD = os.environ.get("TEST_JUNIOR_PASSWORD", "JunCrew2026!")
STARTING_PASSWORD = os.environ.get("TEST_STARTING_PASSWORD", "haulyeah123")
