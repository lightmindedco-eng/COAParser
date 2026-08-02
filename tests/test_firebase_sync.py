from pathlib import Path

import pytest

import src.core.firebase_sync as firebase_sync
from src.core.firebase_sync import (
    FirebaseSyncError,
    find_service_account_file,
    publish_to_catalog,
)


def test_find_service_account_file_explicit(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text("{}", encoding="utf-8")
    assert find_service_account_file(str(sa)) == sa.resolve()


def test_find_service_account_file_explicit_missing(tmp_path: Path) -> None:
    assert find_service_account_file(str(tmp_path / "nope.json")) is None


def test_find_service_account_file_none_when_unset(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        firebase_sync, "FIREBASE_SERVICE_ACCOUNT_NAME", "not-the-secret.json"
    )
    assert find_service_account_file() is None


def test_publish_missing_service_account(tmp_path: Path) -> None:
    with pytest.raises(FirebaseSyncError, match="Service account file not found"):
        publish_to_catalog(str(tmp_path / "missing.json"), str(tmp_path))


def test_publish_missing_output_dir(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text("{}", encoding="utf-8")
    with pytest.raises(FirebaseSyncError, match="Output folder not found"):
        publish_to_catalog(str(sa), str(tmp_path / "DoesNotExist"))
