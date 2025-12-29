"""
Storage Domain Module

Contains interfaces and value objects for storage operations.
Follows Interface Segregation Principle - storage interface is minimal.
"""

from .interfaces import IStorageService
from .exceptions import StorageError, StorageConnectionError, StorageNotFoundError
from .value_objects import StorageKey, PresignedUrl

__all__ = [
    "IStorageService",
    "StorageError",
    "StorageConnectionError",
    "StorageNotFoundError",
    "StorageKey",
    "PresignedUrl",
]
