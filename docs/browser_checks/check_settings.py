"""Settings for the browser checks: the normal settings on a throwaway database.

run.js sets BROWSER_CHECKS_DB to a file in a temporary folder, so the checks
never touch db.sqlite3.
"""
import os

from config.settings import *  # noqa: F401,F403
from config.settings import DATABASES

DATABASES["default"]["NAME"] = os.environ["BROWSER_CHECKS_DB"]
