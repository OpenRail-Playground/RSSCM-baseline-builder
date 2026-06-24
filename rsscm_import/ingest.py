"""Vendor delivery ingestion — extract and classify files."""
import hashlib
import os
import shutil
import zipfile
from pathlib import Path

MAX_DEPTH = 3
MAX_ENTRIES = 1000
MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_SINGLE_FILE = 100 * 1024 * 1024  # 100 MB

FILE_TYPES = {
    "firmware": {".bin", ".hex", ".mhx", ".s19", ".tlc"},
    "archive": {".zip", ".tgz", ".tar.gz"},
    "document": {".pdf", ".docx", ".doc"},
    "data": {".xls", ".xlsx", ".xlsm", ".csv"},
    "executable": {".exe"},
}


def classify_file(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for ftype, extensions in FILE_TYPES.items():
        if ext in extensions:
            return ftype
    return "other"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_delivery(path: str, store_dir: str | None = None) -> list[dict]:
    """Ingest a vendor delivery zip or folder, returning classified file entries."""
    source = Path(path)
    if source.is_file() and source.suffix.lower() == ".zip":
        return _ingest_zip(source, store_dir)
    elif source.is_dir():
        return _ingest_folder(source, store_dir)
    else:
        raise click.ClickException(f"Unsupported input: {path}")


def _ingest_zip(zip_path: Path, store_dir: str | None, depth: int = 0) -> list[dict]:
    if depth > MAX_DEPTH:
        raise ValueError(f"Max archive depth ({MAX_DEPTH}) exceeded — possible zip bomb.")

    entries = []
    total_size = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ENTRIES:
            raise ValueError(f"Too many entries ({len(infos)} > {MAX_ENTRIES}) — possible zip bomb.")

        for info in infos:
            if info.file_size > MAX_SINGLE_FILE:
                raise ValueError(f"File too large: {info.filename} ({info.file_size} bytes)")
            total_size += info.file_size
            if total_size > MAX_TOTAL_SIZE:
                raise ValueError(f"Total uncompressed size exceeds {MAX_TOTAL_SIZE} bytes — possible zip bomb.")

        # Extract to temp dir for hashing and optional storage
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extractall(tmpdir)
            entries = _ingest_folder(Path(tmpdir), store_dir, depth=depth)
            # Fix paths to be relative to zip
            for entry in entries:
                entry["source_archive"] = str(zip_path)

    return entries


def _ingest_folder(folder: Path, store_dir: str | None, depth: int = 0) -> list[dict]:
    entries = []
    for root, _, files in os.walk(folder):
        for fname in files:
            fpath = Path(root) / fname
            ftype = classify_file(fname)
            size = fpath.stat().st_size
            sha = sha256_file(fpath)
            rel_path = str(fpath.relative_to(folder))

            entry = {
                "path": rel_path,
                "filename": fname,
                "type": ftype,
                "size": size,
                "sha256": sha,
            }

            # Recurse into nested archives
            if ftype == "archive" and fpath.suffix.lower() == ".zip" and depth < MAX_DEPTH:
                entry["nested"] = _ingest_zip(fpath, store_dir, depth=depth + 1)

            entries.append(entry)

            if store_dir:
                dest = Path(store_dir) / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fpath, dest)

    return entries
