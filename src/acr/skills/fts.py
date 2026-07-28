"""SQLite FTS5 virtual table + sync triggers over `skills.name`/`description`.

Same pattern as `acr.memory.fts`: shared by the Alembic migration and test
fixtures so schema and tests can't drift apart.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

CREATE_STATEMENTS: list[str] = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
        name,
        description,
        content='skills',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
        INSERT INTO skills_fts(rowid, name, description)
        VALUES (new.rowid, new.name, new.description);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
        INSERT INTO skills_fts(skills_fts, rowid, name, description)
        VALUES ('delete', old.rowid, old.name, old.description);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
        INSERT INTO skills_fts(skills_fts, rowid, name, description)
        VALUES ('delete', old.rowid, old.name, old.description);
        INSERT INTO skills_fts(rowid, name, description)
        VALUES (new.rowid, new.name, new.description);
    END
    """,
]

DROP_STATEMENTS: list[str] = [
    "DROP TRIGGER IF EXISTS skills_au",
    "DROP TRIGGER IF EXISTS skills_ad",
    "DROP TRIGGER IF EXISTS skills_ai",
    "DROP TABLE IF EXISTS skills_fts",
]


async def create_fts(conn: AsyncConnection) -> None:
    for statement in CREATE_STATEMENTS:
        await conn.execute(text(statement))


async def drop_fts(conn: AsyncConnection) -> None:
    for statement in DROP_STATEMENTS:
        await conn.execute(text(statement))
