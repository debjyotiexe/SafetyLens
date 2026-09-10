import os
import time
import pytest
import config
from storage import StorageBackend, LocalStorage, get_storage, reset_storage


@pytest.fixture(autouse=True)
def setup_storage(tmp_path):
    reset_storage()
    test_snapshot_dir = str(tmp_path / "snapshots")
    os.makedirs(test_snapshot_dir, exist_ok=True)
    config.SNAPSHOT_DIR = test_snapshot_dir
    config.STORAGE_BACKEND = "local"
    yield
    reset_storage()


def test_storage_singleton():
    s1 = get_storage()
    s2 = get_storage()
    assert s1 is s2
    assert isinstance(s1, LocalStorage)


def test_storage_invalid_backend():
    reset_storage()
    config.STORAGE_BACKEND = "s3_unknown"
    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_storage()


def test_local_storage_save_and_url():
    storage = get_storage()
    dummy_data = b"fake_jpeg_content_12345"
    ref = storage.save(dummy_data, hint="NO_HELMET")

    assert ref.endswith("_NO_HELMET.jpg")
    assert storage.url(ref) == f"/snapshots/{ref}"
    assert storage.exists(ref) is True

    # Check file content on disk
    filepath = os.path.join(config.SNAPSHOT_DIR, ref)
    assert os.path.isfile(filepath)
    with open(filepath, "rb") as f:
        assert f.read() == dummy_data


def test_local_storage_delete_and_exists():
    storage = get_storage()
    dummy_data = b"bytes_to_delete"
    ref = storage.save(dummy_data, hint="test_del")

    assert storage.exists(ref) is True
    assert storage.delete(ref) is True
    assert storage.exists(ref) is False
    assert storage.delete(ref) is False  # Second delete should return False


def test_backward_compatible_refs():
    storage = get_storage()

    # Direct filename
    assert storage.url("12345_NO_HELMET.jpg") == "/snapshots/12345_NO_HELMET.jpg"

    # Full path
    assert storage.url("/app/backend/snapshots/12345_NO_HELMET.jpg") == "/snapshots/12345_NO_HELMET.jpg"

    # Relative path
    assert storage.url("snapshots/12345_NO_HELMET.jpg") == "/snapshots/12345_NO_HELMET.jpg"

    # Windows path
    assert storage.url(r"C:\SafetyLens\snapshots\12345_NO_HELMET.jpg") == "/snapshots/12345_NO_HELMET.jpg"


def test_cleanup_retention():
    storage = get_storage()
    now = time.time()

    # Create old file (10 days old)
    old_file = os.path.join(config.SNAPSHOT_DIR, "old_snap.jpg")
    with open(old_file, "wb") as f:
        f.write(b"old")
    ten_days_ago = now - (10 * 86400)
    os.utime(old_file, (ten_days_ago, ten_days_ago))

    # Create new file (1 day old)
    new_file = os.path.join(config.SNAPSHOT_DIR, "new_snap.jpg")
    with open(new_file, "wb") as f:
        f.write(b"new")
    one_day_ago = now - (1 * 86400)
    os.utime(new_file, (one_day_ago, one_day_ago))

    # Retention with days=0 (should do nothing)
    assert storage.cleanup_retention(days=0) == 0
    assert os.path.isfile(old_file)
    assert os.path.isfile(new_file)

    # Retention with days=5 (should delete old_file, keep new_file)
    deleted = storage.cleanup_retention(days=5)
    assert deleted == 1
    assert not os.path.isfile(old_file)
    assert os.path.isfile(new_file)
