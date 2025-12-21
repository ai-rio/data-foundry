"""
Rate limiting module for Data Foundry
"""

import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque


class RateLimiter:
    """
    Simple in-memory rate limiter implementation.
    """

    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute
        """
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, deque] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def is_allowed(self, user_id: str, tenant_id: Optional[str] = None) -> bool:
        """
        Check if a request is allowed for the given user.

        Args:
            user_id: User identifier
            tenant_id: Optional tenant identifier for multi-tenant rate limiting

        Returns:
            True if request is allowed, False otherwise
        """
        key = f"{tenant_id}:{user_id}" if tenant_id else user_id

        async with self.lock:
            now = time.time()
            window_start = now - 60  # 1 minute window

            # Remove old requests outside the window
            user_requests = self.requests[key]
            while user_requests and user_requests[0] < window_start:
                user_requests.popleft()

            # Check if under the limit
            if len(user_requests) < self.requests_per_minute:
                user_requests.append(now)
                return True

            return False