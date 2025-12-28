"""
Upload API Module

File upload endpoints following REST conventions.
"""

from .router import router
from .contracts import (
    UploadResponseContract,
    ValidationErrorContract,
)

__all__ = [
    "router",
    "UploadResponseContract",
    "ValidationErrorContract",
]
