"""
Storage Infrastructure

Implementations of IStorageService for various providers.
"""

from .local_storage_service import LocalStorageService

# Lazy import for R2StorageService to avoid boto3 dependency when not needed
def __getattr__(name):
    if name == "R2StorageService":
        from .r2_storage_service import R2StorageService
        return R2StorageService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "R2StorageService",
    "LocalStorageService",
]
