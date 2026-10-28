"""把规格、代码和测试放进嵌入式 seekdb，再查出来。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pylibseekdb as seekdb

from minimax.paths import RECORDS, ROOT, SEEKDB_DIR, load_manifest

_CREATE_SQL = """
CREATE TABLE engineering_material (
    material_id VARCHAR(64) PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    path VARCHAR(512) NOT NULL,
    symbol VARCHAR(128) NOT NULL,
    body LONGTEXT NOT NULL,
    FULLTEXT INDEX ft_material (body, path, symbol) WITH PARSER ik
)
"""


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _match_text(value: str) -> str:
    kept = []
    for char in value:
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            kept.append(char)
    return "".join(kept)[:200]


class Catalog:
    """一次打开、用完就关掉的 seekdb。"""

    def __init__(self, directory: Path = SEEKDB_DIR) -> None:
        self.directory = directory
        self._instance: Any = None
        self._connection: Any = None
        self._cursor: Any = None

    def __enter__(self) -> Catalog:
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        self._instance = seekdb.open(str(self.directory))
        self._connection = self._instance.connect("test", autocommit=True)
        self._cursor = self._connection.cursor()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._connection is not None:
            self._connection.close()
        if self._instance is not None:
            self._instance.close()

    def import_materials(self) -> list[dict[str, str]]:
        manifest = load_manifest()
        self._cursor.execute("DROP TABLE IF EXISTS engineering_material")
        self._cursor.execute(_CREATE_SQL)
        imported: list[dict[str, str]] = []
        for index, item in enumerate(manifest["required"], start=1):
            path = str(item["path"])
            body = (ROOT / path).read_text(encoding="utf-8")
            row = {
                "material_id": f"m{index}",
                "kind": str(item["kind"]),
                "path": path,
                "symbol": str(item["symbol"]),
                "body": body,
            }
            self._cursor.execute(
                "INSERT INTO engineering_material (material_id, kind, path, symbol, body) VALUES ("
                + ", ".join(_quote(row[name]) for name in ("material_id", "kind", "path", "symbol", "body"))
                + ")"
            )
            imported.append(row)
        return imported

    def query_for_task(self, task: str) -> dict[str, Any]:
        manifest = load_manifest()
        paths = [str(item["path"]) for item in manifest["required"]]
        path_sql = (
            "SELECT material_id, kind, path, symbol, body FROM engineering_material WHERE path IN ("
            + ", ".join(_quote(path) for path in paths)
            + ")"
        )
        self._cursor.execute(path_sql)
        rows = [_row(item) for item in self._cursor.fetchall()]
        match_sql = ""
        match_error = ""
        match_text = _match_text(task)
        if match_text:
            match_sql = (
                "SELECT material_id, kind, path, symbol, body FROM engineering_material "
                f"WHERE MATCH(body, path, symbol) AGAINST({_quote(match_text)} IN NATURAL LANGUAGE MODE)"
            )
            try:
                self._cursor.execute(match_sql)
                for item in self._cursor.fetchall():
                    row = _row(item)
                    if all(existing["material_id"] != row["material_id"] for existing in rows):
                        rows.append(row)
            except Exception as error:  # noqa: BLE001  检索失败要记下来，不能假装查到了
                match_error = f"{type(error).__name__}: {error}"
        record = {
            "task": task,
            "path_sql": " ".join(path_sql.split()),
            "match_sql": " ".join(match_sql.split()),
            "match_error": match_error,
            "rows": rows,
        }
        RECORDS.mkdir(parents=True, exist_ok=True)
        (RECORDS / "db_query.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return record


def _row(item: tuple) -> dict[str, str]:
    material_id, kind, path, symbol, body = item
    return {
        "material_id": material_id,
        "kind": kind,
        "path": path,
        "symbol": symbol,
        "body": body,
    }
