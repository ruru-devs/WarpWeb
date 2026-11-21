"""
WarpWeb DOM Sectionizer and Scraper
Takes raw HTML (from crawler or static page) and parses it into distinct, addressable section nodes
with exact anchor IDs, clean text, detected action buttons, and pricing/timings metadata.
"""
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import re
import urllib.parse
from app.models import SectionNode

class HTMLSectionizer:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def parse(self, html_content: str, current_url: Optional[str] = None) -> List[SectionNode]:
        url = current_url or self.base_url
        soup = BeautifulSoup(html_content, "html.parser")

        # Strip scripts, styles, iframes, SVGs to keep index clean
        for element in soup(["script", "style", "svg", "noscript", "iframe"]):
            element.decompose()

        sections: List[SectionNode] = []

        # Find all distinct logical blocks: sections, articles, or major heading boundaries
        raw_sections = soup.find_all(["section", "article", "div"])
        
        # We target elements that have an ID or heading tags (h1, h2, h3, h4)
        processed_elements = set()
        
        # 1. First priority: explicit semantic tags or elements with IDs
        candidates = soup.find_all(lambda tag: tag.name in ["section", "article"] or (tag.get("id") and tag.name in ["div", "main"]))

        # If no explicit semantic sections, cluster around headings
        if not candidates or len(candidates) < 2:
            headings = soup.find_all(["h1", "h2", "h3"])
            for h in headings:
                parent = h.parent
                if parent and parent not in processed_elements:
                    candidates.append(parent)
                    processed_elements.add(parent)

        node_index = 0
        for block in candidates:
            # Skip empty or tiny blocks
            text = " ".join(block.stripped_strings)
            if len(text) < 25:
                continue

            # Heading discovery
            h_tag = block.find(["h1", "h2", "h3", "h4"])
            title = h_tag.get_text(strip=True) if h_tag else ""
            if not title:
                # Try finding strong/b or take first words
                strong = block.find(["strong", "b"])
                title = strong.get_text(strip=True) if strong else " ".join(text.split()[:5])

            # Anchor discovery
            anchor_id = block.get("id")
            if not anchor_id and h_tag and h_tag.get("id"):
                anchor_id = h_tag.get("id")

            # Extract buttons / links in this section (actions)
            action_btn = block.find(["a", "button"])
            action_label = None
            action_url = None
            action_type = "navigate"

            if action_btn:
                action_label = action_btn.get_text(strip=True)
                href = action_btn.get("href", "")
                if href:
                    action_url = urllib.parse.urljoin(url, href)
                    if "wa.me" in href or "whatsapp" in href:
                        action_type = "whatsapp"
                    elif "tel:" in href:
                        action_type = "call"
                    elif any(kw in href.lower() or kw in action_label.lower() for kw in ["book", "appointment", "reserve"]):
                        action_type = "book"
                    elif any(kw in href.lower() or kw in action_label.lower() for kw in ["buy", "cart", "order", "purchase"]):
                        action_type = "purchase"

            # Metadata extraction: Prices, Hours/Timings
            metadata: Dict[str, Any] = {}
            price_match = re.search(r'(?:₹|\$|USD|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)', text, re.IGNORECASE)
            if price_match:
                metadata["price"] = price_match.group(0).strip()

            hours_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\s*-\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))', text)
            if hours_match:
                metadata["timings"] = hours_match.group(0).strip()

            # Target deep link: URL + #anchor
            target_url = url
            if anchor_id:
                target_url = f"{url}#{anchor_id}"

            node_index += 1
            # Unique node id incorporating page url path hash/slug
            url_slug = re.sub(r'[^a-zA-Z0-9]', '_', url.split('/')[-1] or 'root')
            node_id = f"sec_{url_slug}_{node_index}_{anchor_id or 'blk'}"

            # Simple keyword tokens
            tokens = list(set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', (title + " " + text).lower())))

            node = SectionNode(
                id=node_id,
                url=url,
                anchor_id=anchor_id,
                title=title[:120],
                content=text[:1200], # compact snippet for speed
                keywords=tokens[:25],
                action_type=action_type,
                action_label=action_label if action_label and len(action_label) < 30 else None,
                action_url=action_url,
                metadata=metadata
            )
            sections.append(node)

        return sections
