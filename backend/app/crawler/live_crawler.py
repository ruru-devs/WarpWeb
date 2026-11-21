"""
WarpWeb Live-Domain Crawler
Features:
1. Recursive breadth-first live domain crawl (internal links only)
2. Configurable depth limit, page limit, and URL deduplication
3. robots.txt parsing and compliance (urllib.robotparser)
4. SHA-256 incremental change detection: skips unchanged sections on re-crawl
5. Optional Playwright headless JS rendering behind a flag (default static httpx/BeautifulSoup)
6. Linked PDF document text extraction via pypdf into indexed sections
"""
import os
import re
import urllib.parse
import urllib.robotparser
from typing import List, Dict, Set, Optional, Tuple, Any
from collections import deque
import hashlib
import httpx
from bs4 import BeautifulSoup

from app.crawler.sectionizer import HTMLSectionizer
from app.models import SectionNode
from app.db.storage import DatabaseManager
from app.indexer.hybrid_search import HybridIndex
from app.security.ssrf import (
    is_safe_domain,
    resolve_and_validate_url,
    safe_fetch_page,
    safe_fetch_bytes,
    clean_hostname,
    MAX_TOTAL_CRAWL_BYTES
)

USER_AGENT = "WarpWebBot/1.0 (+https://warpweb.io/bot)"

def normalize_url(url: str) -> str:
    """Canonicalizes a URL by stripping fragments, trailing slashes, and sorting params."""
    parsed = urllib.parse.urlparse(url)
    # Strip fragment
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urllib.parse.urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        parsed.query,
        ""
    ))

def is_same_domain(url1: str, url2: str) -> bool:
    """
    Strict hostname equality and dot-boundary subdomain validation.
    Prevents suffix injection (e.g. notexample.com or example.com.evil.net)
    and userinfo spoofing (example.com@evil.com).
    """
    try:
        p2 = urllib.parse.urlsplit(url2) if "://" in url2 else None
        target = p2.hostname if p2 and p2.hostname else clean_hostname(url2)
        return is_safe_domain(url1, target)
    except Exception:
        return False

class LiveCrawler:
    def __init__(
        self,
        site_id: str,
        start_url: str,
        max_pages: int = 50,
        max_depth: int = 3,
        respect_robots: bool = True,
        use_playwright: bool = False,
        index_pdfs: bool = True,
        max_total_bytes: int = MAX_TOTAL_CRAWL_BYTES
    ):
        self.site_id = site_id
        self.start_url = start_url
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.respect_robots = respect_robots
        self.use_playwright = use_playwright
        self.index_pdfs = index_pdfs
        self.max_total_bytes = max_total_bytes
        self.total_bytes_crawled = 0
        self.db = DatabaseManager()

        parsed = urllib.parse.urlsplit(start_url)
        self.base_domain = clean_hostname(parsed.hostname or "")
        self.scheme = parsed.scheme.lower() or "https"

        # Initialize robots.txt parser with SSRF validation
        self.robot_parser = urllib.robotparser.RobotFileParser()
        if self.respect_robots and self.base_domain:
            try:
                robots_url = f"{self.scheme}://{self.base_domain}/robots.txt"
                content, _, err = safe_fetch_page(
                    robots_url,
                    allowed_domain=self.base_domain,
                    max_bytes=512 * 1024,
                    user_agent=USER_AGENT
                )
                if content:
                    self.robot_parser.parse(content.splitlines())
            except Exception:
                pass

    def can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            return self.robot_parser.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def extract_links(self, html: str, current_url: str) -> Tuple[List[str], List[str]]:
        """Extracts internal page links and linked PDF files."""
        page_links = []
        pdf_links = []
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            abs_url = urllib.parse.urljoin(current_url, href)
            clean_url = normalize_url(abs_url)

            if not is_same_domain(clean_url, self.start_url):
                continue

            if clean_url.lower().endswith(".pdf"):
                pdf_links.append(clean_url)
            else:
                page_links.append(clean_url)

        return page_links, pdf_links

    def fetch_page(self, url: str) -> Optional[str]:
        """Fetches page content with SSRF defenses using either static httpx or Playwright."""
        if self.total_bytes_crawled >= self.max_total_bytes:
            return None

        if self.use_playwright:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(user_agent=USER_AGENT)

                    # Intercept and validate every subrequest to prevent SSRF
                    def route_handler(route):
                        req_url = route.request.url
                        is_safe, _, _ = resolve_and_validate_url(req_url, allowed_domain=self.base_domain)
                        if not is_safe:
                            route.abort()
                        else:
                            route.continue_()

                    page.route("**/*", route_handler)
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    content = page.content()
                    browser.close()

                    content_len = len(content.encode("utf-8"))
                    if self.total_bytes_crawled + content_len > self.max_total_bytes:
                        return None
                    self.total_bytes_crawled += content_len
                    return content
            except Exception:
                # Fallback to static fetch if Playwright fails
                pass

        try:
            content, _, err = safe_fetch_page(
                url,
                allowed_domain=self.base_domain,
                user_agent=USER_AGENT
            )
            if not content:
                return None

            content_len = len(content.encode("utf-8"))
            if self.total_bytes_crawled + content_len > self.max_total_bytes:
                return None
            self.total_bytes_crawled += content_len
            return content
        except Exception:
            return None

    def extract_pdf_sections(self, pdf_url: str) -> List[SectionNode]:
        """Extracts text from linked PDF documents and turns them into sections with page references."""
        if not self.index_pdfs or self.total_bytes_crawled >= self.max_total_bytes:
            return []

        sections: List[SectionNode] = []
        try:
            import io
            import pypdf

            pdf_bytes, _, err = safe_fetch_bytes(
                pdf_url,
                allowed_domain=self.base_domain,
                user_agent=USER_AGENT
            )
            if not pdf_bytes:
                return []

            if self.total_bytes_crawled + len(pdf_bytes) > self.max_total_bytes:
                return []
            self.total_bytes_crawled += len(pdf_bytes)

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pdf_name = pdf_url.split("/")[-1] or "Document.pdf"

            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                clean_text = " ".join(text.split()).strip()
                if len(clean_text) < 40:
                    continue

                title = f"{pdf_name} - Page {page_num}"
                content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
                slug = re.sub(r'[^a-zA-Z0-9]', '_', pdf_name)[:30]
                node_id = f"sec_pdf_{slug}_p{page_num}"

                sections.append(SectionNode(
                    id=node_id,
                    url=f"{pdf_url}#page={page_num}",
                    anchor_id=f"page-{page_num}",
                    title=title,
                    content=clean_text[:1400],
                    keywords=list(set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', clean_text.lower())))[:25],
                    action_type="navigate",
                    action_label="Open PDF Page",
                    action_url=f"{pdf_url}#page={page_num}",
                    content_hash=content_hash,
                    metadata={"format": "pdf", "page": page_num, "filename": pdf_name}
                ))
        except Exception:
            pass

        return sections

    def crawl_and_index(self) -> Dict[str, Any]:
        """
        Executes live crawl, parses sections, detects delta changes via content_hash,
        and saves updated sections to database and hybrid index.
        """
        self.db.update_crawl_job(self.site_id, status="running", pages_crawled=0, sections_indexed=0)

        visited_urls: Set[str] = set()
        queue: deque = deque([(self.start_url, 0)]) # (url, depth)
        all_sections: List[SectionNode] = []
        discovered_pdfs: Set[str] = set()

        # Load existing sections for content change detection
        existing_sections = self.db.get_sections(self.site_id)
        existing_hashes = {s.content_hash: s for s in existing_sections if s.content_hash}
        existing_embeddings = self.db.get_section_embeddings(self.site_id)

        pages_crawled = 0

        try:
            while queue and len(visited_urls) < self.max_pages:
                curr_url, depth = queue.popleft()
                norm_curr = normalize_url(curr_url)
                if norm_curr in visited_urls:
                    continue

                if depth > self.max_depth or not self.can_fetch(norm_curr):
                    continue

                visited_urls.add(norm_curr)
                html = self.fetch_page(norm_curr)
                if not html:
                    continue

                pages_crawled += 1

                # Parse sections with sectionizer
                sectionizer = HTMLSectionizer(base_url=norm_curr)
                page_sections = sectionizer.parse(html, current_url=norm_curr)

                # Content change detection: reuse embeddings if content hash is unchanged
                for s in page_sections:
                    if s.content_hash and s.content_hash in existing_hashes:
                        prev_s = existing_hashes[s.content_hash]
                        if prev_s.id in existing_embeddings:
                            existing_embeddings[s.id] = existing_embeddings[prev_s.id]

                all_sections.extend(page_sections)

                # Discover new links
                if depth < self.max_depth:
                    new_links, pdfs = self.extract_links(html, norm_curr)
                    for pdf in pdfs:
                        discovered_pdfs.add(pdf)
                    for link in new_links:
                        if link not in visited_urls:
                            queue.append((link, depth + 1))

                self.db.update_crawl_job(
                    self.site_id,
                    status="running",
                    pages_crawled=pages_crawled,
                    sections_indexed=len(all_sections)
                )

            # Process discovered PDFs
            for pdf_url in discovered_pdfs:
                pdf_sections = self.extract_pdf_sections(pdf_url)
                all_sections.extend(pdf_sections)

            # Persist site and sections
            self.db.save_sections(self.site_id, all_sections)

            # Re-index hybrid search
            idx = HybridIndex(self.site_id)
            overrides = self.db.get_overrides(self.site_id)
            synonyms = self.db.get_synonyms(self.site_id)
            idx.set_overrides(overrides)
            idx.set_synonyms(synonyms)
            idx.index_sections(all_sections, cached_embeddings=existing_embeddings, db_manager=self.db)

            self.db.update_crawl_job(
                self.site_id,
                status="completed",
                pages_crawled=pages_crawled,
                sections_indexed=len(all_sections)
            )

            return {
                "status": "completed",
                "site_id": self.site_id,
                "pages_crawled": pages_crawled,
                "sections_indexed": len(all_sections),
                "pdfs_indexed": len(discovered_pdfs)
            }
        except Exception as e:
            self.db.update_crawl_job(
                self.site_id,
                status="failed",
                pages_crawled=pages_crawled,
                sections_indexed=len(all_sections),
                error_message=str(e)
            )
            return {
                "status": "failed",
                "site_id": self.site_id,
                "error": str(e)
            }
