"""SQLite FTS5 virtual table + sync triggers over `memory_records.content`.

Shared by the Alembic migration (production schema) and test fixtures (fast
in-process schema setup) so the two definitions can never drift apart.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

CREATE_STATEMENTS: list[str] = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
        content,
        content='memory_records',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_records_ai AFTER INSERT ON memory_records BEGIN
        INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_records_ad AFTER DELETE ON memory_records BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, content)
        VALUES ('delete', old.rowid, old.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_records_au AFTER UPDATE ON memory_records BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, content)
        VALUES ('delete', old.rowid, old.content);
        INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
    END
    """,
]

DROP_STATEMENTS: list[str] = [
    "DROP TRIGGER IF EXISTS memory_records_au",
    "DROP TRIGGER IF EXISTS memory_records_ad",
    "DROP TRIGGER IF EXISTS memory_records_ai",
    "DROP TABLE IF EXISTS memory_fts",
]


async def create_fts(conn: AsyncConnection) -> None:
    for statement in CREATE_STATEMENTS:
        await conn.execute(text(statement))


async def drop_fts(conn: AsyncConnection) -> None:
    for statement in DROP_STATEMENTS:
        await conn.execute(text(statement))
