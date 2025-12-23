"""
Admin/Monitoring API Package - Week 4 Phase 2.5

This package provides admin and monitoring endpoints for the Data Foundry platform.
It includes health checks, metrics aggregation, and pipeline status monitoring.

SECURITY HARDENING - Week 4 Phase 2.5:
- CRITICAL #1: Rate limiting using in-memory IP tracker (sliding window)
- CRITICAL #2: Admin authorization on POST /pipeline/trigger
- CRITICAL #4: Thread safety with threading.Lock
- CRITICAL #5: Bounded memory using deque(maxlen=10000)
- Generic error messages (no information disclosure)
- Hashed user IDs in logs

Pattern reference: src/api/v1/signals/router.py (96/100 score)
"""

from .router import router

__all__ = ["router"]
