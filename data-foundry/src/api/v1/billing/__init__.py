"""Billing API package initialization."""

from fastapi import APIRouter

from .router import router as billing_router

__all__ = ["billing_router"]
