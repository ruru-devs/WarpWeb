"""
WarpWeb Authentication & Tenant Authorization
Implements API Key authentication, constant-time verification, and tenant isolation.
"""
import hashlib
import hmac
import secrets
import urllib.parse
from typing import Optional
from fastapi import Header, HTTPException, Depends
from app.db.storage import DatabaseManager

db = DatabaseManager()

def hash_api_key(raw_key: str) -> str:
    """Computes SHA-256 hash of API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def generate_api_key(prefix: str = "ww_live_") -> str:
    """Generates a cryptographically secure random API key."""
    return f"{prefix}{secrets.token_urlsafe(24)}"

def extract_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """Extracts raw API key from either X-API-Key or Authorization: Bearer <token>."""
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return None

def require_site_auth(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Enforces tenant authorization for owner-facing endpoints:
    Verifies that the provided API key matches the registered owner key for site_id.
    """
    raw_key = extract_api_key(x_api_key, authorization)
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide API key via X-API-Key or Authorization: Bearer header."
        )

    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")

    stored_hash = site.get("api_key_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=500,
            detail="Site has no configured API key. Please re-register or set key."
        )

    provided_hash = hash_api_key(raw_key)
    if not hmac.compare_digest(provided_hash, stored_hash):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: API key is not authorized for site '{site_id}'."
        )

    return site_id

def validate_override_url(target_url: str, site_domain: str):
    """
    Validates override target URL belongs to site domain, anchor, or relative path.
    Rejects dangerous schemes (javascript:, data:) and external domains.
    """
    url_stripped = target_url.strip()
    if not url_stripped:
        raise HTTPException(status_code=400, detail="Target URL cannot be empty.")

    # 1. Anchor link (e.g. #book-appointment)
    if url_stripped.startswith("#"):
        if any(c in url_stripped for c in ["<", ">", "\"", "'", " "]):
            raise HTTPException(status_code=400, detail="Invalid characters in anchor URL.")
        return

    # 2. Relative path (e.g. /doctors.html#doc-sharma)
    if url_stripped.startswith("/") and not url_stripped.startswith("//"):
        return

    # 3. Absolute URL: must parse properly
    try:
        parsed = urllib.parse.urlparse(url_stripped)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format.")

    # Only http and https allowed
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = (parsed.hostname or "").lower()
    site_domain_lower = site_domain.lower()

    # Allowed if host matches domain or subdomain, or localhost in development
    is_same_domain = (hostname == site_domain_lower) or hostname.endswith(f".{site_domain_lower}")
    is_localhost = hostname in ("localhost", "127.0.0.1")

    if not (is_same_domain or is_localhost):
        raise HTTPException(
            status_code=400,
            detail=f"Target URL domain '{hostname}' does not match registered site domain '{site_domain}'."
        )
