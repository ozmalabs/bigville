"""Wikipedia library — local read API over the wikimedia/structured-wikipedia
parquet snapshot. The library is a physical-feeling thing the agent can walk
up to and consult; this module is the back-end (index + parquet reads), and
``wiki_world`` is the front-end (affordances inside a World).

The snapshot lives at ``$WIKI_DATA_DIR`` (default ``/home/matt/ozma/data/wikipedia``)
as a directory of parquet files under ``enwiki/data/``. Each row is one
article. The structured fields (``sections``, ``infoboxes``, ``tables``,
``references``) are stored as JSON-encoded strings inside the parquet rows
— the dataset's own design — so we parse them on demand rather than at
load time.

Index: a sidecar SQLite database keyed by ``title_norm`` (lower-cased title)
→ ``(file_idx, row_idx)``. Built lazily by ``build_index()`` walking every
parquet file's name column once; takes minutes on first run, instant on
restart. The index is a derived artefact — delete to rebuild.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pyarrow.parquet as pq


DEFAULT_DATA_DIR = Path("/home/matt/ozma/data/wikipedia")


@dataclass
class Article:
    """One Wikipedia article, materialised lazily from a parquet row."""
    identifier: int
    title: str
    url: str
    abstract: str
    description: str
    sections: list[dict] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    infoboxes: list[dict] = field(default_factory=list)

    def section_names(self) -> list[str]:
        return [s.get("name", "") for s in self.sections]

    def section_text(self, idx: int) -> str:
        """Concatenated free-text of one section (skip nested structures)."""
        if idx < 0 or idx >= len(self.sections):
            return ""
        return _flatten_text(self.sections[idx])


# ----------------------------------------------------------------------------
# section-tree text extractor
# ----------------------------------------------------------------------------

def _flatten_text(node: dict) -> str:
    """Walk a section sub-tree, yielding paragraph text in order."""
    parts: list[str] = []
    has_parts = node.get("has_parts") or []
    for p in has_parts:
        t = p.get("type")
        if t == "paragraph":
            v = p.get("value") or ""
            if v:
                parts.append(v.strip())
        elif t in ("section", "list", "table"):
            sub = _flatten_text(p)
            if sub:
                parts.append(sub)
    return "\n\n".join(parts)


def _extract_links(node: dict, out: list[str]) -> None:
    """Collect article-name targets of inline wiki links inside a sub-tree."""
    for p in (node.get("has_parts") or []):
        for L in (p.get("links") or []):
            url = L.get("url") or ""
            # https://en.wikipedia.org/wiki/Bob_Dylan → Bob Dylan
            if "/wiki/" in url:
                tail = url.split("/wiki/", 1)[1]
                if "#" in tail:
                    tail = tail.split("#", 1)[0]
                if tail and ":" not in tail:
                    out.append(tail.replace("_", " "))
        if p.get("type") in ("section", "list", "table"):
            _extract_links(p, out)


def _parse_row(row: dict) -> Article:
    """Parquet row dict → Article. Parses JSON-encoded structured fields."""
    sections_raw = row.get("sections") or "[]"
    try:
        sections = json.loads(sections_raw) if isinstance(sections_raw, str) \
                   else (sections_raw or [])
    except Exception:
        sections = []
    if not isinstance(sections, list):
        sections = []

    infoboxes_raw = row.get("infoboxes") or "[]"
    try:
        infoboxes = json.loads(infoboxes_raw) if isinstance(infoboxes_raw, str) \
                    else (infoboxes_raw or [])
    except Exception:
        infoboxes = []
    if not isinstance(infoboxes, list):
        infoboxes = []

    links: list[str] = []
    for sec in sections:
        _extract_links(sec, links)
    # de-dupe preserving order
    seen: set[str] = set()
    uniq_links = []
    for L in links:
        if L not in seen:
            seen.add(L)
            uniq_links.append(L)

    return Article(
        identifier=int(row.get("identifier") or 0),
        title=str(row.get("name") or ""),
        url=str(row.get("url") or ""),
        abstract=str(row.get("abstract") or ""),
        description=str(row.get("description") or ""),
        sections=sections,
        links=uniq_links,
        infoboxes=infoboxes,
    )


# ----------------------------------------------------------------------------
# library
# ----------------------------------------------------------------------------

@dataclass
class WikipediaLibrary:
    """Local read API over the structured-wikipedia snapshot.

    Lazy: only opens parquet files when a request lands on them. The index
    DB persists across runs.
    """
    data_dir: Path = DEFAULT_DATA_DIR
    index_path: Path | None = None

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        if self.index_path is None:
            self.index_path = self.data_dir / "title_index.sqlite"
        self.index_path = Path(self.index_path)
        self._files: list[Path] | None = None
        self._db: sqlite3.Connection | None = None

    # --- file discovery ------------------------------------------------

    def parquet_files(self) -> list[Path]:
        """Cached list of parquet files under enwiki/data/, sorted."""
        if self._files is None:
            d = self.data_dir / "enwiki" / "data"
            if not d.exists():
                self._files = []
            else:
                self._files = sorted(d.glob("enwiki_namespace_0_*.parquet"))
        return self._files

    def refresh(self) -> None:
        """Forget cached file list — call after the download adds more shards."""
        self._files = None

    # --- index ---------------------------------------------------------

    def _open_db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = sqlite3.connect(str(self.index_path))
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS articles ("
                "  title_norm TEXT PRIMARY KEY, "
                "  title TEXT NOT NULL, "
                "  file_idx INTEGER NOT NULL, "
                "  row_idx INTEGER NOT NULL)")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS indexed_files ("
                "  file_idx INTEGER PRIMARY KEY, "
                "  filename TEXT NOT NULL UNIQUE)")
            self._db.commit()
        return self._db

    def index_size(self) -> int:
        db = self._open_db()
        return db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def indexed_files(self) -> set[int]:
        db = self._open_db()
        return {r[0] for r in db.execute("SELECT file_idx FROM indexed_files")}

    def build_index(self, max_files: int | None = None,
                    progress: bool = False) -> int:
        """Walk every parquet file once, fill the index. Idempotent — files
        already indexed are skipped.

        Returns total number of articles indexed so far."""
        db = self._open_db()
        files = self.parquet_files()
        done = self.indexed_files()
        new_files = [(i, f) for i, f in enumerate(files) if i not in done]
        if max_files is not None:
            new_files = new_files[:max_files]
        for idx, path in new_files:
            if progress:
                print(f"  indexing {path.name} ({idx + 1}/{len(files)})…")
            try:
                pf = pq.ParquetFile(path)
                row_offset = 0
                for batch in pf.iter_batches(columns=["name"], batch_size=8192):
                    names = batch.column("name").to_pylist()
                    rows = [
                        (str(n).lower(), str(n), idx, row_offset + j)
                        for j, n in enumerate(names) if n
                    ]
                    db.executemany(
                        "INSERT OR REPLACE INTO articles "
                        "(title_norm, title, file_idx, row_idx) "
                        "VALUES (?, ?, ?, ?)", rows)
                    row_offset += len(names)
                db.execute(
                    "INSERT OR REPLACE INTO indexed_files (file_idx, filename) "
                    "VALUES (?, ?)", (idx, path.name))
                db.commit()
            except Exception as e:
                if progress:
                    print(f"  skip {path.name}: {e}")
        return self.index_size()

    # --- reads ---------------------------------------------------------

    def article(self, title: str) -> Article | None:
        """Look up an article by title. Case-insensitive."""
        db = self._open_db()
        row = db.execute(
            "SELECT file_idx, row_idx FROM articles WHERE title_norm = ?",
            (title.lower(),)).fetchone()
        if row is None:
            return None
        file_idx, row_idx = row
        return self._read_row(file_idx, row_idx)

    def random_article(self, rng: random.Random | None = None) -> Article | None:
        """Pick a random article from the index. Uniform over indexed titles."""
        db = self._open_db()
        total = self.index_size()
        if total == 0:
            return None
        rng = rng or random
        which = rng.randint(0, total - 1)
        row = db.execute(
            "SELECT file_idx, row_idx FROM articles LIMIT 1 OFFSET ?",
            (which,)).fetchone()
        if row is None:
            return None
        file_idx, row_idx = row
        return self._read_row(file_idx, row_idx)

    def search_prefix(self, prefix: str, limit: int = 20) -> list[str]:
        """Titles starting with prefix (case-insensitive)."""
        db = self._open_db()
        rows = db.execute(
            "SELECT title FROM articles WHERE title_norm LIKE ? LIMIT ?",
            (prefix.lower() + "%", limit)).fetchall()
        return [r[0] for r in rows]

    def has_article(self, title: str) -> bool:
        db = self._open_db()
        r = db.execute(
            "SELECT 1 FROM articles WHERE title_norm = ? LIMIT 1",
            (title.lower(),)).fetchone()
        return r is not None

    # --- internals -----------------------------------------------------

    def _read_row(self, file_idx: int, row_idx: int) -> Article | None:
        files = self.parquet_files()
        if file_idx >= len(files):
            return None
        path = files[file_idx]
        pf = pq.ParquetFile(path)
        # binary-walk row_groups instead of reading the whole file
        offset = 0
        for rg in range(pf.num_row_groups):
            nrows = pf.metadata.row_group(rg).num_rows
            if offset + nrows > row_idx:
                table = pf.read_row_group(rg)
                local = row_idx - offset
                row = {c: table.column(c)[local].as_py()
                       for c in table.column_names}
                return _parse_row(row)
            offset += nrows
        return None

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


__all__ = ["Article", "WikipediaLibrary", "DEFAULT_DATA_DIR"]
