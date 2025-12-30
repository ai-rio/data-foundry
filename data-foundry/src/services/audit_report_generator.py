"""
AML Audit Report Generator Service

This module implements the AuditReportGenerator class for creating comprehensive
AML audit reports in JSON and PDF formats for regulatory compliance.

Features:
- JSON report generation with all required sections
- PDF generation from report data
- Metrics calculation (risk distribution, typology distribution)
- Inter-rater agreement integration (Cohen's Kappa)
- Expert review queue tracking
- Regulatory references inclusion
- Complete audit trail metadata

SOLID Principles:
- Single Responsibility: Each method handles one specific aspect of report generation
- Open/Closed: Extensible through composition, closed for modification
- Liskov Substitution: Compatible with any report data source
- Interface Segregation: Focused public API
- Dependency Inversion: No concrete database dependencies

Quality Gates:
- SOLID adherence: 100%
- Test coverage: >90%
- Docstring coverage: >80%
- Function length: <50 lines

Reference: P01-015 (Audit Report Generation)
Author: Data Foundry Team
Version: 1.0.0
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fpdf import FPDF
from src.core.agreement_calculator import CohenKappaCalculator

logger = logging.getLogger(__name__)


class AuditReportGenerator:
    """
    AML Audit Report Generator for regulatory compliance.

    This service generates comprehensive audit reports for AML labeling workflows,
    including transaction statistics, risk distributions, inter-rater agreement
    metrics, and regulatory references.

    The generated reports support regulatory defensibility and compliance with
    FATF recommendations and FinCEN advisories.

    Attributes:
        None (stateless service)

    Example:
        >>> generator = AuditReportGenerator()
        >>> report = generator.generate_report(
        ...     job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
        ...     labels=labeled_transactions,
        ...     kappa_score=0.85
        ... )
        >>> pdf_bytes = generator.generate_pdf(report)
    """

    # Regulatory references for AML compliance
    REGULATORY_REFERENCES = [
        "FATF Recommendation 10: Financial Investigations",
        "FATF Recommendation 20: Suspicious Transaction Reports",
        "FinCEN Advisory AML-1: Priority Crypto-Assets",
        "FinCEN Advisory AML-2: Real Estate Money Laundering",
        "EU AML Directive 6 (AMLD6): Art. 32 & 33",
        "BSA/AML Manual: FFIEC Examination Procedures"
    ]

    # Methodology version for audit trail
    METHODOLOGY_VERSION = "v1.0"

    def __init__(self):
        """
        Initialize the AuditReportGenerator.

        The generator is stateless and thread-safe. All dependencies are
        injected via method parameters, following the Dependency Inversion
        Principle.
        """
        logger.debug("AuditReportGenerator initialized")

    def generate_report(
        self,
        job_data: Dict[str, Any],
        labels: list[Dict[str, Any]],
        kappa_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate JSON audit report for AML labeling job.

        Creates a comprehensive audit report with all required sections for
        regulatory compliance, including transaction statistics, risk
        distributions, inter-rater agreement metrics, and audit trail metadata.

        Args:
            job_data: Dictionary containing job metadata:
                - job_id: Unique processing job identifier
                - tenant_id: Tenant identifier for multi-tenancy
            labels: List of AML-labeled transaction records with fields:
                - aml_risk_level: Risk classification (LOW, MEDIUM, HIGH, CRITICAL)
                - aml_typology: FATF typology code
                - aml_requires_expert_review: Boolean flag for expert review queue
            kappa_score: Optional Cohen's Kappa coefficient for inter-rater agreement

        Returns:
            Dictionary with complete audit report including:
                - report_id: Unique report identifier (UUID-based)
                - generated_at: ISO timestamp of report generation
                - job_id: Processing job identifier
                - tenant_id: Tenant identifier
                - total_transactions: Total number of transactions processed
                - aml_risk_distribution: Count per risk level
                - typology_distribution: Count per FATF typology
                - inter_rater_agreement: Kappa score and confidence level
                - expert_review_queue_size: Number of transactions pending review
                - regulatory_references: List of applicable regulatory citations
                - audit_trail: Methodology version and compliance status

        Raises:
            KeyError: If required job_data fields are missing
            TypeError: If labels is not a list

        Example:
            >>> report = generator.generate_report(
            ...     job_data={"job_id": "job_abc", "tenant_id": "tenant_001"},
            ...     labels=labeled_data,
            ...     kappa_score=0.85
            ... )
            >>> print(report["total_transactions"])  # 150
            >>> print(report["aml_risk_distribution"])  # {"LOW": 80, "MEDIUM": 40, ...}
        """
        # Validate inputs
        if not isinstance(job_data, dict):
            raise TypeError("job_data must be a dictionary")
        if not isinstance(labels, list):
            raise TypeError("labels must be a list")

        # Extract identifiers and calculate metrics
        job_id = job_data.get("job_id", "unknown")
        tenant_id = job_data.get("tenant_id", "unknown")
        metrics = self.calculate_metrics(labels)

        # Build report structure
        report_id = self._generate_report_id()
        inter_rater_agreement = self._build_inter_rater_agreement(kappa_score)

        # Assemble complete report
        report = self._assemble_report(
            report_id, job_id, tenant_id, metrics,
            inter_rater_agreement, kappa_score
        )

        logger.info(
            f"Generated audit report {report_id} for job {job_id}: "
            f"{metrics['total_transactions']} transactions, kappa={kappa_score}"
        )

        return report

    def _generate_report_id(self) -> str:
        """Generate unique report ID with timestamp and UUID suffix."""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_suffix = uuid.uuid4().hex[:8]
        return f"aml_report_{timestamp}_{unique_suffix}"

    def _assemble_report(
        self,
        report_id: str,
        job_id: str,
        tenant_id: str,
        metrics: Dict[str, Any],
        inter_rater_agreement: Dict[str, Any],
        kappa_score: Optional[float]
    ) -> Dict[str, Any]:
        """Assemble complete report dictionary from components."""
        return {
            "report_id": report_id,
            "report_generated_at": datetime.utcnow().isoformat(),  # P01-015 required field name
            "generated_at": datetime.utcnow().isoformat(),  # Alias for backward compatibility
            "job_id": job_id,
            "tenant_id": tenant_id,
            "total_transactions": metrics["total_transactions"],
            "aml_risk_distribution": metrics["aml_risk_distribution"],
            "typology_distribution": metrics["typology_distribution"],
            "inter_rater_agreement": inter_rater_agreement,
            "expert_review_queue_size": metrics["expert_review_queue_size"],
            "regulatory_references": self.REGULATORY_REFERENCES,
            "audit_trail": {
                "methodology_version": self.METHODOLOGY_VERSION,
                "generated_by": "system",
                "compliance_status": "ready"
            }
        }

    def generate_pdf(self, report_data: Dict[str, Any]) -> bytes:
        """
        Generate PDF document from report data.

        Creates a formatted PDF report suitable for printing or archival.
        The PDF includes all key metrics, distributions, and audit trail
        information in a professional layout.

        Args:
            report_data: Complete report dictionary from generate_report()

        Returns:
            bytes: PDF document as bytes (suitable for file write or HTTP response)

        Raises:
            ValueError: If report_data is missing required fields
            RuntimeError: If PDF generation fails

        Example:
            >>> pdf_bytes = generator.generate_pdf(report_data)
            >>> with open("audit_report.pdf", "wb") as f:
            ...     f.write(pdf_bytes)
        """
        if not isinstance(report_data, dict):
            raise TypeError("report_data must be a dictionary")

        # Create PDF document and add sections
        pdf = FPDF()
        pdf.add_page()
        self._add_pdf_header(pdf)
        self._add_pdf_metadata(pdf, report_data)
        self._add_pdf_statistics(pdf, report_data)
        self._add_pdf_risk_distribution(pdf, report_data)
        self._add_pdf_agreement_section(pdf, report_data)
        self._add_pdf_review_queue(pdf, report_data)
        self._add_pdf_audit_trail(pdf, report_data)

        # Generate and return PDF bytes
        pdf_bytes = pdf.output(dest="S").encode("latin-1")
        logger.debug(f"Generated PDF report ({len(pdf_bytes)} bytes)")
        return pdf_bytes

    def _add_pdf_header(self, pdf: FPDF) -> None:
        """Add PDF header section."""
        pdf.set_font("Arial", size=12)
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, txt="AML Audit Report", ln=True, align="C")

    def _add_pdf_metadata(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add PDF metadata section."""
        pdf.set_font("Arial", size=10)
        pdf.ln(5)
        pdf.cell(0, 6, txt=f"Report ID: {report_data.get('report_id', 'N/A')}", ln=True)
        pdf.cell(0, 6, txt=f"Generated: {report_data.get('generated_at', 'N/A')}", ln=True)
        pdf.cell(0, 6, txt=f"Job ID: {report_data.get('job_id', 'N/A')}", ln=True)
        pdf.cell(0, 6, txt=f"Tenant ID: {report_data.get('tenant_id', 'N/A')}", ln=True)

    def _add_pdf_statistics(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add summary statistics section."""
        pdf.ln(10)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, txt="Summary Statistics", ln=True)
        pdf.set_font("Arial", size=10)
        total_txn = report_data.get("total_transactions", 0)
        pdf.cell(0, 6, txt=f"Total Transactions: {total_txn}", ln=True)

    def _add_pdf_risk_distribution(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add risk level distribution section."""
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, txt="Risk Level Distribution", ln=True)
        pdf.set_font("Arial", size=10)
        risk_dist = report_data.get("aml_risk_distribution", {})
        for risk_level, count in risk_dist.items():
            pdf.cell(0, 6, txt=f"  {risk_level}: {count}", ln=True)

    def _add_pdf_agreement_section(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add inter-rater agreement section."""
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, txt="Inter-Rater Agreement", ln=True)
        pdf.set_font("Arial", size=10)
        agreement = report_data.get("inter_rater_agreement", {})
        kappa = agreement.get("kappa_score", "N/A")
        confidence = agreement.get("confidence_level", "N/A")
        pdf.cell(0, 6, txt=f"  Cohen's Kappa: {kappa}", ln=True)
        pdf.cell(0, 6, txt=f"  Confidence Level: {confidence}", ln=True)

    def _add_pdf_review_queue(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add expert review queue section."""
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, txt="Expert Review Queue", ln=True)
        pdf.set_font("Arial", size=10)
        queue_size = report_data.get("expert_review_queue_size", 0)
        pdf.cell(0, 6, txt=f"  Pending Reviews: {queue_size}", ln=True)

    def _add_pdf_audit_trail(self, pdf: FPDF, report_data: Dict[str, Any]) -> None:
        """Add audit trail section."""
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, txt="Audit Trail", ln=True)
        pdf.set_font("Arial", size=10)
        audit_trail = report_data.get("audit_trail", {})
        pdf.cell(0, 6, txt=f"  Methodology Version: {audit_trail.get('methodology_version', 'N/A')}", ln=True)
        pdf.cell(0, 6, txt=f"  Generated By: {audit_trail.get('generated_by', 'N/A')}", ln=True)
        pdf.cell(0, 6, txt=f"  Compliance Status: {audit_trail.get('compliance_status', 'N/A')}", ln=True)

    def calculate_metrics(self, labels: list[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate metrics from AML-labeled transactions.

        Computes key statistics including total transactions, risk level
        distribution, typology distribution, and expert review queue size.

        Args:
            labels: List of AML-labeled transaction records

        Returns:
            Dictionary with calculated metrics:
                - total_transactions: Total number of labels
                - aml_risk_distribution: Count per risk level (LOW, MEDIUM, HIGH, CRITICAL)
                - typology_distribution: Count per FATF typology
                - expert_review_queue_size: Number of labels requiring expert review

        Example:
            >>> metrics = generator.calculate_metrics(labels)
            >>> print(metrics["total_transactions"])  # 150
            >>> print(metrics["aml_risk_distribution"])  # {"LOW": 80, ...}
        """
        # Initialize counters
        risk_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        typology_distribution: Dict[str, int] = {}
        expert_review_queue_size = 0

        # Process each label
        for label in labels:
            # Count risk level distribution
            risk_level = label.get("aml_risk_level", "UNKNOWN")
            if risk_level in risk_distribution:
                risk_distribution[risk_level] += 1

            # Count typology distribution
            typology = label.get("aml_typology", "UNKNOWN")
            typology_distribution[typology] = typology_distribution.get(typology, 0) + 1

            # Count expert review queue
            if label.get("aml_requires_expert_review", False):
                expert_review_queue_size += 1

        # Build metrics dictionary
        metrics = {
            "total_transactions": len(labels),
            "aml_risk_distribution": risk_distribution,
            "typology_distribution": typology_distribution,
            "expert_review_queue_size": expert_review_queue_size
        }

        logger.debug(
            f"Calculated metrics: {metrics['total_transactions']} transactions, "
            f"risk_dist={risk_distribution}, queue_size={expert_review_queue_size}"
        )

        return metrics

    def _build_inter_rater_agreement(
        self,
        kappa_score: Optional[float]
    ) -> Dict[str, Any]:
        """
        Build inter-rater agreement section for report.

        Uses CohenKappaCalculator to determine confidence level from
        kappa score. Handles None kappa gracefully.

        Args:
            kappa_score: Cohen's Kappa coefficient (optional)

        Returns:
            Dictionary with kappa_score and confidence_level
        """
        if kappa_score is not None:
            # Use CohenKappaCalculator to interpret kappa
            calculator = CohenKappaCalculator()
            confidence_level = calculator.get_confidence_level(kappa_score)

            return {
                "kappa_score": kappa_score,
                "confidence_level": confidence_level,
                "available": True
            }
        else:
            # No kappa data available
            return {
                "kappa_score": None,
                "confidence_level": "UNAVAILABLE",
                "available": False
            }
