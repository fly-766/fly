"""Append-only local history, content-addressed artifacts and deterministic audit."""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

ZERO = "0" * 64

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".partial")
    with temp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)

class Journal:
    def __init__(self, directory, *, readonly=False):
        self.root = Path(directory)
        if not readonly: self.root.mkdir(parents=True, exist_ok=True)
        db = self.root / "journal.sqlite"
        self.db = sqlite3.connect(f"file:{db}?mode=ro" if readonly else str(db), uri=readonly)
        self.db.row_factory = sqlite3.Row
        if not readonly:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rounds(seq INTEGER PRIMARY KEY, previous TEXT NOT NULL,
                    root TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY, name TEXT NOT NULL, bytes INTEGER NOT NULL);
            """)
            self.db.commit()

    def close(self): self.db.close()

    def meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def initialize(self, manifest):
        if self.meta("manifest") is not None:
            if self.meta("manifest") != manifest: raise ValueError("Existing run manifest differs")
            return
        if self.db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]: raise ValueError("History without genesis")
        with self.db:
            self.db.execute("INSERT INTO meta VALUES ('manifest',?)", (canonical(manifest).decode(),))

    def artifact(self, data, suffix):
        if suffix not in (".png", ".npz", ".json"): raise ValueError("Unsupported artifact")
        h = hashlib.sha256(data).hexdigest()
        name = h + suffix
        target = self.root / "artifacts" / name
        if not target.exists(): atomic(target, data)
        elif file_digest(target) != h: raise ValueError("Artifact corruption")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?)", (h, name, len(data)))
        return {"sha256": h, "name": name, "bytes": len(data)}

    def artifact_path(self, name):
        if not re.fullmatch(r"[0-9a-f]{64}\.(png|npz|json)", name): raise ValueError("Invalid artifact name")
        row = self.db.execute("SELECT name FROM artifacts WHERE name=?", (name,)).fetchone()
        if not row: raise FileNotFoundError(name)
        return self.root / "artifacts" / row[0]

    def rows(self, limit=None):
        if limit is None:
            rows = self.db.execute("SELECT * FROM rounds ORDER BY seq").fetchall()
        else:
            rows = self.db.execute("SELECT * FROM rounds ORDER BY seq DESC LIMIT ?", (max(1,min(int(limit),100)),)).fetchall()[::-1]
        return [{"seq":r["seq"],"previous":r["previous"],"root":r["root"],"body":json.loads(r["body"])} for r in rows]

    def append(self, body):
        manifest = self.meta("manifest")
        if manifest is None: raise ValueError("Missing genesis")
        last = self.db.execute("SELECT seq,root FROM rounds ORDER BY seq DESC LIMIT 1").fetchone()
        seq, previous = (last[0]+1,last[1]) if last else (1,digest(manifest))
        if body.get("sequence") != seq or body.get("runId") != manifest["runId"]:
            raise ValueError("Sequence or run identity mismatch")
        root = digest({"previous":previous,"body":body})
        with self.db:
            self.db.execute("INSERT INTO rounds VALUES (?,?,?,?)", (seq,previous,root,canonical(body).decode()))
        return {"seq":seq,"previous":previous,"root":root,"body":body}

    def audit(self, expected_head=None):
        manifest = self.meta("manifest")
        if not manifest: raise ValueError("Missing manifest")
        previous = digest(manifest)
        rows = self.rows()
        for i,row in enumerate(rows,1):
            b = row["body"]
            if row["seq"]!=i or b.get("sequence")!=i or b.get("runId")!=manifest["runId"]: raise ValueError("Sequence mismatch")
            if row["previous"]!=previous or row["root"]!=digest({"previous":previous,"body":b}): raise ValueError("History changed")
            for key in ("input", "checkpoint"):
                a=b.get(key)
                if a and file_digest(self.artifact_path(a["name"]))!=a["sha256"]: raise ValueError("Artifact changed")
            previous=row["root"]
        genesis=manifest["genesis"]
        if file_digest(self.artifact_path(genesis["name"]))!=genesis["sha256"]: raise ValueError("Genesis changed")
        if expected_head and previous!=expected_head: raise ValueError("Does not match externally held head")
        return {"valid":True,"rounds":len(rows),"head":previous,"manifestHash":digest(manifest),
                "anchoredOnchain":False,"trust":"local hash-chain; external head needed to detect full history replacement"}
