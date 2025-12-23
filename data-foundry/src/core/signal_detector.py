"""
SignalDetector class for pre-filtering data records to identify opportunity signals
Uses pattern matching and data quality metrics to avoid wasting LLM calls on irrelevant content

Adapted from pipeline-v4 for Data Foundry DataRecord model

Features:
- Pre-compiled regex patterns for performance
- Comprehensive structlog logging for production monitoring
- Input validation with detailed error messages
- Pattern validation at initialization
"""

import re
import json
import logging.config
from typing import Dict, List, Optional, Any, Pattern
from pathlib import Path

from pydantic import BaseModel, Field
import structlog

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

from src.models.data_record import DataRecord


class SignalResult(BaseModel):
    """Result of signal detection analysis"""

    signal_type: str = Field(description="Signal type: TOOL_REQUEST, PAIN_COMPLAINT, PRICE_MENTION, etc.")
    signal_strength: float = Field(description="Signal strength score 0-100")
    evidence_snippets: List[str] = Field(default_factory=list, description="Exact text matches")
    engagement_metrics: Dict[str, Any] = Field(default_factory=dict, description="Data quality and access metrics")
    should_analyze: bool = Field(description="True if strength > threshold")


class SignalDetector:
    """
    Detects opportunity signals in DataRecord instances using pattern matching
    and data quality metrics to determine if LLM analysis is warranted

    Adapted from pipeline-v4 SignalDetector for Data Foundry:
    - RedditSubmission.title -> DataRecord.data_preview
    - RedditSubmission.text -> DataRecord.raw_data/extracted_text
    - RedditSubmission.score -> DataRecord.data_quality_score
    - RedditSubmission.comments_count -> DataRecord.access_count

    Performance:
    - Pre-compiled regex patterns (no recompilation on each call)
    - Early termination for low-quality records
    - Efficient text extraction with caching
    """

    # Default signal patterns (raw strings for validation)
    DEFAULT_OPPORTUNITY_PATTERNS: Dict[str, List[str]] = {
        "TOOL_REQUEST": [
            r"is there a (tool|app|software)",
            r"looking for (a tool|an app|software)",
            r"does anyone know of a",
            r"recommend me a",
        ],
        "PAIN_COMPLAINT": [
            r"i hate when",
            r"frustrated with",
            r"can\'t stand",
            r"why is it so hard to",
            r"struggling with",
        ],
        "PRICE_MENTION": [
            r"\$\d+",
            r"would pay for",
            r"willing to pay",
            r"cost too much",
            r"not worth \$.+",
        ],
        "PROBLEM_SOLUTION": [
            r"how do i",
            r"need help with",
            r"any way to",
            r"solution for",
        ],
        "COMPARISON": [
            r"vs",
            r"alternative to",
            r"better than",
            r"instead of",
        ],
    }

    # Strong indicator patterns for scoring
    STRONG_PATTERNS = [
        r"recommend",
        r"looking for",
        r"frustrated",
        r"hate when",
        r"urgent",
        r"desperate",
    ]

    def __init__(
        self,
        threshold: float = 70,
        opportunity_patterns: Optional[Dict[str, List[str]]] = None
    ):
        """
        Initialize SignalDetector with analysis threshold

        Args:
            threshold: Signal strength threshold for analysis (0-100)
            opportunity_patterns: Custom opportunity patterns (optional)

        Raises:
            ValueError: If threshold is out of valid range or patterns are invalid
        """
        # Validate threshold
        if not 0 <= threshold <= 100:
            raise ValueError(f"Threshold must be between 0 and 100, got {threshold}")

        self.threshold = threshold

        # Use custom patterns or defaults
        raw_patterns = opportunity_patterns or self.DEFAULT_OPPORTUNITY_PATTERNS

        # Pre-compile all regex patterns at initialization
        self.opportunity_patterns: Dict[str, List[Pattern]] = self._compile_patterns(raw_patterns)

        # Pre-compile strong indicator patterns
        self._strong_pattern_regexes = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.STRONG_PATTERNS
        ]

        logger.info(
            "SignalDetector_initialized",
            threshold=threshold,
            pattern_types=list(self.opportunity_patterns.keys()),
            n_patterns=sum(len(patterns) for patterns in self.opportunity_patterns.values()),
        )

    def _compile_patterns(self, raw_patterns: Dict[str, List[str]]) -> Dict[str, List[Pattern]]:
        """
        Pre-compile regex patterns for performance.

        Args:
            raw_patterns: Dictionary of signal type to list of pattern strings

        Returns:
            Dictionary of signal type to list of compiled Pattern objects

        Raises:
            ValueError: If any pattern is invalid
        """
        compiled = {}
        invalid_patterns = []

        for signal_type, pattern_strings in raw_patterns.items():
            compiled_patterns = []
            for pattern_str in pattern_strings:
                try:
                    compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
                    compiled_patterns.append(compiled_pattern)
                except re.error as e:
                    invalid_patterns.append({
                        "signal_type": signal_type,
                        "pattern": pattern_str,
                        "error": str(e)
                    })
                    logger.warning(
                        "invalid_pattern_skipped",
                        signal_type=signal_type,
                        pattern=pattern_str,
                        error=str(e),
                    )

            if compiled_patterns:
                compiled[signal_type] = compiled_patterns
            else:
                logger.warning(
                    "no_valid_patterns_for_signal_type",
                    signal_type=signal_type,
                )

        if invalid_patterns:
            logger.warning(
                "some_patterns_invalid",
                n_invalid=len(invalid_patterns),
                invalid=invalid_patterns,
            )

        if not compiled:
            raise ValueError(
                f"No valid patterns found. All {len(invalid_patterns)} patterns failed to compile."
            )

        return compiled

    def detect_signals(self, record: DataRecord) -> SignalResult:
        """
        Analyze a DataRecord for opportunity signals

        Args:
            record: DataRecord to analyze

        Returns:
            SignalResult with analysis details

        Raises:
            ValueError: If record is None or invalid
        """
        # Input validation
        if record is None:
            raise ValueError("Record cannot be None")

        logger.debug(
            "detect_signals_called",
            record_id=str(record.id) if hasattr(record, 'id') else "unknown",
            data_source=str(record.data_source) if hasattr(record, 'data_source') else "unknown",
        )

        # Calculate engagement metrics
        engagement_metrics = self._calculate_engagement_metrics(record)

        # Skip low-quality or low-engagement records
        quality_score = record.data_quality_score or 0.0
        access_count = record.access_count or 0

        logger.debug(
            "quality_check",
            quality_score=quality_score,
            access_count=access_count,
            threshold=0.3,
        )

        if quality_score < 0.3 or access_count == 0:
            logger.info(
                "record_filtered_low_quality",
                quality_score=quality_score,
                access_count=access_count,
                reason="Below quality threshold",
            )
            return SignalResult(
                signal_type="NONE",
                signal_strength=0,
                evidence_snippets=[],
                engagement_metrics=engagement_metrics,
                should_analyze=False,
            )

        # Extract text content from record
        content = self._extract_text_content(record)

        if not content or len(content.strip()) < 10:
            logger.info(
                "record_filtered_no_content",
                content_length=len(content) if content else 0,
                reason="Insufficient text content",
            )
            return SignalResult(
                signal_type="NONE",
                signal_strength=0,
                evidence_snippets=[],
                engagement_metrics=engagement_metrics,
                should_analyze=False,
            )

        # Find all signal matches
        signal_matches = self._find_signal_matches(content)

        if not signal_matches:
            logger.info(
                "no_signals_detected",
                content_length=len(content),
            )
            return SignalResult(
                signal_type="NONE",
                signal_strength=0,
                evidence_snippets=[],
                engagement_metrics=engagement_metrics,
                should_analyze=False,
            )

        # Calculate signal strength
        signal_type = max(signal_matches.keys(), key=lambda k: len(signal_matches[k]))
        base_strength = self._calculate_base_strength(
            signal_matches[signal_type], content
        )
        engagement_boost = self._calculate_engagement_boost(engagement_metrics)

        # Combine and cap signal strength
        signal_strength = min(100, base_strength + engagement_boost)

        # Extract evidence snippets
        evidence_snippets = self._extract_evidence_snippets(
            signal_matches[signal_type], self._extract_text_content(record, original_case=True)
        )

        # Determine if should analyze
        should_analyze = signal_strength >= self.threshold

        logger.info(
            "signal_detection_complete",
            signal_type=signal_type,
            signal_strength=signal_strength,
            should_analyze=should_analyze,
            threshold=self.threshold,
            n_evidence=len(evidence_snippets),
        )

        return SignalResult(
            signal_type=signal_type,
            signal_strength=signal_strength,
            evidence_snippets=evidence_snippets,
            engagement_metrics=engagement_metrics,
            should_analyze=should_analyze,
        )

    def _extract_text_content(self, record: DataRecord, original_case: bool = False) -> str:
        """
        Extract text content from DataRecord

        Args:
            record: DataRecord to extract text from
            original_case: If True, preserve original case; otherwise lowercase

        Returns:
            Combined text content
        """
        if record is None:
            logger.warning("extract_text_content_called_with_none_record")
            return ""

        parts = []

        # Add data_preview (analogous to RedditSubmission.title)
        if record.data_preview:
            parts.append(record.data_preview)

        # Add extracted_text if available
        if record.extracted_text:
            parts.append(record.extracted_text)
        else:
            # Try to extract text from raw_data (JSON)
            if record.raw_data:
                try:
                    raw_dict = json.loads(record.raw_data)
                    # Look for common text fields
                    for key in ["text", "content", "description", "message", "body"]:
                        if key in raw_dict and raw_dict[key]:
                            parts.append(str(raw_dict[key]))
                            break
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(
                        "raw_data_not_json",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # If not JSON, use raw_data as-is
                    parts.append(record.raw_data)

        content = " ".join(parts)
        result = content if original_case else content.lower()

        logger.debug(
            "text_extracted",
            length=len(result),
            n_parts=len(parts),
            original_case=original_case,
        )

        return result

    def _calculate_engagement_metrics(self, record: DataRecord) -> Dict:
        """
        Calculate engagement metrics from DataRecord

        Args:
            record: DataRecord to calculate metrics from

        Returns:
            Dictionary with engagement metrics
        """
        if record is None:
            logger.warning("calculate_engagement_metrics_called_with_none_record")
            return {
                "data_quality_score": 0.0,
                "access_count": 0,
                "engagement_ratio": 0.0,
            }

        quality_score = record.data_quality_score or 0.0
        access_count = record.access_count or 0

        # Engagement ratio: access_count per quality_score unit
        engagement_ratio = access_count / max(0.1, quality_score)

        metrics = {
            "data_quality_score": quality_score,
            "access_count": access_count,
            "engagement_ratio": engagement_ratio,
        }

        logger.debug(
            "engagement_metrics_calculated",
            **metrics,
        )

        return metrics

    def _find_signal_matches(self, content: str) -> Dict[str, List[re.Match]]:
        """
        Find all pattern matches in content using pre-compiled patterns

        Args:
            content: Text content to search

        Returns:
            Dictionary mapping signal type to list of matches
        """
        if not content:
            logger.debug("find_signal_matches_called_with_empty_content")
            return {}

        signal_matches = {}

        for signal_type, compiled_patterns in self.opportunity_patterns.items():
            matches = []
            for pattern in compiled_patterns:
                try:
                    pattern_matches = list(pattern.finditer(content))
                    matches.extend(pattern_matches)
                except Exception as e:
                    logger.error(
                        "pattern_match_failed",
                        signal_type=signal_type,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            if matches:
                signal_matches[signal_type] = matches

        if signal_matches:
            logger.debug(
                "signals_found",
                n_types=len(signal_matches),
                n_matches=sum(len(m) for m in signal_matches.values()),
            )

        return signal_matches

    def _calculate_base_strength(self, matches: List[re.Match], content: str) -> float:
        """
        Calculate base signal strength from pattern matches

        Args:
            matches: List of regex match objects
            content: Full content text

        Returns:
            Base strength score (0-100)
        """
        if not matches:
            return 0

        # Start with higher base strength for better threshold performance
        base_strength = 40

        # Add strength for multiple matches
        match_bonus = min(30, len(matches) * 15)
        base_strength += match_bonus

        # Add strength for pattern density (matches per 100 chars)
        density = (len(matches) * 100) / max(1, len(content))
        density_bonus = min(20, density * 2)
        base_strength += density_bonus

        # Add strength for strong indicators using pre-compiled patterns
        for match in matches:
            match_text = match.group(0).lower()
            for strong_pattern in self._strong_pattern_regexes:
                if strong_pattern.search(match_text):
                    base_strength += 10
                    break

        result = min(100, base_strength)

        logger.debug(
            "base_strength_calculated",
            result=result,
            n_matches=len(matches),
            density=density,
        )

        return result

    def _calculate_engagement_boost(self, engagement_metrics: Dict) -> float:
        """
        Calculate engagement boost to signal strength

        Args:
            engagement_metrics: Dictionary with engagement metrics

        Returns:
            Engagement boost score (0-20)
        """
        quality_score = engagement_metrics.get("data_quality_score", 0)
        access_count = engagement_metrics.get("access_count", 0)
        engagement_ratio = engagement_metrics.get("engagement_ratio", 0)

        boost = 0

        # Boost for high quality score
        if quality_score > 0.9:
            boost += 10
        elif quality_score > 0.8:
            boost += 5
        elif quality_score > 0.5:
            boost += 3

        # Boost for high access count
        if access_count > 100:
            boost += 10
        elif access_count > 50:
            boost += 5
        elif access_count > 25:
            boost += 3

        # Boost for high engagement ratio
        if engagement_ratio > 100:
            boost += 5
        elif engagement_ratio > 50:
            boost += 3

        result = min(20, boost)

        logger.debug(
            "engagement_boost_calculated",
            result=result,
            quality_score=quality_score,
            access_count=access_count,
            engagement_ratio=engagement_ratio,
        )

        return result

    def _extract_evidence_snippets(
        self, matches: List[re.Match], original_content: str
    ) -> List[str]:
        """
        Extract evidence snippets from matched content

        Args:
            matches: List of regex match objects
            original_content: Original content text (with original case)

        Returns:
            List of evidence snippets
        """
        if not matches:
            return []

        snippets = []

        for match in matches[:3]:  # Limit to top 3 matches
            start = max(0, match.start() - 50)
            end = min(len(original_content), match.end() + 50)
            snippet = original_content[start:end].strip()

            # Truncate if too long
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."

            snippets.append(snippet)

        logger.debug(
            "evidence_snippets_extracted",
            n_snippets=len(snippets),
        )

        return snippets
