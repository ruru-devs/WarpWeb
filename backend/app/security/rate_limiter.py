"""
In-memory sliding window rate limiter for WarpWeb API endpoints.
Configurable per-IP and per-site limits with automatic window pruning.
"""
import time
import os
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Request, HTTPException

class SlidingWindowRateLimiter:
    def __init__(
        self,
        default_limit: int = 60,
        window_seconds: int = 60,
        name: str = "default"
    ):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.name = name
        # Store request timestamps: key -> list of float timestamps
        self._records: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, limit: Optional[int] = None) -> bool:
        max_requests = limit if limit is not None else self.default_limit
        now = time.time()
        window_start = now - self.window_seconds

        timestamps = self._records[key]
        # Prune old timestamps outside window
        valid_timestamps = [t for t in timestamps if t > window_start]
        self._records[key] = valid_timestamps

        if len(valid_timestamps) >= max_requests:
            return False

        valid_timestamps.append(now)
        return True

    def check(self, key: str, limit: Optional[int] = None, client_type: str = "request"):
        if not self.is_allowed(key, limit):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {client_type}. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)}
            )

    def reset(self):
        """Helper for test suites."""
        self._records.clear()

# Configurable limits via environment variables
SEARCH_IP_LIMIT = int(os.getenv("WARPWEB_RATE_LIMIT_SEARCH_IP", "60"))       # 60 req/min per IP
SEARCH_SITE_LIMIT = int(os.getenv("WARPWEB_RATE_LIMIT_SEARCH_SITE", "300"))   # 300 req/min per site
LEAD_IP_LIMIT = int(os.getenv("WARPWEB_RATE_LIMIT_LEAD_IP", "10"))           # 10 req/min per IP
LEAD_SITE_LIMIT = int(os.getenv("WARPWEB_RATE_LIMIT_LEAD_SITE", "50"))       # 50 req/min per site

search_ip_limiter = SlidingWindowRateLimiter(default_limit=SEARCH_IP_LIMIT, window_seconds=60, name="search_ip")
search_site_limiter = SlidingWindowRateLimiter(default_limit=SEARCH_SITE_LIMIT, window_seconds=60, name="search_site")

lead_ip_limiter = SlidingWindowRateLimiter(default_limit=LEAD_IP_LIMIT, window_seconds=60, name="lead_ip")
lead_site_limiter = SlidingWindowRateLimiter(default_limit=LEAD_SITE_LIMIT, window_seconds=60, name="lead_site")

def get_client_ip(request: Request) -> str:
    """Safely extracts client IP, honoring X-Forwarded-For if available."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in chain is client IP
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

def rate_limit_search(request: Request, site_id: str):
    ip = get_client_ip(request)
    search_ip_limiter.check(f"ip:{ip}", client_type="IP")
    search_site_limiter.check(f"site:{site_id}", client_type="site")

def rate_limit_leads(request: Request, site_id: str):
    ip = get_client_ip(request)
    lead_ip_limiter.check(f"ip:{ip}", client_type="IP")
    lead_site_limiter.check(f"site:{site_id}", client_type="site")
