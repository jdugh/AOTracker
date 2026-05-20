import sys
from typing import List

from services.scraper import BaseScraper
from services.database import AORecord


def run_scraper(scraper: BaseScraper) -> List[AORecord]:
    """Lance un scraper avec affichage standardisé et gestion d'erreur."""
    print("=" * 60)
    print(f"  {scraper.source_name()} — Scraping")
    print("=" * 60)
    try:
        records = scraper.scrape()
        print(f"{scraper.source_name()} : {len(records)} AO récupéré(s)")
        return records
    except Exception as exc:
        print(f"Erreur {scraper.source_name()} : {exc}", file=sys.stderr)
        return []
