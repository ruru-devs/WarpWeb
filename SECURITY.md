# WarpWeb Security Policy & Architecture

This document describes the security architecture, authentication model, access controls, rate limiting defaults, and vulnerability reporting procedures for WarpWeb.

---

## 1. Authentication & Tenant Isolation Model

WarpWeb separates public visitor actions (querying the search engine, submitting fallback leads, recording telemetry) from owner-facing administration (viewing query logs, configuring overrides, managing synonyms, triggering crawlers, exporting or purging data).

### Site API Keys
- Each site registered in WarpWeb possesses a dedicated API key (`X-API-Key` or `Authorization: Bearer <key>`).
- API keys are hashed with **SHA-256** prior to persistence in the database; plaintext API keys are never stored.
- Authentication checks use constant-time comparisons (`hmac.compare_digest`) to prevent timing attacks against key hashes.

### Strict Tenant Authorization
- Every authenticated endpoint (`/api/analytics/{site_id}`, `/api/overrides/{site_id}`, `/api/synonyms/{site_id}`, `/api/crawl/{site_id}`, `/api/export/{site_id}`, `/api/site-data/{site_id}`) validates that the provided API key matches the requested `site_id`.
- Site data is strictly partitioned by `site_id` in SQLite. A valid API key for Site A cannot view, mutate, or export data belonging to Site B (returns `403 Forbidden`).

---

## 2. Origin Restrictions & CORS

- **CORS Allowed Origins**: Configurable via the `WARPWEB_ALLOWED_ORIGINS` environment variable (default: `http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000`).
- Wildcard `*` origins are disabled for endpoints requiring authentication or credentials.
- In production, configure `WARPWEB_ALLOWED_ORIGINS` with the exact domains hosting the WarpWeb owner dashboard and authorized embedded host sites.

---

## 3. Rate Limiting Defaults

WarpWeb enforces memory-based sliding-window rate limiting on all public visitor endpoints to mitigate abuse, scraping, and brute-force attacks:

| Endpoint | Target | Limit | Window | Action on Exceeded |
| :--- | :--- | :--- | :--- | :--- |
| `POST /api/search` | Remote IP | 60 requests | 60 seconds | `429 Too Many Requests` |
| `POST /api/search` | Site ID | 600 requests | 60 seconds | `429 Too Many Requests` |
| `POST /api/leads` | Remote IP | 5 requests | 60 seconds | `429 Too Many Requests` |
| `POST /api/leads` | Site ID | 30 requests | 60 seconds | `429 Too Many Requests` |

Rate limiters automatically clean up stale timestamps and can be tuned or replaced with Redis-backed token buckets for multi-instance deployments.

---

## 4. Input Validation & XSS Defense

### Backend Validation
- All inbound query payloads, lead requests, synonym rules, and overrides are strictly validated using Pydantic v2 schemas.
- Max lengths, character set regexes, and data types are enforced at the API boundary:
  - `query`: max 300 characters.
  - `site_id`: alphanumeric with `-`, `_`, `.` (max 100 characters).
  - `visitor_contact`: min 3, max 150 characters.
  - `override target_url`: validated against the site's registered domain. External domains, relative traversals, `javascript:`, and `data:` schemes are rejected with `400 Bad Request`.

### Client Widget Defense (Shadow DOM)
- The client widget (`warpweb.ts` / `warpweb.js`) creates UI elements exclusively via safe DOM node construction (`document.createElement`, `textContent`, `setAttribute`).
- Dynamic queries, search snippets, and server responses are **never** interpolated into `innerHTML`.
- Target navigation URLs are sanitized before assignment: only `http:` and `https:` protocols are permitted.

---

## 5. Compliance, Consent & Data Retention

- **Visitor Consent**: The lead fallback modal includes an explicit, interactive consent notice. When submitted, the backend stores `consent=1`, `consent_text`, and a microsecond-precision `consent_timestamp`.
- **GDPR / Data Subject Rights**:
  - `GET /api/export/{site_id}`: Exports all leads, queries, feedback, and telemetry for a site in JSON format.
  - `DELETE /api/leads/{site_id}/{lead_id}`: Immediately removes an individual lead upon erasure request.
  - `DELETE /api/site-data/{site_id}`: Purges all stored data, indexed sections, and telemetry for a site.
- **Automated Retention Cleanup**:
  - `POST /api/cleanup/{site_id}` accepts a retention window (default: 90 days) and purges old logs, clicks, feedback, and lead records past the threshold.

---

## 6. Vulnerability Reporting

If you discover a potential security vulnerability in WarpWeb:
1. **Do not open a public issue.**
2. Report the vulnerability privately to the WarpWeb security team via GitHub Security Advisories or by emailing `security@warpweb.ai`.
3. Provide a clear description, reproduction steps, and proof of concept if applicable.
4. We acknowledge reports within 48 hours and work to release patches promptly.
