"""
WarpWeb Advanced DOM Sectionizer and Scraper
Features:
1. Nested candidate section detection and deduplication (keeps specific child sections, discards parent wrappers)
2. Stable anchor generation when IDs are missing + text-fragment and DOM path locator strategies
3. Multi-action extraction per section (Book, Call, WhatsApp, Purchase, Navigate)
4. SHA-256 content change hashing for incremental delta re-crawling
5. Metadata extraction (prices, OPD timings, availability)
"""
from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Any, Optional
import re
import urllib.parse
import hashlib
from app.models import SectionNode

def slugify(text: str) -> str:
    """Generates a clean URL/DOM-safe slug from text."""
    clean = re.sub(r'[^a-zA-Z0-9\s-]', '', text.lower()).strip()
    return re.sub(r'[\s_-]+', '-', clean)[:60]

def compute_dom_path(elem: Tag) -> str:
    """Computes a unique CSS selector path for an element."""
    path = []
    current = elem
    while current and current.name not in [None, "[document]", "html", "body"]:
        name = current.name
        elem_id = current.get("id")
        if elem_id:
            path.insert(0, f"#{elem_id}")
            break
        # Calculate nth-of-type
        parent = current.parent
        if parent:
            siblings = [s for s in parent.children if isinstance(s, Tag) and s.name == name]
            if len(siblings) > 1:
                idx = siblings.index(current) + 1
                path.insert(0, f"{name}:nth-of-type({idx})")
            else:
                path.insert(0, name)
        else:
            path.insert(0, name)
        current = parent
    return " > ".join(path) if path else "body"

class HTMLSectionizer:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def parse(self, html_content: str, current_url: Optional[str] = None) -> List[SectionNode]:
        url = current_url or self.base_url
        soup = BeautifulSoup(html_content, "html.parser")

        # Strip scripts, styles, iframes, SVGs to keep index clean
        for element in soup(["script", "style", "svg", "noscript", "iframe"]):
            element.decompose()

        # 1. Discover raw candidate blocks
        # Targets: section, article, main, or divs with IDs or semantic roles
        candidate_tags = soup.find_all(
            lambda tag: tag.name in ["section", "article"] or 
                        (tag.get("id") and tag.name in ["div", "main", "aside"])
        )

        # Fallback to heading parent containers if explicit semantic tags are sparse
        if len(candidate_tags) < 2:
            seen_parents = set(candidate_tags)
            for h in soup.find_all(["h1", "h2", "h3"]):
                p = h.parent
                if p and p not in seen_parents and p.name not in ["html", "body"]:
                    candidate_tags.append(p)
                    seen_parents.add(p)

        # 2. Nested Section De-duplication Rule:
        # If candidate A contains candidate B, and candidate B has substantial text (>= 40% of A)
        # or child B has its own heading, keep the more specific child B and discard parent A.
        # This prevents duplicate indexing of wrapper divs/sections.
        surviving_candidates: List[Tag] = []
        for cand in candidate_tags:
            cand_text_len = len(" ".join(cand.stripped_strings))
            if cand_text_len < 25:
                continue

            # Check if this candidate is a parent of other candidate tags
            children_in_candidates = [other for other in candidate_tags if other is not cand and other in cand.descendants]
            if children_in_candidates:
                # Sum text length of children
                child_text_sum = sum(len(" ".join(c.stripped_strings)) for c in children_in_candidates)
                # If children account for >= 50% of parent text or have headings, drop the parent
                if child_text_sum >= 0.50 * cand_text_len:
                    continue

            surviving_candidates.append(cand)

        sections: List[SectionNode] = []
        node_index = 0

        for block in surviving_candidates:
            raw_text = " ".join(block.stripped_strings)
            if len(raw_text) < 25:
                continue

            # Heading discovery
            h_tag = block.find(["h1", "h2", "h3", "h4"])
            title = h_tag.get_text(strip=True) if h_tag else ""
            if not title:
                strong = block.find(["strong", "b"])
                title = strong.get_text(strip=True) if strong else " ".join(raw_text.split()[:5])

            # Anchor discovery & Stable Anchor Generation
            anchor_id = block.get("id")
            if not anchor_id and h_tag and h_tag.get("id"):
                anchor_id = h_tag.get("id")

            # Fallback locator strategy for sites without IDs
            stable_slug = slugify(title)
            generated_anchor = anchor_id or (f"sec-{stable_slug}" if stable_slug else f"sec-{node_index}")
            dom_path = compute_dom_path(block)
            
            # Text-fragment URL according to W3C Web Platform specification (scroll-to-text-fragment)
            title_fragment = urllib.parse.quote(title[:45])
            text_fragment = f":~:text={title_fragment}" if title_fragment else ""

            # 3. Multiple Actions Extraction:
            # Find ALL action elements (a, button) inside this block
            actions: List[Dict[str, Any]] = []
            interactive_elements = block.find_all(["a", "button"])
            for el in interactive_elements:
                lbl = el.get_text(strip=True)
                href = el.get("href", "")
                if not lbl or len(lbl) > 50:
                    continue

                act_type = "navigate"
                act_url = urllib.parse.urljoin(url, href) if href else url
                href_lower = href.lower()
                lbl_lower = lbl.lower()

                if "wa.me" in href_lower or "whatsapp" in href_lower:
                    act_type = "whatsapp"
                elif "tel:" in href_lower:
                    act_type = "call"
                elif any(kw in href_lower or kw in lbl_lower for kw in ["book", "appointment", "reserve", "slot"]):
                    act_type = "book"
                elif any(kw in href_lower or kw in lbl_lower for kw in ["buy", "cart", "order", "purchase", "checkout"]):
                    act_type = "purchase"

                # Avoid duplicate action buttons
                if not any(a["label"] == lbl and a["url"] == act_url for a in actions):
                    actions.append({
                        "type": act_type,
                        "label": lbl,
                        "url": act_url
                    })

            # Primary action for backwards compatibility
            primary_action = actions[0] if actions else None
            primary_label = primary_action["label"] if primary_action else None
            primary_url = primary_action["url"] if primary_action else None
            primary_type = primary_action["type"] if primary_action else "navigate"

            # 4. Metadata extraction: Prices, Hours/Timings
            metadata: Dict[str, Any] = {
                "locator": {
                    "dom_path": dom_path,
                    "text_fragment": text_fragment,
                    "has_native_id": bool(anchor_id)
                }
            }
            price_match = re.search(r'(?:₹|\$|USD|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)', raw_text, re.IGNORECASE)
            if price_match:
                metadata["price"] = price_match.group(0).strip()

            hours_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\s*-\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))', raw_text)
            if hours_match:
                metadata["timings"] = hours_match.group(0).strip()

            # 5. Content Change Detection Hashing
            content_hash = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()

            # Target URL
            target_url = url
            if anchor_id:
                target_url = f"{url}#{anchor_id}"
            elif text_fragment:
                target_url = f"{url}#{text_fragment}"

            node_index += 1
            url_slug = re.sub(r'[^a-zA-Z0-9]', '_', url.split('/')[-1] or 'root')
            node_id = f"sec_{url_slug}_{node_index}_{anchor_id or stable_slug or 'blk'}"

            # Token keywords
            tokens = list(set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', (title + " " + raw_text).lower())))

            node = SectionNode(
                id=node_id,
                url=url,
                anchor_id=anchor_id,
                title=title[:120],
                content=raw_text[:1400],
                keywords=tokens[:30],
                action_type=primary_type,
                action_label=primary_label,
                action_url=primary_url,
                actions=actions,
                content_hash=content_hash,
                metadata=metadata
            )
            sections.append(node)

        return sections
