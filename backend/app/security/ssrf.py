"""
SSRF Protection and Domain Validation for WarpWeb.
Defends against:
- Internal network / loopback scanning (127.0.0.1, ::1)
- Cloud metadata service theft (169.254.169.254, fe80::/10)
- RFC1918 private network access (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
- DNS rebinding attacks via IP-pinning connection validation
- Open redirects to unvalidated destinations
- Hostname confusion & suffix injection (notexample.com, example.com.evil.net)
- Userinfo impersonation (example.com@evil.com)
"""

import socket
import ipaddress
import urllib.parse
from typing import Optional, Tuple, List, Set
import httpcore
import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024   # 2 MB per page
MAX_TOTAL_CRAWL_BYTES = 20 * 1024 * 1024 # 20 MB total per site crawl
REQUEST_TIMEOUT = 8.0                  # 8 seconds per request


class PinnedBackend(httpcore.SyncBackend):
    """Network backend that connects to a pre-validated, pinned IP to defeat DNS rebinding."""
    def __init__(self, pinned_ip: str):
        self.pinned_ip = pinned_ip

    def connect_tcp(self, host: str, port: int, timeout=None, local_address=None, socket_options=None):
        return super().connect_tcp(
            self.pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options
        )


class PinnedHTTPTransport(httpx.HTTPTransport):
    """HTTPTransport that binds socket connection to the validated pinned IP."""
    def __init__(self, pinned_ip: str, **kwargs):
        super().__init__(**kwargs)
        self._pool._network_backend = PinnedBackend(pinned_ip)


def clean_hostname(host_or_domain: str) -> str:
    """Strips port and lowercase normalizes a domain string."""
    cleaned = host_or_domain.strip().lower()
    if ":" in cleaned and not cleaned.startswith("["):
        cleaned = cleaned.split(":")[0]
    return cleaned


def is_safe_domain(candidate_url_or_host: str, target_domain: str) -> bool:
    """
    Validates that a URL or hostname strictly belongs to target_domain.
    Rules:
    - Only 'http' and 'https' schemes are permitted.
    - Userinfo (user:pass@) is strictly forbidden.
    - Hostname must match target_domain exactly, or be a dot-separated subdomain (.target_domain).
    - Prevents suffix injection: notexample.com or example.com.attacker.com are rejected.
    - Handles www. symmetry (www.target.com matches target.com).
    """
    if not candidate_url_or_host or not target_domain:
        return False

    clean_target = clean_hostname(target_domain)

    # Determine if input is a full URL or a raw hostname
    if "://" in candidate_url_or_host:
        try:
            parsed = urllib.parse.urlsplit(candidate_url_or_host)
        except Exception:
            return False

        if parsed.scheme not in ("http", "https"):
            return False

        # Reject userinfo tricks (e.g. https://target.com@evil.com)
        if parsed.username or parsed.password:
            return False

        candidate_host = clean_hostname(parsed.hostname or "")
    else:
        candidate_host = clean_hostname(candidate_url_or_host)

    if not candidate_host:
        return False

    # Exact equality
    if candidate_host == clean_target:
        return True

    # www. symmetry
    if clean_target.startswith("www."):
        bare_target = clean_target[4:]
        if candidate_host == bare_target:
            return True
        if candidate_host.endswith(f".{bare_target}"):
            return True
    else:
        if candidate_host == f"www.{clean_target}":
            return True
        if candidate_host.endswith(f".{clean_target}"):
            return True

    return False


def is_private_or_reserved_ip(ip_str: str) -> bool:
    """
    Checks if an IP address string is loopback, private (RFC1918), link-local (169.254.x.x),
    unique-local (IPv6), multicast, or reserved.
    Also unpacks IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1).
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Unpack IPv4-mapped IPv6 addresses
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        return (
            ip.is_loopback or
            ip.is_private or
            ip.is_link_local or
            ip.is_multicast or
            ip.is_reserved or
            ip.is_unspecified
        )
    except ValueError:
        return True


def resolve_and_validate_url(
    url: str,
    allowed_domain: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Resolves DNS for a URL's hostname and verifies that all resolved IPs are public.
    If allowed_domain is provided, enforces is_safe_domain.
    Returns: (is_safe: bool, validated_ip: Optional[str], error_message: Optional[str])
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False, None, "Malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, None, f"Unsupported scheme '{parsed.scheme}'. Only http and https allowed."

    if parsed.username or parsed.password:
        return False, None, "Userinfo credentials in URL are prohibited."

    hostname = clean_hostname(parsed.hostname or "")
    if not hostname:
        return False, None, "Missing hostname in URL."

    if allowed_domain and not is_safe_domain(url, allowed_domain):
        return False, None, f"URL domain '{hostname}' does not match allowed domain '{allowed_domain}'."

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # DNS Resolution
    try:
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, None, f"DNS resolution failed for '{hostname}': {e}"

    if not addr_info:
        return False, None, f"No IP address found for '{hostname}'."

    # Validate EVERY resolved IP address
    resolved_ip = None
    for entry in addr_info:
        sockaddr = entry[4]
        ip_addr = sockaddr[0]

        if is_private_or_reserved_ip(ip_addr):
            return False, None, f"Host '{hostname}' resolved to private/reserved IP '{ip_addr}'."

        if not resolved_ip:
            resolved_ip = ip_addr

    return True, resolved_ip, None


def safe_fetch_page(
    url: str,
    allowed_domain: Optional[str] = None,
    max_redirects: int = 5,
    user_agent: str = "WarpWeb-Bot/1.0",
    max_bytes: int = MAX_RESPONSE_BYTES
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Performs an SSRF-safe HTTP GET request:
    - Validates domain & resolves DNS before connecting.
    - Pins the validated IP using PinnedHTTPTransport to defeat DNS rebinding.
    - Manually follows redirects, re-validating EVERY hop against SSRF rules.
    - Enforces response size cap and request timeout.
    Returns: (html_content: Optional[str], final_url: Optional[str], error: Optional[str])
    """
    current_url = url
    visited_urls: Set[str] = set()

    for hop in range(max_redirects + 1):
        if current_url in visited_urls:
            return None, current_url, "Redirect loop detected"
        visited_urls.add(current_url)

        is_safe, resolved_ip, err = resolve_and_validate_url(current_url, allowed_domain)
        if not is_safe:
            return None, current_url, f"SSRF check failed at hop {hop}: {err}"

        try:
            transport = PinnedHTTPTransport(resolved_ip) if resolved_ip else None
            with httpx.Client(
                transport=transport,
                follow_redirects=False,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": user_agent}
            ) as client:
                res = client.get(current_url)

                if res.is_redirect or res.status_code in (301, 302, 303, 307, 308):
                    location = res.headers.get("Location")
                    if not location:
                        return None, current_url, "Redirect response missing Location header"
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue

                if res.status_code != 200:
                    return None, current_url, f"HTTP status {res.status_code}"

                # Enforce response byte limit
                content_length = res.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    return None, current_url, f"Response size {content_length} exceeds limit of {max_bytes} bytes"

                body_bytes = res.content
                if len(body_bytes) > max_bytes:
                    return None, current_url, f"Body size {len(body_bytes)} exceeds limit of {max_bytes} bytes"

                return res.text, current_url, None

        except Exception as e:
            return None, current_url, f"Network error during fetch: {str(e)}"

    return None, current_url, "Too many redirects"


def safe_fetch_bytes(
    url: str,
    allowed_domain: Optional[str] = None,
    max_redirects: int = 5,
    user_agent: str = "WarpWeb-Bot/1.0",
    max_bytes: int = MAX_RESPONSE_BYTES
) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """
    Performs an SSRF-safe HTTP GET request returning raw bytes (for PDF documents).
    Pins the validated IP to defeat DNS rebinding.
    """
    current_url = url
    visited_urls: Set[str] = set()

    for hop in range(max_redirects + 1):
        if current_url in visited_urls:
            return None, current_url, "Redirect loop detected"
        visited_urls.add(current_url)

        is_safe, resolved_ip, err = resolve_and_validate_url(current_url, allowed_domain)
        if not is_safe:
            return None, current_url, f"SSRF check failed at hop {hop}: {err}"

        try:
            transport = PinnedHTTPTransport(resolved_ip) if resolved_ip else None
            with httpx.Client(
                transport=transport,
                follow_redirects=False,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": user_agent}
            ) as client:
                res = client.get(current_url)

                if res.is_redirect or res.status_code in (301, 302, 303, 307, 308):
                    location = res.headers.get("Location")
                    if not location:
                        return None, current_url, "Redirect response missing Location header"
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue

                if res.status_code != 200:
                    return None, current_url, f"HTTP status {res.status_code}"

                content_length = res.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    return None, current_url, f"Response size exceeds {max_bytes} bytes"

                body_bytes = res.content
                if len(body_bytes) > max_bytes:
                    return None, current_url, f"Body size exceeds {max_bytes} bytes"

                return body_bytes, current_url, None

        except Exception as e:
            return None, current_url, f"Network error during fetch: {str(e)}"

    return None, current_url, "Too many redirects"
