"""
Multi-Page Crawl & Ingestion Pipeline for WarpWeb
Recursively or batch-indexes local HTML or live domains, parsing all subpages into a unified
cross-page knowledge graph with anchor preservation.
"""
import os
import glob
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup
from app.crawler.sectionizer import HTMLSectionizer
from app.models import SectionNode
from app.db.storage import DatabaseManager
from app.indexer.hybrid_search import HybridIndex

def index_folder_site(
    site_id: str, 
    domain: str, 
    name: str, 
    folder_path: str, 
    base_web_url: str
) -> int:
    """
    Crawls all HTML files inside a site directory, constructs canonical cross-page URLs,
    extracts deep anchor sections, and stores in database & hybrid index.
    """
    db = DatabaseManager()
    all_sections: List[SectionNode] = []
    
    html_files = glob.glob(os.path.join(folder_path, "**/*.html"), recursive=True)
    print(f"[{name}] Found {len(html_files)} pages to index from {folder_path}...")

    for file_path in html_files:
        rel_path = os.path.relpath(file_path, folder_path)
        # Construct web accessible URL for this page
        page_url = f"{base_web_url.rstrip('/')}/{rel_path.replace(os.sep, '/')}"
        
        with open(file_path, "r", encoding="utf-8") as f:
            html = f.read()

        sectionizer = HTMLSectionizer(base_url=page_url)
        page_sections = sectionizer.parse(html, current_url=page_url)
        all_sections.extend(page_sections)
        print(f"  -> Indexed {len(page_sections)} sections from {rel_path}")

    # Persist site & all sections
    db.save_site(site_id, domain, name)
    db.save_sections(site_id, all_sections)

    # Precompute and persist dense embeddings into SQLite
    index = HybridIndex(site_id)
    index.index_sections(all_sections, db_manager=db)

    print(f"[{name}] Successfully indexed total of {len(all_sections)} cross-page sections (with embeddings)!")
    return len(all_sections)

if __name__ == "__main__":
    # 1. Index Multi-Page ApexCare Hospital Site
    index_folder_site(
        site_id="apexcare-clinic",
        domain="apexcareclinic.com",
        name="Apex Care Specialty Hospital",
        folder_path="demo/apexcare",
        base_web_url="http://localhost:3000/demo/apexcare"
    )

    # 2. Index Multi-Page PulseTech D2C Commerce Site
    index_folder_site(
        site_id="shoppulse-commerce",
        domain="pulsetechaudio.com",
        name="PulseTech Pro Audio & Electronics",
        folder_path="demo/shoppulse",
        base_web_url="http://localhost:3000/demo/shoppulse"
    )
