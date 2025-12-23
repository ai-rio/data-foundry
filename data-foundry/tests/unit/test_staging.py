"""
Tests for staging layer deduplication

Adapted from pipeline-v4/tests/test_staging.py for Data Foundry.
Changed from RedditSubmission to DataRecord model.
Uses record_hash field for deduplication with fallback to record_id.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.staging import StagingLayer
from src.models.data_record import DataRecord, DataSource


@pytest.fixture
def temp_staging_dir():
    """Create a temporary staging directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_data_record():
    """Create a sample DataRecord for testing"""
    return DataRecord(
        record_id="test-record-123",
        record_hash="hash-test-record-123",
        tenant_id="test-tenant",
        data_source=DataSource.API,
        raw_data='{"test": "data"}',
    )


@pytest.fixture
def staging_layer(temp_staging_dir):
    """Create a staging layer instance"""
    return StagingLayer(temp_staging_dir)


def test_staging_init_empty(temp_staging_dir):
    """Test staging initialization with empty state"""
    staging = StagingLayer(temp_staging_dir)
    assert len(staging.processed_ids) == 0
    assert staging.staging_dir == Path(temp_staging_dir)


def test_staging_init_with_existing_state(temp_staging_dir, sample_data_record):
    """Test staging initialization with existing state file"""
    # Create a state file with some processed IDs
    state_file = Path(temp_staging_dir) / "processed.json"
    state_data = {
        "processed_ids": [
            sample_data_record.record_hash,
            "hash-another-record"
        ],
        "count": 2
    }
    with open(state_file, "w") as f:
        json.dump(state_data, f)

    # Initialize staging - should load existing state
    staging = StagingLayer(temp_staging_dir)
    assert len(staging.processed_ids) == 2
    assert sample_data_record.record_hash in staging.processed_ids
    assert "hash-another-record" in staging.processed_ids


def test_is_duplicate(staging_layer, sample_data_record):
    """Test duplicate detection"""
    # Initially not a duplicate
    assert not staging_layer.is_duplicate(sample_data_record)

    # After checkpointing, it should be a duplicate
    staging_layer.checkpoint_single(sample_data_record)
    assert staging_layer.is_duplicate(sample_data_record)


def test_checkpoint_single(staging_layer, sample_data_record):
    """Test checkpointing a single record"""
    record_hash = sample_data_record.record_hash
    assert record_hash not in staging_layer.processed_ids

    staging_layer.checkpoint_single(sample_data_record)
    assert record_hash in staging_layer.processed_ids

    # Check that state file was created
    state_file = staging_layer.state_file
    assert state_file.exists()

    # Verify state file content
    with open(state_file) as f:
        state_data = json.load(f)
        assert record_hash in state_data["processed_ids"]
        assert state_data["count"] == 1


def test_checkpoint_multiple(staging_layer):
    """Test checkpointing multiple records"""
    records = [
        DataRecord(
            record_id=f"test-record-{i}",
            record_hash=f"hash-test-record-{i}",
            tenant_id="test-tenant",
            data_source=DataSource.API,
            raw_data=f'{{"id": {i}}}',
        )
        for i in range(5)
    ]

    # Checkpoint all records
    staging_layer.checkpoint(records)

    # Verify all hashes are in processed set
    for record in records:
        assert record.record_hash in staging_layer.processed_ids

    # Verify state file
    with open(staging_layer.state_file) as f:
        state_data = json.load(f)
        assert state_data["count"] == 5


def test_checkpoint_with_duplicates(staging_layer, sample_data_record):
    """Test checkpointing with duplicate records"""
    # Checkpoint once
    staging_layer.checkpoint_single(sample_data_record)
    initial_count = len(staging_layer.processed_ids)

    # Checkpoint again - should not increase count
    staging_layer.checkpoint_single(sample_data_record)
    assert len(staging_layer.processed_ids) == initial_count


def test_clear(staging_layer, sample_data_record):
    """Test clearing staging state"""
    # Add a record
    staging_layer.checkpoint_single(sample_data_record)
    assert len(staging_layer.processed_ids) == 1
    assert staging_layer.state_file.exists()

    # Clear state
    staging_layer.clear()

    # Verify everything is cleared
    assert len(staging_layer.processed_ids) == 0
    assert not staging_layer.state_file.exists()


def test_get_statistics(staging_layer, sample_data_record):
    """Test getting staging statistics"""
    # Initially empty
    stats = staging_layer.get_statistics()
    assert stats["processed_count"] == 0
    assert stats["state_file_exists"] is False

    # After adding a record
    staging_layer.checkpoint_single(sample_data_record)
    stats = staging_layer.get_statistics()
    assert stats["processed_count"] == 1
    assert stats["state_file_exists"] is True
    assert str(staging_layer.staging_dir) in stats["staging_directory"]


def test_corrupted_state_file_handling(temp_staging_dir):
    """Test handling of corrupted state file"""
    # Create a corrupted JSON file
    state_file = Path(temp_staging_dir) / "processed.json"
    with open(state_file, "w") as f:
        f.write("invalid json content")

    # Initialize staging - should handle gracefully
    staging = StagingLayer(temp_staging_dir)
    assert len(staging.processed_ids) == 0  # Should start fresh


def test_auto_create_directory():
    """Test that staging directory is auto-created"""
    with tempfile.TemporaryDirectory() as tmpdir:
        staging_dir = Path(tmpdir) / "subdir" / "data_foundry_staging"
        assert not staging_dir.exists()

        staging = StagingLayer(str(staging_dir))
        assert staging_dir.exists()
        assert staging_dir.is_dir()


def test_fallback_to_record_id_when_hash_missing():
    """Test that staging falls back to record_id when record_hash is None"""
    staging = StagingLayer(tempfile.mkdtemp())

    # Create record without record_hash
    record = DataRecord(
        record_id="test-record-no-hash",
        record_hash=None,
        tenant_id="test-tenant",
        data_source=DataSource.MANUAL,
        raw_data='{"test": "no hash"}',
    )

    # Should use record_id as fallback
    assert not staging.is_duplicate(record)
    staging.checkpoint_single(record)
    assert staging.is_duplicate(record)
    assert record.record_id in staging.processed_ids


# ----------------------------------------------------------------------
# New tests for P0 and P1 fixes
# ----------------------------------------------------------------------


def test_checkpoint_returns_true_on_success(staging_layer, sample_data_record):
    """Test checkpoint returns True on successful save"""
    result = staging_layer.checkpoint([sample_data_record])
    assert result is True


def test_checkpoint_returns_false_on_save_failure(staging_layer, sample_data_record):
    """Test checkpoint returns False and rolls back memory on save failure"""
    # Mock _save_state to return False (simulating save failure)
    with patch.object(staging_layer, '_save_state', return_value=False):
        result = staging_layer.checkpoint([sample_data_record])

        # Should return False
        assert result is False

        # Memory should be rolled back - hash should NOT be in processed_ids
        assert sample_data_record.record_hash not in staging_layer.processed_ids


def test_checkpoint_single_returns_true_on_success(staging_layer, sample_data_record):
    """Test checkpoint_single returns True on successful save"""
    result = staging_layer.checkpoint_single(sample_data_record)
    assert result is True


def test_checkpoint_single_returns_false_on_save_failure(staging_layer, sample_data_record):
    """Test checkpoint_single returns False and rolls back memory on save failure"""
    # Mock _save_state to return False (simulating save failure)
    with patch.object(staging_layer, '_save_state', return_value=False):
        result = staging_layer.checkpoint_single(sample_data_record)

        # Should return False
        assert result is False

        # Memory should be rolled back
        assert sample_data_record.record_hash not in staging_layer.processed_ids


def test_checkpoint_single_rollback_preserves_existing_records(staging_layer):
    """Test that rollback on checkpoint_single failure preserves existing records"""
    # First, successfully add a record
    record1 = DataRecord(
        record_id="record-1",
        record_hash="hash-1",
        tenant_id="test",
        data_source=DataSource.API,
        raw_data="{}",
    )
    staging_layer.checkpoint_single(record1)
    assert "hash-1" in staging_layer.processed_ids

    # Now try to add another record but simulate save failure
    record2 = DataRecord(
        record_id="record-2",
        record_hash="hash-2",
        tenant_id="test",
        data_source=DataSource.API,
        raw_data="{}",
    )
    with patch.object(staging_layer, '_save_state', return_value=False):
        staging_layer.checkpoint_single(record2)

    # First record should still be there
    assert "hash-1" in staging_layer.processed_ids
    # Second record should not be there (rolled back)
    assert "hash-2" not in staging_layer.processed_ids


def test_checkpoint_rollback_preserves_existing_records(staging_layer):
    """Test that rollback on checkpoint failure preserves existing records"""
    # First, successfully add some records
    records1 = [
        DataRecord(
            record_id=f"record-{i}",
            record_hash=f"hash-{i}",
            tenant_id="test",
            data_source=DataSource.API,
            raw_data="{}",
        )
        for i in range(3)
    ]
    staging_layer.checkpoint(records1)
    assert len(staging_layer.processed_ids) == 3

    # Now try to add more records but simulate save failure
    records2 = [
        DataRecord(
            record_id=f"new-record-{i}",
            record_hash=f"new-hash-{i}",
            tenant_id="test",
            data_source=DataSource.API,
            raw_data="{}",
        )
        for i in range(2)
    ]
    with patch.object(staging_layer, '_save_state', return_value=False):
        staging_layer.checkpoint(records2)

    # Original records should still be there
    assert len(staging_layer.processed_ids) == 3
    for r in records1:
        assert r.record_hash in staging_layer.processed_ids
    # New records should not be there (rolled back)
    for r in records2:
        assert r.record_hash not in staging_layer.processed_ids


def test_get_record_hash_invalid_type(staging_layer):
    """Test _get_record_hash raises TypeError for non-DataRecord"""
    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer._get_record_hash("not a record")

    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer._get_record_hash(None)

    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer._get_record_hash({"record_id": "test"})


def test_get_record_hash_missing_identifiers(staging_layer):
    """Test _get_record_hash raises ValueError when both hash and id are None"""
    # Create a record with both record_hash and record_id as None
    # This is an invalid record that shouldn't exist in normal usage
    class InvalidRecord:
        record_hash = None
        record_id = None

    invalid_record = InvalidRecord()

    # First check that it passes isinstance check if we patch it
    # But the real test is that DataRecord with None values raises ValueError
    record = DataRecord(
        record_id=None,
        record_hash=None,
        tenant_id="test",
        data_source=DataSource.MANUAL,
        raw_data="{}",
    )

    # Since DataRecord allows None values, we test the validation logic
    # by directly calling the method
    with pytest.raises(ValueError, match="must have either record_hash or record_id"):
        staging_layer._get_record_hash(record)


def test_is_duplicate_with_invalid_type(staging_layer):
    """Test is_duplicate raises TypeError for non-DataRecord"""
    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer.is_duplicate("not a record")


def test_checkpoint_with_invalid_type(staging_layer):
    """Test checkpoint raises TypeError for non-DataRecord items"""
    # This test verifies type validation in the _get_record_hash method
    # which is called by checkpoint

    # Create one valid record
    valid_record = DataRecord(
        record_id="valid",
        record_hash="hash-valid",
        tenant_id="test",
        data_source=DataSource.API,
        raw_data="{}",
    )

    # Create an invalid item (not a DataRecord)
    invalid_item = {"record_id": "invalid"}

    # checkpoint should raise TypeError when processing invalid_item
    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer.checkpoint([valid_record, invalid_item])


def test_checkpoint_single_with_invalid_type(staging_layer):
    """Test checkpoint_single raises TypeError for non-DataRecord"""
    with pytest.raises(TypeError, match="Expected DataRecord"):
        staging_layer.checkpoint_single("not a record")


def test_checkpoint_duplicate_no_save_call(staging_layer, sample_data_record):
    """Test that checkpointing duplicate records doesn't call save"""
    # Checkpoint once
    staging_layer.checkpoint_single(sample_data_record)

    # Mock _save_state to track if it's called
    with patch.object(staging_layer, '_save_state', return_value=True) as mock_save:
        # Checkpoint same record again
        result = staging_layer.checkpoint([sample_data_record])

        # Should succeed without calling save (already in set)
        assert result is True
        mock_save.assert_not_called()


def test_checkpoint_single_duplicate_no_save_call(staging_layer, sample_data_record):
    """Test that checkpoint_single on duplicate doesn't call save"""
    # Checkpoint once
    staging_layer.checkpoint_single(sample_data_record)

    # Mock _save_state to track if it's called
    with patch.object(staging_layer, '_save_state', return_value=True) as mock_save:
        # Checkpoint same record again
        result = staging_layer.checkpoint_single(sample_data_record)

        # Should succeed without calling save (already in set)
        assert result is True
        mock_save.assert_not_called()


def test_get_statistics_returns_typed_dict(staging_layer, sample_data_record):
    """Test get_statistics returns properly typed dictionary"""
    stats = staging_layer.get_statistics()

    # Verify all required keys are present
    assert "processed_count" in stats
    assert "staging_directory" in stats
    assert "state_file" in stats
    assert "state_file_exists" in stats

    # Verify types
    assert isinstance(stats["processed_count"], int)
    assert isinstance(stats["staging_directory"], str)
    assert isinstance(stats["state_file"], str)
    assert isinstance(stats["state_file_exists"], bool)

    # After adding a record
    staging_layer.checkpoint_single(sample_data_record)
    stats = staging_layer.get_statistics()
    assert stats["processed_count"] == 1
    assert stats["state_file_exists"] is True


def test_checkpoint_empty_list(staging_layer):
    """Test checkpoint with empty list"""
    result = staging_layer.checkpoint([])
    assert result is True  # Empty list is a no-op, should succeed


def test_checkpoint_all_duplicates(staging_layer, sample_data_record):
    """Test checkpoint with all duplicate records"""
    # First checkpoint the record
    staging_layer.checkpoint_single(sample_data_record)

    # Now checkpoint the same record again in a list
    result = staging_layer.checkpoint([sample_data_record])
    assert result is True

    # Count should still be 1
    assert len(staging_layer.processed_ids) == 1
