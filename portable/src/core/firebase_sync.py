"""Publish Database Output .txt files straight into the Firestore catalog.

Uses a Firebase service-account JSON (a secret — keep it out of git) with
the ``firebase-admin`` Python SDK. Records are built by
:mod:`src.core.catalog_record`, which mirrors the web tool's parser, so an
automated publish writes to the same document ids with ``merge`` that the
admin panel uses.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.core.catalog_record import build_catalog_doc
from src.core.database_output import find_output_files

FIREBASE_SERVICE_ACCOUNT_NAME = "firebase-service-account.json"
DEFAULT_COLLECTION = "products"
BATCH_LIMIT = 450


class FirebaseSyncError(Exception):
    """User-actionable error while publishing to the catalog."""


def find_service_account_file(explicit: str | None = None) -> Path | None:
    """Locate the service-account JSON.

    Search order: explicit path, the ``GOOGLE_APPLICATION_CREDENTIALS`` env
    var, the current working directory, the repo root, then COAWeb next to
    the repo. Returns None when nothing is found.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p.resolve() if p.exists() else None

    candidates: list[Path] = []
    env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / FIREBASE_SERVICE_ACCOUNT_NAME)
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / FIREBASE_SERVICE_ACCOUNT_NAME)
    candidates.append(repo_root.parent / "COAWeb" / FIREBASE_SERVICE_ACCOUNT_NAME)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


_db_cache: dict[str, object] = {}


def _get_db(service_account_path: str):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as exc:
        raise FirebaseSyncError(
            "firebase-admin is not installed. Run: pip install firebase-admin"
        ) from exc

    if service_account_path in _db_cache:
        return _db_cache[service_account_path]

    try:
        app = firebase_admin.initialize_app(
            credentials.Certificate(service_account_path),
            name="coaparser_catalog_" + format(abs(hash(service_account_path)), "x"),
        )
        db = firestore.client(app=app)
    except Exception as exc:
        raise FirebaseSyncError(
            f"Could not initialize Firebase with the service account: {exc}"
        ) from exc

    _db_cache[service_account_path] = db
    return db


def publish_to_catalog(
    service_account_path: str,
    output_dir: str | Path = "Output",
    collection: str = DEFAULT_COLLECTION,
    on_progress=None,
) -> dict:
    """Build catalog docs from every .txt in output_dir and write them to
    Firestore in batches (merge, chunked at BATCH_LIMIT).

    ``on_progress(done, total, message)`` is invoked as batches commit.
    Returns ``{"published": int, "collection": str}``.
    """
    path = Path(service_account_path)
    if not path.exists():
        raise FirebaseSyncError(f"Service account file not found: {path}")
    if not Path(output_dir).exists():
        raise FirebaseSyncError(f"Output folder not found: {output_dir}")

    db = _get_db(str(path))

    txts = find_output_files(output_dir)
    if not txts:
        raise FirebaseSyncError("No .txt outputs found in the Output folder.")

    from firebase_admin import firestore

    docs = []
    for txt in txts:
        doc = build_catalog_doc(txt.read_text(encoding="utf-8"), txt.name)
        doc["created"] = firestore.SERVER_TIMESTAMP
        docs.append(doc)

    col = db.collection(collection)
    total = len(docs)
    done = 0
    for i in range(0, total, BATCH_LIMIT):
        chunk = docs[i : i + BATCH_LIMIT]
        batch = db.batch()
        for doc in chunk:
            batch.set(col.document(doc["id"]), doc, merge=True)
        batch.commit()
        done += len(chunk)
        if on_progress:
            on_progress(done, total, f"Publishing {done}/{total} product(s)")

    return {"published": total, "collection": collection}
