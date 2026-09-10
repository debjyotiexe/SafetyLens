from abc import ABC, abstractmethod
import os
import time
import config


class StorageBackend(ABC):
    """Abstract storage backend for snapshot artifacts."""

    @abstractmethod
    def save(self, data: bytes, hint: str = "snapshot") -> str:
        """Save raw bytes and return a reference string."""
        pass

    @abstractmethod
    def url(self, ref: str) -> str:
        """Return a URL path to serve/access the stored artifact."""
        pass

    @abstractmethod
    def delete(self, ref: str) -> bool:
        """Delete artifact by reference. Return True if deleted, False otherwise."""
        pass

    @abstractmethod
    def exists(self, ref: str) -> bool:
        """Check if an artifact exists by reference."""
        pass

    @abstractmethod
    def cleanup_retention(self, days: int) -> int:
        """Delete artifacts older than `days` days. Return count of deleted items."""
        pass


class LocalStorage(StorageBackend):
    """Local filesystem storage implementation over config.SNAPSHOT_DIR."""

    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> str:
        return self._base_dir or config.SNAPSHOT_DIR

    @staticmethod
    def _safe_basename(ref: str) -> str:
        # Cross-platform basename: handles both / and \ on any OS
        return ref.replace("\\", "/").split("/")[-1]

    def _resolve_path(self, ref: str) -> str:
        basename = self._safe_basename(ref)
        return os.path.join(self.base_dir, basename)

    def save(self, data: bytes, hint: str = "snapshot") -> str:
        os.makedirs(self.base_dir, exist_ok=True)
        # Sanitize hint for safe filename usage
        safe_hint = "".join(c for c in hint if c.isalnum() or c in ("-", "_")).strip() or "snapshot"
        timestamp_ms = int(time.time() * 1000)
        filename = f"{timestamp_ms}_{safe_hint}.jpg"
        filepath = os.path.join(self.base_dir, filename)

        with open(filepath, "wb") as f:
            f.write(data)

        return filename

    def url(self, ref: str) -> str:
        basename = self._safe_basename(ref)
        return f"/snapshots/{basename}"

    def delete(self, ref: str) -> bool:
        filepath = self._resolve_path(ref)
        if os.path.isfile(filepath):
            try:
                os.remove(filepath)
                return True
            except OSError:
                return False
        return False

    def exists(self, ref: str) -> bool:
        filepath = self._resolve_path(ref)
        return os.path.isfile(filepath)

    def cleanup_retention(self, days: int) -> int:
        if days <= 0:
            return 0

        if not os.path.isdir(self.base_dir):
            return 0

        cutoff = time.time() - (days * 86400)
        deleted_count = 0

        for entry in os.listdir(self.base_dir):
            filepath = os.path.join(self.base_dir, entry)
            if os.path.isfile(filepath):
                try:
                    if os.path.getmtime(filepath) < cutoff:
                        os.remove(filepath)
                        deleted_count += 1
                except OSError:
                    continue

        return deleted_count


_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Factory returning singleton StorageBackend based on config.STORAGE_BACKEND."""
    global _storage_instance
    if _storage_instance is None:
        backend_type = getattr(config, "STORAGE_BACKEND", "local").lower()
        if backend_type == "local":
            _storage_instance = LocalStorage()
        else:
            raise ValueError(f"Unsupported storage backend: {backend_type}")
    return _storage_instance


def reset_storage():
    """Reset the singleton instance (primarily for test isolation)."""
    global _storage_instance
    _storage_instance = None
