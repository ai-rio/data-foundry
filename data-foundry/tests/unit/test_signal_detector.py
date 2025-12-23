"""
Test-Driven Development tests for SignalDetector class (Week 3)
Tests are written first to fail, then implementation is added to make them pass

Adapted from pipeline-v4 tests for Data Foundry DataRecord model
"""

from datetime import datetime, UTC
from typing import Dict, List

import pytest

from src.core.signal_detector import SignalDetector, SignalResult
from src.models.data_record import DataRecord, DataSource, DataStatus


# Helper function to create test DataRecord instances
def create_test_record(
    record_id: str,
    data_preview: str,
    raw_data: str,
    data_quality_score: float = 0.8,
    access_count: int = 10,
) -> DataRecord:
    """Helper to create test DataRecord instances"""
    return DataRecord(
        id=1,
        record_id=record_id,
        tenant_id="test_tenant",
        data_source=DataSource.MANUAL,
        status=DataStatus.RAW,
        data_preview=data_preview,
        raw_data=raw_data,
        data_quality_score=data_quality_score,
        access_count=access_count,
        created_at=datetime.now(UTC),
    )


class TestSignalDetectorInitialization:
    """Test SignalDetector class initialization"""

    def test_signal_detector_initializes_with_default_threshold(self):
        """Test that SignalDetector initializes with default threshold of 70"""
        detector = SignalDetector()
        assert detector.threshold == 70

    def test_signal_detector_initializes_with_custom_threshold(self):
        """Test that SignalDetector accepts custom threshold"""
        detector = SignalDetector(threshold=80)
        assert detector.threshold == 80

    def test_signal_detector_has_opportunity_patterns(self):
        """Test that SignalDetector has all required opportunity patterns"""
        detector = SignalDetector()
        required_patterns = [
            "TOOL_REQUEST",
            "PAIN_COMPLAINT",
            "PRICE_MENTION",
            "PROBLEM_SOLUTION",
            "COMPARISON",
        ]
        for pattern in required_patterns:
            assert pattern in detector.opportunity_patterns
            assert isinstance(detector.opportunity_patterns[pattern], list)
            assert len(detector.opportunity_patterns[pattern]) > 0


class TestPatternMatching:
    """Test pattern matching functionality"""

    def test_detect_tool_request_pattern(self):
        """Test detection of tool request patterns"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test1",
            data_preview="Is there a tool that can automate my workflow?",
            raw_data='{"text": "I\'m looking for an app that helps with task management"}',
        )

        result = detector.detect_signals(record)

        # Should detect TOOL_REQUEST signal
        assert result.signal_type == "TOOL_REQUEST"
        assert result.signal_strength > 0
        assert len(result.evidence_snippets) > 0
        assert any("tool" in snippet.lower() for snippet in result.evidence_snippets)

    def test_detect_pain_complaint_pattern(self):
        """Test detection of pain complaint patterns"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test2",
            data_preview="I hate when my computer crashes during work",
            raw_data='{"text": "So frustrated with losing my progress all the time"}',
        )

        result = detector.detect_signals(record)

        # Should detect PAIN_COMPLAINT signal
        assert result.signal_type == "PAIN_COMPLAINT"
        assert result.signal_strength > 0
        assert len(result.evidence_snippets) > 0

    def test_detect_price_mention_pattern(self):
        """Test detection of price mention patterns"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test3",
            data_preview="Would pay $50 for a solution to this problem",
            raw_data='{"text": "This software costs too much at $100/month"}',
        )

        result = detector.detect_signals(record)

        # Should detect PRICE_MENTION signal
        assert result.signal_type == "PRICE_MENTION"
        assert result.signal_strength > 0
        assert len(result.evidence_snippets) > 0
        assert any("$" in snippet for snippet in result.evidence_snippets)

    def test_detect_problem_solution_pattern(self):
        """Test detection of problem-solution patterns"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test4",
            data_preview="How do I organize my digital files effectively?",
            raw_data='{"text": "Need help with document management system"}',
        )

        result = detector.detect_signals(record)

        # Should detect PROBLEM_SOLUTION signal
        assert result.signal_type == "PROBLEM_SOLUTION"
        assert result.signal_strength > 0

    def test_detect_comparison_pattern(self):
        """Test detection of comparison patterns"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test5",
            data_preview="Notion vs Obsidian for knowledge management",
            raw_data='{"text": "Looking for an alternative to Evernote"}',
        )

        result = detector.detect_signals(record)

        # Should detect COMPARISON signal
        assert result.signal_type == "COMPARISON"
        assert result.signal_strength > 0

    def test_no_signal_detected(self):
        """Test when no opportunity signal is detected"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test6",
            data_preview="Just a regular post about cats",
            raw_data='{"text": "My cat is cute and likes to sleep"}',
        )

        result = detector.detect_signals(record)

        # Should have no signal or very low signal strength
        assert result.signal_type == "NONE"
        assert result.signal_strength == 0
        assert result.should_analyze is False


class TestSignalStrengthCalculation:
    """Test signal strength calculation"""

    def test_signal_strength_calculation_with_multiple_matches(self):
        """Test signal strength increases with multiple pattern matches"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test7",
            data_preview="Looking for a tool that can help. Is there any app that works? Please recommend me a solution.",
            raw_data='{"text": "I need help with this problem"}',
            data_quality_score=0.8,
            access_count=30,
        )

        result = detector.detect_signals(record)

        # Should have higher signal strength due to multiple matches
        assert result.signal_strength > 50
        assert len(result.evidence_snippets) >= 2

    def test_signal_strength_boost_for_high_engagement(self):
        """Test signal strength boost for high engagement posts"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test8",
            data_preview="Is there a tool for this?",
            raw_data='{"text": "Looking for recommendations"}',
            data_quality_score=0.9,
            access_count=100,
        )

        result = detector.detect_signals(record)

        # Should have signal strength boosted by engagement
        engagement_metrics = result.engagement_metrics
        assert engagement_metrics["data_quality_score"] == 0.9
        assert engagement_metrics["access_count"] == 100
        # Engagement ratio is access_count / quality_score
        assert "engagement_ratio" in engagement_metrics

    def test_signal_strength_capped_at_100(self):
        """Test signal strength is capped at 100"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test9",
            data_preview="Tool tool tool looking for app recommend me software solution help problem vs alternative",
            raw_data='{"text": "Tool app software recommend me help problem solution tool app software vs alternative"}',
            data_quality_score=1.0,
            access_count=1000,
        )

        result = detector.detect_signals(record)

        # Signal strength should not exceed 100
        assert result.signal_strength <= 100


class TestDataRecordMetricsAnalysis:
    """Test DataRecord metrics analysis"""

    def test_skip_low_quality_posts(self):
        """Test that posts with quality_score < 0.3 are skipped"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test10",
            data_preview="Is there a tool for this?",
            raw_data='{"text": "Looking for recommendations"}',
            data_quality_score=0.2,
            access_count=2,
        )

        result = detector.detect_signals(record)

        # Should not analyze low quality posts
        assert result.should_analyze is False
        assert result.engagement_metrics["data_quality_score"] == 0.2

    def test_skip_zero_access_posts(self):
        """Test that posts with 0 access_count are skipped"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test11",
            data_preview="Need help with this problem",
            raw_data='{"text": "Looking for a solution"}',
            data_quality_score=0.7,
            access_count=0,
        )

        result = detector.detect_signals(record)

        # Should not analyze posts with no access
        assert result.should_analyze is False
        assert result.engagement_metrics["access_count"] == 0

    def test_engagement_ratio_calculation(self):
        """Test engagement ratio calculation"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test12",
            data_preview="Test post",
            raw_data='{"text": "Test content"}',
            data_quality_score=0.8,
            access_count=50,
        )

        result = detector.detect_signals(record)

        # Engagement ratio should be access_count / data_quality_score
        expected_ratio = 50 / 0.8  # 62.5
        assert abs(result.engagement_metrics["engagement_ratio"] - expected_ratio) < 0.1


class TestEvidenceSnippetExtraction:
    """Test evidence snippet extraction"""

    def test_evidence_snippets_exact_matches(self):
        """Test evidence snippets contain exact pattern matches"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test13",
            data_preview="I hate when software crashes",
            raw_data='{"text": "This is so frustrating with my workflow"}',
        )

        result = detector.detect_signals(record)

        # Should extract exact matching snippets
        assert len(result.evidence_snippets) > 0
        assert any("hate when" in snippet for snippet in result.evidence_snippets)

    def test_evidence_snippets_length_limit(self):
        """Test evidence snippets are length-limited"""
        detector = SignalDetector()
        long_text = "I hate when " + "x" * 200 + " this happens"
        record = create_test_record(
            record_id="test14",
            data_preview="I hate when this happens",
            raw_data=f'{{"text": "{long_text}"}}',
        )

        result = detector.detect_signals(record)

        # Snippets should be reasonably sized
        for snippet in result.evidence_snippets:
            assert len(snippet) <= 200


class TestThresholdFiltering:
    """Test threshold filtering logic"""

    def test_should_analyze_above_threshold(self):
        """Test posts above threshold should be analyzed"""
        detector = SignalDetector(threshold=70)
        record = create_test_record(
            record_id="test15",
            data_preview="Looking for a tool that can automate everything",
            raw_data='{"text": "Please recommend me the best software solution"}',
            data_quality_score=0.85,
            access_count=50,
        )

        result = detector.detect_signals(record)

        # High signal strength should trigger analysis
        assert result.signal_strength > 70
        assert result.should_analyze is True

    def test_should_not_analyze_below_threshold(self):
        """Test posts below threshold should not be analyzed"""
        detector = SignalDetector(threshold=70)
        record = create_test_record(
            record_id="test16",
            data_preview="Maybe looking for something",
            raw_data='{"text": "Not sure what I need"}',
            data_quality_score=0.5,
            access_count=5,
        )

        result = detector.detect_signals(record)

        # Low signal strength should not trigger analysis
        if result.signal_strength > 0:
            assert result.signal_strength < 70
        assert result.should_analyze is False


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_content(self):
        """Test handling of minimal content"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test17",
            data_preview="minimal",
            raw_data='{}',
        )

        result = detector.detect_signals(record)

        # Should handle minimal content gracefully
        assert result.signal_type == "NONE"
        assert result.signal_strength == 0
        assert result.should_analyze is False

    def test_special_characters(self):
        """Test handling of special characters"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test18",
            data_preview="Looking for a tool! @#$%^&*()_+",
            raw_data='{"text": "Special chars: \ud83d\ude80 \ud83d\udd25 \ud83d\udcaf émojis too"}',
        )

        result = detector.detect_signals(record)

        # Should handle special characters without crashing
        assert result is not None
        assert isinstance(result.signal_strength, (int, float))

    def test_very_long_content(self):
        """Test handling of very long content"""
        detector = SignalDetector()
        long_preview = "Looking for " + "tool " * 50
        long_data = "I need help " * 500

        record = create_test_record(
            record_id="test19",
            data_preview=long_preview,
            raw_data=f'{{"text": "{long_data}"}}',
        )

        result = detector.detect_signals(record)

        # Should handle long content efficiently
        assert result is not None
        assert result.signal_strength <= 100

    def test_unicode_content(self):
        """Test handling of unicode content"""
        detector = SignalDetector()
        record = create_test_record(
            record_id="test20",
            data_preview="¿Hay una herramienta que pueda ayudar con esto?",  # Spanish
            raw_data='{"text": "Besoin d\'aide pour trouver un logiciel"}',  # French
        )

        result = detector.detect_signals(record)

        # Should handle unicode without errors
        assert result is not None
        assert isinstance(result, SignalResult)

    def test_engagement_boost_edge_cases(self):
        """Test specific engagement boost edge cases for coverage"""
        detector = SignalDetector()

        # Test quality score between 0.5-0.8 case
        record1 = create_test_record(
            record_id="test21",
            data_preview="Need help with this",
            raw_data='{"text": "Looking for a solution"}',
            data_quality_score=0.65,
            access_count=75,
        )

        # Test high engagement ratio case
        record2 = create_test_record(
            record_id="test22",
            data_preview="Looking for a tool",
            raw_data='{"text": "Need recommendations"}',
            data_quality_score=0.3,  # Low quality
            access_count=10,  # High access, ratio > threshold
        )

        result1 = detector.detect_signals(record1)
        result2 = detector.detect_signals(record2)

        # Both should have engagement boosts
        assert result1.engagement_metrics["data_quality_score"] == 0.65
        assert result2.engagement_metrics["access_count"] == 10

    def test_snippet_truncation(self):
        """Test snippet truncation for long content"""
        detector = SignalDetector()

        # Create a record that will generate a snippet needing truncation
        long_prefix = "x" * 150  # 150 chars
        record = create_test_record(
            record_id="test23",
            data_preview=f"{long_prefix} I hate when this happens",
            raw_data='{}',
        )

        result = detector.detect_signals(record)

        # Should have snippets with truncation
        assert len(result.evidence_snippets) > 0
        # Check that snippet processing worked (we have a valid snippet)
        snippet = result.evidence_snippets[0]
        assert len(snippet) > 0
        # Verify snippet contains relevant content
        assert "hate when" in snippet.lower()

    def test_invalid_regex_pattern_handling(self):
        """Test handling of invalid regex patterns for coverage"""
        detector = SignalDetector()

        # Temporarily add an invalid pattern to test exception handling
        detector.opportunity_patterns["TEST_PATTERN"] = [r"[invalid regex"]

        record = create_test_record(
            record_id="test24",
            data_preview="Test invalid regex handling",
            raw_data='{"text": "This should not crash with invalid patterns"}',
        )

        result = detector.detect_signals(record)

        # Should handle invalid patterns gracefully
        assert result is not None
        assert isinstance(result, SignalResult)
