"""目录和样例清单。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_app"
DATA = ROOT / "data"
RECORDS = ROOT / "records"
SEEKDB_DIR = DATA / "seekdb"
POWERCONTEXT_DB = DATA / "powercontext.db"
MANIFEST_PATH = SAMPLE / "manifest.json"
SPEC_PATH = SAMPLE / "spec.md"
TASKS_PATH = SAMPLE / "tasks.py"
BEFORE_TASKS = ROOT / "snapshots" / "before" / "tasks.py"

SPEC_TOKEN = "SPEC_TOKEN_ALPHA"
UPDATED_SPEC_TOKEN = "SPEC_TOKEN_BETA"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def task_text() -> str:
    return str(load_manifest()["task"])
