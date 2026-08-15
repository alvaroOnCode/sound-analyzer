from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from sound_analyzer.paths import index_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    relpath TEXT UNIQUE NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    duration REAL,
    sample_rate INTEGER,
    channels INTEGER,
    codec TEXT,
    scanned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    duration_ms INTEGER NOT NULL,
    category TEXT,
    subcategory TEXT,
    tags_json TEXT,
    suggested_name TEXT,
    confidence REAL,
    embedded INTEGER NOT NULL DEFAULT 0,
    tagged INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS embeddings (
    clip_id INTEGER PRIMARY KEY,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    FOREIGN KEY(clip_id) REFERENCES clips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS organize_log (
    id INTEGER PRIMARY KEY,
    clip_id INTEGER NOT NULL,
    dest_relpath TEXT NOT NULL,
    method TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(clip_id) REFERENCES clips(id)
);

CREATE INDEX IF NOT EXISTS idx_clips_file ON clips(file_id);
CREATE INDEX IF NOT EXISTS idx_clips_embedded ON clips(embedded);
CREATE INDEX IF NOT EXISTS idx_clips_tagged ON clips(tagged);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class FileRow:
    id: int
    relpath: str
    size: int
    mtime: float
    duration: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None

    @property
    def path(self) -> Path:
        return Path(self.relpath)


@dataclass(frozen=True)
class ClipRow:
    id: int
    file_id: int
    relpath: str
    start_sec: float
    end_sec: float
    duration_ms: int
    category: str | None
    subcategory: str | None
    tags_json: str | None
    suggested_name: str | None
    confidence: float | None
    embedded: int
    tagged: int

    @property
    def tags(self) -> list[dict[str, Any]]:
        if not self.tags_json:
            return []
        return json.loads(self.tags_json)

    @property
    def is_full_file(self) -> bool:
        return self.start_sec <= 0.02 and (self.end_sec >= (self.duration_ms / 1000.0) - 0.08)


@dataclass(frozen=True)
class ClipView:
    """A clip together with the file it comes from, read in a single join."""

    clip: ClipRow
    file: FileRow


SORTS: dict[str, str] = {
    "name": "COALESCE(NULLIF(clips.suggested_name, ''), files.relpath) ASC, clips.start_sec ASC",
    "path": "files.relpath ASC, clips.start_sec ASC",
    "short": "clips.duration_ms ASC, files.relpath ASC",
    "long": "clips.duration_ms DESC, files.relpath ASC",
    "recent": "files.mtime DESC, files.relpath ASC",
    "confidence": "clips.confidence IS NULL, clips.confidence DESC, files.relpath ASC",
}

_CLIP_VIEW_COLUMNS = """
    clips.*,
    files.relpath AS relpath,
    files.id AS file_row_id,
    files.size AS file_size,
    files.mtime AS file_mtime,
    files.duration AS file_duration,
    files.sample_rate AS file_sample_rate,
    files.channels AS file_channels,
    files.codec AS file_codec
"""


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _browse_filters(
    *,
    category: str | None,
    subcategory: str | None,
    folder: str | None,
    text: str | None,
    min_duration: float | None,
    max_duration: float | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("clips.category = ?")
        params.append(category)
    if subcategory:
        clauses.append("clips.subcategory = ?")
        params.append(subcategory)
    if folder:
        prefix = folder.replace("\\", "/").strip("/")
        if prefix:
            clauses.append("files.relpath LIKE ? ESCAPE '\\'")
            params.append(f"{_like_escape(prefix)}/%")
    if text and text.strip():
        needle = f"%{_like_escape(text.strip().lower())}%"
        clauses.append(
            "("
            "LOWER(COALESCE(clips.suggested_name, '')) LIKE ? ESCAPE '\\'"
            " OR LOWER(files.relpath) LIKE ? ESCAPE '\\'"
            " OR LOWER(COALESCE(clips.tags_json, '')) LIKE ? ESCAPE '\\'"
            " OR LOWER(COALESCE(clips.category, '')) LIKE ? ESCAPE '\\'"
            " OR LOWER(COALESCE(clips.subcategory, '')) LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([needle] * 5)
    if min_duration is not None:
        clauses.append("clips.duration_ms >= ?")
        params.append(int(min_duration * 1000))
    if max_duration is not None:
        clauses.append("clips.duration_ms <= ?")
        params.append(int(max_duration * 1000))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


class Catalog:
    def __init__(self, library: Path):
        self.library = library.resolve()
        self.dir = index_dir(self.library)
        self.db_path = self.dir / "catalog.sqlite"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def abs_path(self, relpath: str) -> Path:
        return self.library / relpath

    def upsert_file(
        self,
        relpath: str,
        *,
        size: int,
        mtime: float,
        duration: float | None,
        sample_rate: int | None,
        channels: int | None,
        codec: str | None,
    ) -> tuple[int, bool]:
        """Insert or update a file. Returns (id, changed)."""
        existing = self.conn.execute(
            "SELECT id, size, mtime FROM files WHERE relpath = ?",
            (relpath,),
        ).fetchone()
        if existing is None:
            cur = self.conn.execute(
                """
                INSERT INTO files (relpath, size, mtime, duration, sample_rate, channels, codec, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (relpath, size, mtime, duration, sample_rate, channels, codec, _utcnow()),
            )
            self.conn.commit()
            return int(cur.lastrowid), True
        file_id = int(existing["id"])
        changed = existing["size"] != size or abs(existing["mtime"] - mtime) > 0.001
        self.conn.execute(
            """
            UPDATE files
            SET size = ?, mtime = ?, duration = ?, sample_rate = ?, channels = ?, codec = ?, scanned_at = ?
            WHERE id = ?
            """,
            (size, mtime, duration, sample_rate, channels, codec, _utcnow(), file_id),
        )
        self.conn.commit()
        return file_id, changed

    def get_file(self, file_id: int) -> FileRow | None:
        row = self.conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return self._file_from_row(row) if row else None

    def get_file_by_path(self, relpath: str) -> FileRow | None:
        row = self.conn.execute("SELECT * FROM files WHERE relpath = ?", (relpath,)).fetchone()
        return self._file_from_row(row) if row else None

    def iter_files(self) -> Iterator[FileRow]:
        for row in self.conn.execute("SELECT * FROM files ORDER BY relpath"):
            yield self._file_from_row(row)

    def file_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])

    def clip_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0])

    def replace_clips(self, file_id: int, intervals: Iterable[tuple[float, float]]) -> int:
        self.conn.execute("DELETE FROM clips WHERE file_id = ?", (file_id,))
        count = 0
        for start, end in intervals:
            duration_ms = max(1, int(round((end - start) * 1000)))
            self.conn.execute(
                """
                INSERT INTO clips (file_id, start_sec, end_sec, duration_ms)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, start, end, duration_ms),
            )
            count += 1
        self.conn.commit()
        return count

    def clips_for_file(self, file_id: int) -> list[ClipRow]:
        rows = self.conn.execute(
            """
            SELECT clips.*, files.relpath
            FROM clips JOIN files ON files.id = clips.file_id
            WHERE file_id = ?
            ORDER BY start_sec
            """,
            (file_id,),
        ).fetchall()
        return [self._clip_from_row(row) for row in rows]

    def iter_clips(self, *, missing_embed: bool = False, missing_tags: bool = False) -> Iterator[ClipRow]:
        clauses = []
        if missing_embed:
            clauses.append("clips.embedded = 0")
        if missing_tags:
            clauses.append("clips.tagged = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT clips.*, files.relpath
            FROM clips JOIN files ON files.id = clips.file_id
            {where}
            ORDER BY files.relpath, clips.start_sec
        """
        for row in self.conn.execute(sql):
            yield self._clip_from_row(row)

    def get_clip(self, clip_id: int) -> ClipRow | None:
        row = self.conn.execute(
            """
            SELECT clips.*, files.relpath
            FROM clips JOIN files ON files.id = clips.file_id
            WHERE clips.id = ?
            """,
            (clip_id,),
        ).fetchone()
        return self._clip_from_row(row) if row else None

    def save_embedding(self, clip_id: int, vector) -> None:
        import numpy as np

        arr = np.asarray(vector, dtype=np.float32).reshape(-1)
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings (clip_id, dim, vector) VALUES (?, ?, ?)",
            (clip_id, int(arr.shape[0]), arr.tobytes()),
        )
        self.conn.execute("UPDATE clips SET embedded = 1 WHERE id = ?", (clip_id,))
        self.conn.commit()

    def load_embeddings(self) -> tuple[list[int], Any]:
        import numpy as np

        rows = self.conn.execute(
            """
            SELECT embeddings.clip_id, embeddings.dim, embeddings.vector
            FROM embeddings
            JOIN clips ON clips.id = embeddings.clip_id
            ORDER BY embeddings.clip_id
            """
        ).fetchall()
        if not rows:
            return [], np.zeros((0, 512), dtype=np.float32)
        ids = [int(row["clip_id"]) for row in rows]
        dim = int(rows[0]["dim"])
        matrix = np.vstack(
            [np.frombuffer(row["vector"], dtype=np.float32, count=dim) for row in rows]
        )
        return ids, matrix

    def save_tags(
        self,
        clip_id: int,
        *,
        category: str,
        subcategory: str,
        tags: list[dict[str, Any]],
        suggested_name: str,
        confidence: float,
    ) -> None:
        self.conn.execute(
            """
            UPDATE clips
            SET category = ?, subcategory = ?, tags_json = ?, suggested_name = ?,
                confidence = ?, tagged = 1
            WHERE id = ?
            """,
            (category, subcategory, json.dumps(tags, ensure_ascii=False), suggested_name, confidence, clip_id),
        )
        self.conn.commit()

    def log_organize(self, clip_id: int, dest_relpath: str, method: str) -> None:
        self.conn.execute(
            """
            INSERT INTO organize_log (clip_id, dest_relpath, method, applied_at, undone)
            VALUES (?, ?, ?, ?, 0)
            """,
            (clip_id, dest_relpath, method, _utcnow()),
        )
        self.conn.commit()

    def pending_organize(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT organize_log.*, clips.suggested_name, clips.category, clips.subcategory
                FROM organize_log
                JOIN clips ON clips.id = organize_log.clip_id
                WHERE undone = 0
                ORDER BY organize_log.id
                """
            )
        )

    def mark_undone(self, log_id: int) -> None:
        self.conn.execute("UPDATE organize_log SET undone = 1 WHERE id = ?", (log_id,))
        self.conn.commit()

    def stats(self) -> dict[str, int]:
        tagged = int(self.conn.execute("SELECT COUNT(*) FROM clips WHERE tagged = 1").fetchone()[0])
        embedded = int(self.conn.execute("SELECT COUNT(*) FROM clips WHERE embedded = 1").fetchone()[0])
        organized = int(
            self.conn.execute("SELECT COUNT(*) FROM organize_log WHERE undone = 0").fetchone()[0]
        )
        return {
            "files": self.file_count(),
            "clips": self.clip_count(),
            "embedded": embedded,
            "tagged": tagged,
            "organized": organized,
        }

    def category_tree(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT category, subcategory, COUNT(*) AS total
            FROM clips
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category, subcategory
            ORDER BY category ASC, total DESC
            """
        ).fetchall()
        tree: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = tree.setdefault(row["category"], {"name": row["category"], "count": 0, "subcategories": []})
            entry["count"] += int(row["total"])
            if row["subcategory"]:
                entry["subcategories"].append({"name": row["subcategory"], "count": int(row["total"])})
        return sorted(tree.values(), key=lambda item: -item["count"])

    def folders(self) -> list[dict[str, Any]]:
        """Top-level folders of the bank, with clip counts."""
        rows = self.conn.execute(
            """
            SELECT
                CASE
                    WHEN instr(files.relpath, '/') > 0
                    THEN substr(files.relpath, 1, instr(files.relpath, '/') - 1)
                    ELSE ''
                END AS folder,
                COUNT(*) AS total
            FROM clips JOIN files ON files.id = clips.file_id
            GROUP BY folder
            ORDER BY folder ASC
            """
        ).fetchall()
        return [
            {"name": row["folder"] or ".", "path": row["folder"], "count": int(row["total"])}
            for row in rows
        ]

    def query_clips(
        self,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        folder: str | None = None,
        text: str | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        sort: str = "name",
        limit: int = 60,
        offset: int = 0,
    ) -> list[ClipView]:
        where, params = _browse_filters(
            category=category,
            subcategory=subcategory,
            folder=folder,
            text=text,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        order = SORTS.get(sort, SORTS["name"])
        rows = self.conn.execute(
            f"""
            SELECT {_CLIP_VIEW_COLUMNS}
            FROM clips JOIN files ON files.id = clips.file_id
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,
            [*params, max(0, int(limit)), max(0, int(offset))],
        ).fetchall()
        return [self._clip_view_from_row(row) for row in rows]

    def count_clips(
        self,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        folder: str | None = None,
        text: str | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
    ) -> int:
        where, params = _browse_filters(
            category=category,
            subcategory=subcategory,
            folder=folder,
            text=text,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM clips JOIN files ON files.id = clips.file_id {where}",
            params,
        ).fetchone()
        return int(row[0])

    def get_clip_view(self, clip_id: int) -> ClipView | None:
        row = self.conn.execute(
            f"""
            SELECT {_CLIP_VIEW_COLUMNS}
            FROM clips JOIN files ON files.id = clips.file_id
            WHERE clips.id = ?
            """,
            (clip_id,),
        ).fetchone()
        return self._clip_view_from_row(row) if row else None

    @classmethod
    def _clip_view_from_row(cls, row: sqlite3.Row) -> ClipView:
        file = FileRow(
            id=int(row["file_row_id"]),
            relpath=row["relpath"],
            size=int(row["file_size"]),
            mtime=float(row["file_mtime"]),
            duration=row["file_duration"],
            sample_rate=row["file_sample_rate"],
            channels=row["file_channels"],
            codec=row["file_codec"],
        )
        return ClipView(clip=cls._clip_from_row(row), file=file)

    @staticmethod
    def _file_from_row(row: sqlite3.Row) -> FileRow:
        return FileRow(
            id=int(row["id"]),
            relpath=row["relpath"],
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            duration=row["duration"],
            sample_rate=row["sample_rate"],
            channels=row["channels"],
            codec=row["codec"],
        )

    @staticmethod
    def _clip_from_row(row: sqlite3.Row) -> ClipRow:
        return ClipRow(
            id=int(row["id"]),
            file_id=int(row["file_id"]),
            relpath=row["relpath"],
            start_sec=float(row["start_sec"]),
            end_sec=float(row["end_sec"]),
            duration_ms=int(row["duration_ms"]),
            category=row["category"],
            subcategory=row["subcategory"],
            tags_json=row["tags_json"],
            suggested_name=row["suggested_name"],
            confidence=row["confidence"],
            embedded=int(row["embedded"]),
            tagged=int(row["tagged"]),
        )
