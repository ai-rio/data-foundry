"""
A/B Testing API Module

This module provides endpoints for managing A/B tests and collecting metrics.

Components:
- contracts: Pydantic request/response models
- router: FastAPI route handlers

Example usage:
    # Create a new A/B test
    POST /api/v1/abtest/create
    {
        "test_name": "test-validation-strategies",
        "description": "Testing strict vs lenient validation",
        "variant_ratio": 0.3,
        "control_name": "strict_validation",
        "variant_name": "lenient_validation"
    }

    # Record a prediction
    POST /api/v1/abtest/{test_id}/record
    {
        "sample_id": "sample-001",
        "treatment": "control",
        "prediction": true,
        "ground_truth": true
    }

    # Get metrics
    GET /api/v1/abtest/{test_id}/metrics

Security:
- All endpoints require authentication
- Admin endpoints require admin role
- Rate limiting applies to all endpoints
"""

from src.api.v1.abtest.router import router

__all__ = ["router"]
