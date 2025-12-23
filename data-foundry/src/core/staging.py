"""
Simple staging layer for deduplication before analysis

Adapted from pipeline-v4/core/staging.py for Data Foundry.
Uses JSON file for state persistence with in-memory caching.
Uses DataRecord.record_hash for deduplication with fallback to record_id.
"""

import json
import logging
import sys
from pathlib import Path
from typing import TypedDict

from src.models.data_record import DataRecord

# Platform-specific imports for file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)


class StagingStatistics(TypedDict):
    """Statistics for staging layer"""

    processed_count: int
    staging_directory: str
    state_file: str
    state_file_exists: bool


class StagingLayer:
    """
    Simple staging layer for deduplication with JSON state persistence

    Key features:
    - JSON file state persistence in data_foundry_staging/processed.json
    - In-memory processed_ids set for fast lookups
    - is_duplicate() method to check if record was processed
    - checkpoint() method to mark records as processed (returns bool)
    - checkpoint_single() method to mark single record as processed (returns bool)
    - clear() method to reset all state
    - Auto-creation of staging directory
    - Uses record_hash field for deduplication (falls back to record_id)
    - File locking for concurrent access safety
    - Automatic rollback on save failures
    """

    def __init__(self, staging_dir: str = "data_foundry_staging"):
        """
        Initialize staging layer

        Args:
            staging_dir: Directory for staging state files
        """
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        # JSON file for persistence
        self.state_file = self.staging_dir / "processed.json"

        # In-memory cache for fast lookups
        self.processed_ids: set[str] = set()

        # Load existing state if available
        self._load_state()

        logger.info(
            f"Staging layer initialized with {len(self.processed_ids)} processed IDs"
        )

    def _lock_file(self, file_handle, exclusive: bool = False) -> None:
        """
        Lock a file handle for concurrent access safety

        Args:
            file_handle: Open file handle to lock
            exclusive: True for exclusive lock (write), False for shared (read)
        """
        try:
            if sys.platform == "win32":
                # Windows: use msvcrt.locking
                # For simplicity, we use non-blocking lock with retries
                mode = msvcrt.LK_NBLCK  # Non-blocking lock
                msvcrt.locking(file_handle.fileno(), mode, 1)
            else:
                # Unix/Linux: use fcntl.flock
                flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(file_handle.fileno(), flags)
        except Exception as e:
            logger.warning(f"Failed to acquire file lock: {e}")

    def _unlock_file(self, file_handle) -> None:
        """
        Unlock a file handle

        Args:
            file_handle: Open file handle to unlock
        """
        try:
            if sys.platform == "win32":
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.warning(f"Failed to release file lock: {e}")

    def _get_record_hash(self, record: DataRecord) -> str:
        """
        Get hash for deduplication, using record_hash or falling back to record_id

        Args:
            record: DataRecord to get hash from

        Returns:
            Hash string for deduplication (record_hash if present, else record_id)

        Raises:
            TypeError: If record is not a DataRecord instance
            ValueError: If record has neither record_hash nor record_id
        """
        # Type validation
        if not isinstance(record, DataRecord):
            raise TypeError(
                f"Expected DataRecord, got {type(record).__name__}"
            )

        # Validate we have at least one valid identifier
        hash_val = record.record_hash
        id_val = record.record_id

        if hash_val is None and id_val is None:
            raise ValueError(
                "DataRecord must have either record_hash or record_id"
            )

        # Return hash with fallback to record_id
        return hash_val if hash_val else id_val

    def _load_state(self) -> None:
        """Load processed IDs from JSON file with file locking"""
        try:
            if self.state_file.exists():
                with open(self.state_file, encoding="utf-8") as f:
                    self._lock_file(f, exclusive=False)
                    try:
                        state_data = json.load(f)
                        self.processed_ids = set(
                            state_data.get("processed_ids", [])
                        )
                    finally:
                        self._unlock_file(f)
                logger.info(
                    f"Loaded {len(self.processed_ids)} processed IDs from {self.state_file}"
                )
            else:
                logger.info(
                    f"No existing state file at {self.state_file}, starting fresh"
                )
        except Exception as e:
            logger.warning(f"Failed to load staging state: {e}, starting fresh")
            self.processed_ids = set()

    def _save_state(self) -> bool:
        """
        Save processed IDs to JSON file with file locking

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            state_data = {
                "processed_ids": list(self.processed_ids),
                "count": len(self.processed_ids),
            }

            # Write to temporary file first, then rename to avoid corruption
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                self._lock_file(f, exclusive=True)
                try:
                    json.dump(state_data, f, indent=2)
                finally:
                    self._unlock_file(f)

            temp_file.rename(self.state_file)
            logger.debug(
                f"Saved {len(self.processed_ids)} processed IDs to {self.state_file}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save staging state: {e}")
            return False

    def is_duplicate(self, record: DataRecord) -> bool:
        """
        Check if record has already been processed

        Args:
            record: DataRecord to check

        Returns:
            True if record was already processed, False otherwise

        Raises:
            TypeError: If record is not a DataRecord instance
            ValueError: If record has neither record_hash nor record_id
        """
        return self._get_record_hash(record) in self.processed_ids

    def checkpoint(self, records: list[DataRecord]) -> bool:
        """
        Mark records as processed by adding their hashes to the state

        Args:
            records: List of DataRecords to mark as processed

        Returns:
            True if checkpoint succeeded, False if save failed (memory rolled back)

        Raises:
            TypeError: If any record is not a DataRecord instance
            ValueError: If any record has neither record_hash nor record_id
        """
        new_hashes = [
            self._get_record_hash(r)
            for r in records
            if self._get_record_hash(r) not in self.processed_ids
        ]

        if new_hashes:
            # Save original state for potential rollback
            original_ids = self.processed_ids.copy()
            self.processed_ids.update(new_hashes)

            # Attempt to save state
            if not self._save_state():
                # Rollback memory on save failure
                self.processed_ids = original_ids
                logger.error(
                    f"Checkpoint failed and rolled back for {len(new_hashes)} records"
                )
                return False

            logger.info(
                f"Checkpointed {len(new_hashes)} new records (total: {len(self.processed_ids)})"
            )
        else:
            logger.debug("No new records to checkpoint")

        return True

    def checkpoint_single(self, record: DataRecord) -> bool:
        """
        Mark a single record as processed

        Args:
            record: DataRecord to mark as processed

        Returns:
            True if checkpoint succeeded, False if save failed (memory rolled back)

        Raises:
            TypeError: If record is not a DataRecord instance
            ValueError: If record has neither record_hash nor record_id
        """
        record_hash = self._get_record_hash(record)
        if record_hash not in self.processed_ids:
            self.processed_ids.add(record_hash)

            # Attempt to save state
            if not self._save_state():
                # Rollback memory on save failure
                self.processed_ids.remove(record_hash)
                logger.error(
                    f"Checkpoint_single failed and rolled back for record {record_hash}"
                )
                return False

            logger.debug(f"Checkpointed record {record_hash}")

        return True

    def clear(self) -> None:
        """
        Clear all staging state
        Removes all processed IDs and deletes the state file
        """
        count = len(self.processed_ids)
        self.processed_ids.clear()

        try:
            if self.state_file.exists():
                self.state_file.unlink()
                logger.info(f"Deleted staging state file: {self.state_file}")
        except Exception as e:
            logger.warning(f"Failed to delete staging state file: {e}")

        logger.info(f"Cleared staging state (removed {count} processed IDs)")

    def get_statistics(self) -> StagingStatistics:
        """
        Get staging layer statistics

        Returns:
            StagingStatistics dictionary with:
            - processed_count: Number of processed IDs
            - staging_directory: Path to staging directory
            - state_file: Path to state file
            - state_file_exists: Whether state file exists
        """
        return {
            "processed_count": len(self.processed_ids),
            "staging_directory": str(self.staging_dir),
            "state_file": str(self.state_file),
            "state_file_exists": self.state_file.exists(),
        }
