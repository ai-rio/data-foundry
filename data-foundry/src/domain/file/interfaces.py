"""
File Domain Interfaces

Abstract base classes that define contracts for file-related operations.
These interfaces enable Dependency Inversion and Interface Segregation.

SOLID Principles:
- Interface Segregation: Each interface has a single, focused purpose
- Dependency Inversion: High-level modules depend on these abstractions
- Liskov Substitution: Any implementation can substitute for the interface
"""

from abc import ABC, abstractmethod
from typing import Optional

from .value_objects import FileMetadata, ValidationResult


class IFileValidator(ABC):
    """
    Interface for file validators.

    Interface Segregation Principle: This interface has exactly one method.
    Any validator that needs to validate files implements this interface.

    Validators can be composed using CompositeFileValidator to create
    complex validation chains while keeping each validator simple.
    """

    @abstractmethod
    async def validate(self, file: FileMetadata) -> ValidationResult:
        """
        Validate a file based on its metadata.

        Args:
            file: FileMetadata containing file information

        Returns:
            ValidationResult indicating whether validation passed,
            along with any errors, warnings, or additional data.

        Note:
            Implementations should be stateless and idempotent.
            The same input should always produce the same output.
        """
        pass


class IFileContentValidator(ABC):
    """
    Interface for validators that need to inspect file content.

    This is a separate interface from IFileValidator because:
    - It requires file bytes, not just metadata
    - It may be computationally expensive
    - Not all validation needs content inspection

    Interface Segregation: Separating metadata validation from content validation.
    """

    @abstractmethod
    async def validate_content(
        self,
        file: FileMetadata,
        content: bytes,
    ) -> ValidationResult:
        """
        Validate file content.

        Args:
            file: FileMetadata containing file information
            content: Raw bytes of the file

        Returns:
            ValidationResult with validation outcome
        """
        pass


class IFileHasher(ABC):
    """
    Interface for computing file hashes/checksums.

    Single Responsibility: Only computes hashes, doesn't validate.
    """

    @abstractmethod
    async def compute_hash(self, content: bytes) -> str:
        """
        Compute hash of file content.

        Args:
            content: File content as bytes

        Returns:
            Hash string (typically SHA-256 hex digest)
        """
        pass


class IVirusScanner(ABC):
    """
    Interface for virus/malware scanning.

    This is optional functionality that can be injected when needed.
    Dependency Inversion: Services can optionally depend on this interface.
    """

    @abstractmethod
    async def scan(self, content: bytes) -> ValidationResult:
        """
        Scan file content for viruses/malware.

        Args:
            content: File content as bytes

        Returns:
            ValidationResult with scan results.
            - valid=True means no threats detected
            - valid=False with errors listing detected threats
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the virus scanner is available.

        Returns:
            True if scanner is operational, False otherwise.
        """
        pass
