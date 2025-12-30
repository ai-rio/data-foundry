"""
TDD Test Suite for AML ORM Models (P01-003)

This test module provides comprehensive tests for AML (Anti-Money Laundering) models
following a full TDD approach. These tests cover:
- AML Enums (risk levels, typologies, decisions, statuses)
- AMLLabelingMethodology model
- AMLTransactionLabel model
- AMLExpertReview model
- AMLAuditReport model

Test Strategy:
- RED phase: Tests written first, expected to fail until implementation
- GREEN phase: Models implemented to pass tests
- REFACTOR phase: Code optimized while maintaining test coverage

Reference: P01-001 (Schema Design), P01-002 (Migrations)
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from uuid import uuid4


class TestAMLEnums:
    """Test AML enumeration types for controlled values."""

    def test_aml_risk_level_enum_values(self):
        """Test AMLRiskLevel enum has correct values."""
        from src.models.aml_enums import AMLRiskLevel

        assert AMLRiskLevel.LOW == "LOW"
        assert AMLRiskLevel.MEDIUM == "MEDIUM"
        assert AMLRiskLevel.HIGH == "HIGH"
        assert AMLRiskLevel.CRITICAL == "CRITICAL"

    def test_aml_risk_level_is_str_enum(self):
        """Test AMLRiskLevel inherits from str for serialization."""
        from src.models.aml_enums import AMLRiskLevel

        # Should be usable as string
        risk = AMLRiskLevel.HIGH
        assert isinstance(risk, str)
        assert risk == "HIGH"

    def test_aml_typology_enum_fatf_values(self):
        """Test AMLTypology enum has FATF standard typologies."""
        from src.models.aml_enums import AMLTypology

        # Core FATF typologies
        assert AMLTypology.ML == "ML"  # Money Laundering
        assert AMLTypology.TF == "TF"  # Terrorist Financing
        assert AMLTypology.PEP == "PEP"  # Politically Exposed Persons
        assert AMLTypology.FRAUD == "FRAUD"  # Financial Fraud
        assert AMLTypology.SANCTIONS == "SANCTIONS"  # Sanctions Evasion
        assert AMLTypology.TAX_EVASION == "TAX_EVASION"  # Tax Evasion
        assert AMLTypology.BRIBERY == "BRIBERY"  # Bribery/Corruption
        assert AMLTypology.SMUGGLING == "SMUGGLING"  # Trade-based ML
        assert AMLTypology.DRUG_TRAFFICKING == "DRUG_TRAFFICKING"  # Drug Trafficking
        assert AMLTypology.HUMAN_TRAFFICKING == "HUMAN_TRAFFICKING"  # Human Trafficking

    def test_aml_regulatory_flag_enum_values(self):
        """Test AMLRegulatoryFlag enum has regulatory compliance flags."""
        from src.models.aml_enums import AMLRegulatoryFlag

        assert AMLRegulatoryFlag.HIGH_RISK_JURISDICTION == "HIGH_RISK_JURISDICTION"
        assert AMLRegulatoryFlag.SANCTIONS_MATCH == "SANCTIONS_MATCH"
        assert AMLRegulatoryFlag.SUSPICIOUS_PATTERN == "SUSPICIOUS_PATTERN"
        assert AMLRegulatoryFlag.SHELL_COMPANY == "SHELL_COMPANY"
        assert AMLRegulatoryFlag.UNUSUAL_VOLUME == "UNUSUAL_VOLUME"
        assert AMLRegulatoryFlag.STRUCTURING == "STRUCTURING"
        assert AMLRegulatoryFlag.ROUND_TRIPPING == "ROUND_TRIPPING"
        assert AMLRegulatoryFlag.LAYERING == "LAYERING"

    def test_aml_expert_decision_enum_values(self):
        """Test AMLExpertDecision enum has correct review decisions."""
        from src.models.aml_enums import AMLExpertDecision

        assert AMLExpertDecision.AGREE == "AGREE"
        assert AMLExpertDecision.DISAGREE == "DISAGREE"
        assert AMLExpertDecision.NEEDS_CLARIFICATION == "NEEDS_CLARIFICATION"

    def test_aml_expert_review_status_enum_values(self):
        """Test AMLExpertReviewStatus enum has correct workflow statuses."""
        from src.models.aml_enums import AMLExpertReviewStatus

        assert AMLExpertReviewStatus.PENDING == "PENDING"
        assert AMLExpertReviewStatus.AGREED == "AGREED"
        assert AMLExpertReviewStatus.DISAGREED == "DISAGREED"
        assert AMLExpertReviewStatus.ESCALATED == "ESCALATED"

    def test_aml_agreement_level_enum_values(self):
        """Test AMLAgreementLevel enum has Cohen's Kappa interpretation levels."""
        from src.models.aml_enums import AMLAgreementLevel

        # Based on Landis & Koch (1977) interpretation of Cohen's Kappa
        assert AMLAgreementLevel.POOR == "POOR"  # < 0.00
        assert AMLAgreementLevel.FAIR == "FAIR"  # 0.00 - 0.20
        assert AMLAgreementLevel.MODERATE == "MODERATE"  # 0.21 - 0.40
        assert AMLAgreementLevel.SUBSTANTIAL == "SUBSTANTIAL"  # 0.41 - 0.60
        assert AMLAgreementLevel.PERFECT == "PERFECT"  # 0.61 - 1.00

    def test_aml_methodology_status_enum_values(self):
        """Test AMLMethodologyStatus enum has correct lifecycle statuses."""
        from src.models.aml_enums import AMLMethodologyStatus

        assert AMLMethodologyStatus.DRAFT == "DRAFT"
        assert AMLMethodologyStatus.ACTIVE == "ACTIVE"
        assert AMLMethodologyStatus.ARCHIVED == "ARCHIVED"


class TestAMLLabelingMethodologyModel:
    """Test AMLLabelingMethodology ORM model."""

    def test_methodology_model_creation(self):
        """Test creating an AMLLabelingMethodology instance."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Initial AML labeling methodology for FATF compliance",
            risk_thresholds={
                "LOW": {"min": 0.0, "max": 0.25},
                "MEDIUM": {"min": 0.25, "max": 0.5},
                "HIGH": {"min": 0.5, "max": 0.75},
                "CRITICAL": {"min": 0.75, "max": 1.0}
            },
            typologies=["ML", "TF", "PEP", "FRAUD", "SANCTIONS"],
            regulatory_references={
                "FATF": "https://www.fatf-gafi.org/",
                "FinCEN": "https://www.fincen.gov/"
            },
            created_by=str(uuid4()),
            status=AMLMethodologyStatus.ACTIVE,
            is_deleted=False
        )

        assert methodology.version == "1.0"
        assert methodology.status == AMLMethodologyStatus.ACTIVE
        assert methodology.is_deleted is False
        assert "ML" in methodology.typologies

    def test_methodology_is_active_method(self):
        """Test is_active() method returns correct status."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        active_methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Active methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE
        )

        draft_methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="2.0",
            description="Draft methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.DRAFT
        )

        assert active_methodology.is_active() is True
        assert draft_methodology.is_active() is False

    def test_methodology_get_thresholds_method(self):
        """Test get_thresholds() method returns risk thresholds dict."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        thresholds = {
            "LOW": {"min": 0.0, "max": 0.25},
            "MEDIUM": {"min": 0.25, "max": 0.5},
            "HIGH": {"min": 0.5, "max": 0.75},
            "CRITICAL": {"min": 0.75, "max": 1.0}
        }

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds=thresholds,
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE
        )

        result = methodology.get_thresholds()
        assert result == thresholds
        assert result["CRITICAL"]["min"] == 0.75

    def test_methodology_get_typologies_method(self):
        """Test get_typologies() method returns typologies list."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        typologies = ["ML", "TF", "PEP", "FRAUD"]

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=typologies,
            status=AMLMethodologyStatus.ACTIVE
        )

        result = methodology.get_typologies()
        assert result == typologies
        assert "ML" in result
        assert "TF" in result

    def test_methodology_tablename(self):
        """Test AMLLabelingMethodology has correct table name."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology

        assert AMLLabelingMethodology.__tablename__ == "aml_labeling_methodology"

    def test_methodology_default_timestamps(self):
        """Test methodology has auto-generated timestamps."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.DRAFT
        )

        assert methodology.created_at is not None
        assert isinstance(methodology.created_at, datetime)


class TestAMLTransactionLabelModel:
    """Test AMLTransactionLabel ORM model."""

    def test_transaction_label_creation(self):
        """Test creating an AMLTransactionLabel instance."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="High-risk transaction pattern detected with multiple layering indicators",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            regulatory_flags={"SUSPICIOUS_PATTERN": True, "LAYERING": True},
            is_audit_ready=False,
            is_deleted=False
        )

        assert label.risk_level == AMLRiskLevel.HIGH
        assert label.typology == "ML"
        assert label.confidence_score == Decimal("0.85")
        assert label.is_audit_ready is False

    def test_transaction_label_is_audit_ready_method(self):
        """Test is_audit_ready() method for audit readiness check."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        # Label not ready for audit (pending review)
        pending_label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_audit_ready=False
        )

        # Label ready for audit (agreed by expert)
        ready_label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.95"),
            ai_reasoning="Test reasoning",
            expert_review_status=AMLExpertReviewStatus.AGREED,
            is_audit_ready=True
        )

        assert pending_label.is_audit_ready_check() is False
        assert ready_label.is_audit_ready_check() is True

    def test_transaction_label_to_csv_row_method(self):
        """Test to_csv_row() method for CSV export format."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id="test-uuid-123",
            transaction_id="txn-uuid-456",
            tenant_id="tenant-uuid-789",
            risk_level=AMLRiskLevel.CRITICAL,
            typology="TF",
            confidence_score=Decimal("0.92"),
            ai_reasoning="Terrorist financing pattern detected",
            expert_review_status=AMLExpertReviewStatus.AGREED,
            regulatory_flags={"SANCTIONS_MATCH": True},
            is_audit_ready=True,
            is_deleted=False,
            created_at=datetime(2024, 1, 15, 10, 30, 0)
        )

        csv_row = label.to_csv_row()

        assert isinstance(csv_row, dict)
        assert csv_row["id"] == "test-uuid-123"
        assert csv_row["transaction_id"] == "txn-uuid-456"
        assert csv_row["risk_level"] == "CRITICAL"
        assert csv_row["typology"] == "TF"
        assert csv_row["confidence_score"] == "0.92"
        assert csv_row["is_audit_ready"] is True

    def test_transaction_label_get_risk_color_method(self):
        """Test get_risk_color() method for UI color coding."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        low_risk = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.LOW,
            typology="ML",
            confidence_score=Decimal("0.3"),
            ai_reasoning="Low risk",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )

        critical_risk = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.CRITICAL,
            typology="TF",
            confidence_score=Decimal("0.95"),
            ai_reasoning="Critical risk",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )

        assert low_risk.get_risk_color() == "green"
        assert critical_risk.get_risk_color() == "red"

    def test_transaction_label_mark_for_review_method(self):
        """Test mark_for_review() method sets status to PENDING."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.AGREED,
            is_audit_ready=True
        )

        label.mark_for_review()

        assert label.expert_review_status == AMLExpertReviewStatus.PENDING
        assert label.is_audit_ready is False

    def test_transaction_label_tablename(self):
        """Test AMLTransactionLabel has correct table name."""
        from src.models.aml_transaction_label import AMLTransactionLabel

        assert AMLTransactionLabel.__tablename__ == "aml_transaction_labels"

    def test_transaction_label_confidence_score_validation(self):
        """Test confidence_score must be between 0 and 1."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        # Valid confidence score
        valid_label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.MEDIUM,
            typology="ML",
            confidence_score=Decimal("0.75"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )

        assert valid_label.confidence_score == Decimal("0.75")


class TestAMLExpertReviewModel:
    """Test AMLExpertReview ORM model."""

    def test_expert_review_creation(self):
        """Test creating an AMLExpertReview instance."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="AI assessment is accurate based on FATF indicators",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow(),
            is_deleted=False
        )

        assert review.expert_decision == AMLExpertDecision.AGREE
        assert review.confidence_level == Decimal("0.90")
        assert review.is_deleted is False

    def test_expert_review_is_agreement_method(self):
        """Test is_agreement() method checks for AGREE decision."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        agree_review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Agree with AI",
            confidence_level=Decimal("0.85"),
            reviewed_at=datetime.utcnow()
        )

        disagree_review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.DISAGREE,
            reasoning="Disagree with AI",
            confidence_level=Decimal("0.80"),
            reviewed_at=datetime.utcnow()
        )

        assert agree_review.is_agreement() is True
        assert disagree_review.is_agreement() is False

    def test_expert_review_is_disagreement_method(self):
        """Test is_disagreement() method checks for DISAGREE decision."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        agree_review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Agree with AI",
            confidence_level=Decimal("0.85"),
            reviewed_at=datetime.utcnow()
        )

        disagree_review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.DISAGREE,
            reasoning="Disagree with AI",
            confidence_level=Decimal("0.80"),
            reviewed_at=datetime.utcnow()
        )

        assert agree_review.is_disagreement() is False
        assert disagree_review.is_disagreement() is True

    def test_expert_review_tablename(self):
        """Test AMLExpertReview has correct table name."""
        from src.models.aml_expert_review import AMLExpertReview

        assert AMLExpertReview.__tablename__ == "aml_expert_reviews"

    def test_expert_review_confidence_validation(self):
        """Test confidence_level must be between 0 and 1."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Valid review",
            confidence_level=Decimal("0.75"),
            reviewed_at=datetime.utcnow()
        )

        assert review.confidence_level == Decimal("0.75")


class TestAMLAuditReportModel:
    """Test AMLAuditReport ORM model."""

    def test_audit_report_creation(self):
        """Test creating an AMLAuditReport instance."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/reports/audit_2024_01.pdf",
            is_deleted=False
        )

        assert report.transaction_count == 1000
        assert report.labeled_count == 950
        assert report.expert_reviewed_count == 200
        assert report.kappa_coefficient == Decimal("0.72")
        assert report.agreement_level == AMLAgreementLevel.SUBSTANTIAL

    def test_audit_report_get_summary_method(self):
        """Test get_summary() method returns summary metrics dict."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id="report-uuid-123",
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime(2024, 1, 15, 10, 30, 0),
            report_url="s3://bucket/reports/audit.pdf"
        )

        summary = report.get_summary()

        assert isinstance(summary, dict)
        assert summary["transaction_count"] == 1000
        assert summary["labeled_count"] == 950
        assert summary["expert_reviewed_count"] == 200
        assert summary["kappa_coefficient"] == Decimal("0.72")
        assert summary["agreement_level"] == "SUBSTANTIAL"
        assert summary["labeling_rate"] == 0.95  # 950/1000
        assert summary["review_rate"] == pytest.approx(0.21, rel=0.01)  # 200/950

    def test_audit_report_is_substantial_agreement_method(self):
        """Test is_substantial_agreement() method checks kappa >= 0.6."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        substantial_report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/reports/audit.pdf"
        )

        poor_report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=500,
            expert_reviewed_count=100,
            kappa_coefficient=Decimal("0.35"),
            agreement_level=AMLAgreementLevel.FAIR,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/reports/audit.pdf"
        )

        assert substantial_report.is_substantial_agreement() is True
        assert poor_report.is_substantial_agreement() is False

    def test_audit_report_tablename(self):
        """Test AMLAuditReport has correct table name."""
        from src.models.aml_audit_report import AMLAuditReport

        assert AMLAuditReport.__tablename__ == "aml_audit_reports"

    def test_audit_report_kappa_validation(self):
        """Test kappa_coefficient must be between -1 and 1."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.85"),
            agreement_level=AMLAgreementLevel.PERFECT,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/reports/audit.pdf"
        )

        assert report.kappa_coefficient == Decimal("0.85")


class TestAMLModelRelationships:
    """Test relationships between AML models."""

    def test_transaction_label_methodology_relationship(self):
        """Test AMLTransactionLabel can reference methodology."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        methodology_id = str(uuid4())
        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            version_id=methodology_id
        )

        assert label.version_id == methodology_id

    def test_expert_review_label_relationship(self):
        """Test AMLExpertReview references transaction label."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        label_id = str(uuid4())
        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=label_id,
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow()
        )

        assert review.aml_transaction_label_id == label_id


class TestAMLModelToDict:
    """Test to_dict serialization methods for AML models."""

    def test_methodology_to_dict(self):
        """Test AMLLabelingMethodology to_dict serialization."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id="meth-uuid-123",
            tenant_id="tenant-uuid",
            version="1.0",
            description="Test methodology",
            risk_thresholds={"LOW": {"min": 0.0, "max": 0.25}},
            typologies=["ML", "TF"],
            regulatory_references={"FATF": "https://fatf-gafi.org"},
            status=AMLMethodologyStatus.ACTIVE
        )

        result = methodology.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "meth-uuid-123"
        assert result["version"] == "1.0"
        assert result["status"] == "ACTIVE"

    def test_transaction_label_to_dict(self):
        """Test AMLTransactionLabel to_dict serialization."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id="label-uuid-123",
            transaction_id="txn-uuid-456",
            tenant_id="tenant-uuid",
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test reasoning",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )

        result = label.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "label-uuid-123"
        assert result["risk_level"] == "HIGH"
        assert result["confidence_score"] == "0.85"

    def test_expert_review_to_dict(self):
        """Test AMLExpertReview to_dict serialization."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id="review-uuid-123",
            aml_transaction_label_id="label-uuid",
            tenant_id="tenant-uuid",
            expert_id="expert-uuid",
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="AI assessment is accurate",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime(2024, 1, 15, 10, 30, 0)
        )

        result = review.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "review-uuid-123"
        assert result["expert_decision"] == "AGREE"
        assert result["confidence_level"] == "0.90"

    def test_audit_report_to_dict(self):
        """Test AMLAuditReport to_dict serialization."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id="report-uuid-123",
            tenant_id="tenant-uuid",
            job_id="job-uuid",
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime(2024, 1, 15, 10, 30, 0),
            report_url="s3://bucket/report.pdf"
        )

        result = report.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "report-uuid-123"
        assert result["kappa_coefficient"] == "0.72"
        assert result["agreement_level"] == "SUBSTANTIAL"


class TestAMLAuditTrailFields:
    """Test audit trail fields for forensic compliance (P01-003)."""

    # =========================================================================
    # AMLTransactionLabel Audit Trail Tests (MUTABLE - has updated_by)
    # =========================================================================

    def test_transaction_label_has_updated_by_field(self):
        """Test AMLTransactionLabel has updated_by field."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            updated_by="user-uuid-123"
        )

        assert label.updated_by == "user-uuid-123"

    def test_transaction_label_has_deleted_by_field(self):
        """Test AMLTransactionLabel has deleted_by field."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            deleted_by="admin-uuid-456"
        )

        assert label.deleted_by == "admin-uuid-456"

    def test_transaction_label_has_deleted_at_field(self):
        """Test AMLTransactionLabel has deleted_at field."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        deleted_time = datetime(2024, 6, 15, 14, 30, 0)
        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            deleted_at=deleted_time
        )

        assert label.deleted_at == deleted_time

    def test_transaction_label_mark_as_deleted_by_method(self):
        """Test AMLTransactionLabel mark_as_deleted_by method."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_deleted=False
        )

        user_id = "admin-user-123"
        label.mark_as_deleted_by(user_id)

        assert label.is_deleted is True
        assert label.deleted_by == user_id
        assert label.deleted_at is not None
        assert isinstance(label.deleted_at, datetime)
        assert label.updated_by == user_id
        assert label.updated_at is not None

    def test_transaction_label_to_dict_includes_audit_fields(self):
        """Test AMLTransactionLabel to_dict includes audit trail fields."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        deleted_time = datetime(2024, 6, 15, 14, 30, 0)
        label = AMLTransactionLabel(
            id="label-uuid-123",
            transaction_id="txn-uuid-456",
            tenant_id="tenant-uuid",
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            updated_by="user-123",
            deleted_by="admin-456",
            deleted_at=deleted_time
        )

        result = label.to_dict()

        assert "updated_by" in result
        assert result["updated_by"] == "user-123"
        assert "deleted_by" in result
        assert result["deleted_by"] == "admin-456"
        assert "deleted_at" in result
        assert result["deleted_at"] == deleted_time.isoformat()

    def test_transaction_label_to_csv_row_includes_audit_fields(self):
        """Test AMLTransactionLabel to_csv_row includes audit trail fields."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        deleted_time = datetime(2024, 6, 15, 14, 30, 0)
        label = AMLTransactionLabel(
            id="label-uuid-123",
            transaction_id="txn-uuid-456",
            tenant_id="tenant-uuid",
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            updated_by="user-123",
            deleted_by="admin-456",
            deleted_at=deleted_time
        )

        result = label.to_csv_row()

        assert "updated_by" in result
        assert result["updated_by"] == "user-123"
        assert "deleted_by" in result
        assert result["deleted_by"] == "admin-456"
        assert "deleted_at" in result
        assert result["deleted_at"] == deleted_time.isoformat()

    def test_transaction_label_audit_fields_default_to_none(self):
        """Test AMLTransactionLabel audit fields default to None."""
        from src.models.aml_transaction_label import AMLTransactionLabel
        from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus

        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=str(uuid4()),
            tenant_id=str(uuid4()),
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.85"),
            ai_reasoning="Test",
            expert_review_status=AMLExpertReviewStatus.PENDING
        )

        assert label.updated_by is None
        assert label.deleted_by is None
        assert label.deleted_at is None

    # =========================================================================
    # AMLExpertReview Audit Trail Tests (IMMUTABLE - deleted_by, deleted_at only)
    # =========================================================================

    def test_expert_review_has_deleted_by_field(self):
        """Test AMLExpertReview has deleted_by field."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow(),
            deleted_by="admin-uuid-789"
        )

        assert review.deleted_by == "admin-uuid-789"

    def test_expert_review_has_deleted_at_field(self):
        """Test AMLExpertReview has deleted_at field."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        deleted_time = datetime(2024, 7, 20, 10, 0, 0)
        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow(),
            deleted_at=deleted_time
        )

        assert review.deleted_at == deleted_time

    def test_expert_review_mark_as_deleted_by_method(self):
        """Test AMLExpertReview mark_as_deleted_by method."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow(),
            is_deleted=False
        )

        user_id = "admin-user-456"
        review.mark_as_deleted_by(user_id)

        assert review.is_deleted is True
        assert review.deleted_by == user_id
        assert review.deleted_at is not None
        assert isinstance(review.deleted_at, datetime)

    def test_expert_review_to_dict_includes_audit_fields(self):
        """Test AMLExpertReview to_dict includes audit trail fields."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        deleted_time = datetime(2024, 7, 20, 10, 0, 0)
        review = AMLExpertReview(
            id="review-uuid-123",
            aml_transaction_label_id="label-uuid",
            tenant_id="tenant-uuid",
            expert_id="expert-uuid",
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime(2024, 1, 15, 10, 30, 0),
            deleted_by="admin-789",
            deleted_at=deleted_time
        )

        result = review.to_dict()

        assert "deleted_by" in result
        assert result["deleted_by"] == "admin-789"
        assert "deleted_at" in result
        assert result["deleted_at"] == deleted_time.isoformat()

    def test_expert_review_audit_fields_default_to_none(self):
        """Test AMLExpertReview audit fields default to None."""
        from src.models.aml_expert_review import AMLExpertReview
        from src.models.aml_enums import AMLExpertDecision

        review = AMLExpertReview(
            id=str(uuid4()),
            aml_transaction_label_id=str(uuid4()),
            tenant_id=str(uuid4()),
            expert_id=str(uuid4()),
            expert_decision=AMLExpertDecision.AGREE,
            reasoning="Test",
            confidence_level=Decimal("0.90"),
            reviewed_at=datetime.utcnow()
        )

        assert review.deleted_by is None
        assert review.deleted_at is None

    # =========================================================================
    # AMLAuditReport Audit Trail Tests (IMMUTABLE - deleted_by, deleted_at only)
    # =========================================================================

    def test_audit_report_has_deleted_by_field(self):
        """Test AMLAuditReport has deleted_by field."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/report.pdf",
            deleted_by="admin-uuid-321"
        )

        assert report.deleted_by == "admin-uuid-321"

    def test_audit_report_has_deleted_at_field(self):
        """Test AMLAuditReport has deleted_at field."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        deleted_time = datetime(2024, 8, 10, 16, 45, 0)
        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/report.pdf",
            deleted_at=deleted_time
        )

        assert report.deleted_at == deleted_time

    def test_audit_report_mark_as_deleted_by_method(self):
        """Test AMLAuditReport mark_as_deleted_by method."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/report.pdf",
            is_deleted=False
        )

        user_id = "admin-user-789"
        report.mark_as_deleted_by(user_id)

        assert report.is_deleted is True
        assert report.deleted_by == user_id
        assert report.deleted_at is not None
        assert isinstance(report.deleted_at, datetime)

    def test_audit_report_to_dict_includes_audit_fields(self):
        """Test AMLAuditReport to_dict includes audit trail fields."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        deleted_time = datetime(2024, 8, 10, 16, 45, 0)
        report = AMLAuditReport(
            id="report-uuid-123",
            tenant_id="tenant-uuid",
            job_id="job-uuid",
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime(2024, 1, 15, 10, 30, 0),
            report_url="s3://bucket/report.pdf",
            deleted_by="admin-321",
            deleted_at=deleted_time
        )

        result = report.to_dict()

        assert "deleted_by" in result
        assert result["deleted_by"] == "admin-321"
        assert "deleted_at" in result
        assert result["deleted_at"] == deleted_time.isoformat()

    def test_audit_report_audit_fields_default_to_none(self):
        """Test AMLAuditReport audit fields default to None."""
        from src.models.aml_audit_report import AMLAuditReport
        from src.models.aml_enums import AMLAgreementLevel

        report = AMLAuditReport(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            job_id=str(uuid4()),
            transaction_count=1000,
            labeled_count=950,
            expert_reviewed_count=200,
            kappa_coefficient=Decimal("0.72"),
            agreement_level=AMLAgreementLevel.SUBSTANTIAL,
            generated_at=datetime.utcnow(),
            report_url="s3://bucket/report.pdf"
        )

        assert report.deleted_by is None
        assert report.deleted_at is None

    # =========================================================================
    # AMLLabelingMethodology Audit Trail Tests (IMMUTABLE - deleted_by, deleted_at only)
    # =========================================================================

    def test_methodology_has_deleted_by_field(self):
        """Test AMLLabelingMethodology has deleted_by field."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE,
            deleted_by="admin-uuid-654"
        )

        assert methodology.deleted_by == "admin-uuid-654"

    def test_methodology_has_deleted_at_field(self):
        """Test AMLLabelingMethodology has deleted_at field."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        deleted_time = datetime(2024, 9, 5, 12, 0, 0)
        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE,
            deleted_at=deleted_time
        )

        assert methodology.deleted_at == deleted_time

    def test_methodology_mark_as_deleted_by_method(self):
        """Test AMLLabelingMethodology mark_as_deleted_by method."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE,
            is_deleted=False
        )

        user_id = "admin-user-111"
        methodology.mark_as_deleted_by(user_id)

        assert methodology.is_deleted is True
        assert methodology.deleted_by == user_id
        assert methodology.deleted_at is not None
        assert isinstance(methodology.deleted_at, datetime)

    def test_methodology_to_dict_includes_audit_fields(self):
        """Test AMLLabelingMethodology to_dict includes audit trail fields."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        deleted_time = datetime(2024, 9, 5, 12, 0, 0)
        methodology = AMLLabelingMethodology(
            id="meth-uuid-123",
            tenant_id="tenant-uuid",
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE,
            deleted_by="admin-654",
            deleted_at=deleted_time
        )

        result = methodology.to_dict()

        assert "deleted_by" in result
        assert result["deleted_by"] == "admin-654"
        assert "deleted_at" in result
        assert result["deleted_at"] == deleted_time.isoformat()

    def test_methodology_audit_fields_default_to_none(self):
        """Test AMLLabelingMethodology audit fields default to None."""
        from src.models.aml_labeling_methodology import AMLLabelingMethodology
        from src.models.aml_enums import AMLMethodologyStatus

        methodology = AMLLabelingMethodology(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            version="1.0",
            description="Test methodology",
            risk_thresholds={},
            typologies=[],
            status=AMLMethodologyStatus.ACTIVE
        )

        assert methodology.deleted_by is None
        assert methodology.deleted_at is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
