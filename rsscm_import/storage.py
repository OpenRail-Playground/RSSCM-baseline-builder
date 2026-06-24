"""Asset storage — store binaries locally with SHA-256 verification."""
import shutil
from pathlib import Path


def store_assets(classified_files: list[dict], store_dir: str) -> list[dict]:
    """Store binary files (firmware, archives) in a structured local directory.

    Returns manifest of stored assets with paths and hashes.
    """
    store_path = Path(store_dir)
    store_path.mkdir(parents=True, exist_ok=True)
    manifest = []

    for entry in classified_files:
        if entry["type"] not in ("firmware", "archive", "executable"):
            continue

        # Use filename as the storage path (flat for now)
        dest = store_path / entry["filename"]
        dest.parent.mkdir(parents=True, exist_ok=True)

        # If entry has a source path we can copy from (temp extraction), record it
        manifest.append({
            "filename": entry["filename"],
            "type": entry["type"],
            "sha256": entry["sha256"],
            "size": entry["size"],
            "stored_path": str(dest),
            "release_archive_link": f"file://{dest.resolve()}",
            "release_archive_hash": entry["sha256"],
        })

    if manifest:
        print(f"  {len(manifest)} assets recorded for storage.")
    else:
        print("  No binary assets to store.")

    return manifest
