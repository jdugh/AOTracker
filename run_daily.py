#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrateur quotidien — lance les deux scrapers (BOAMP + PLACE)
et envoie une notification Pushbullet si au moins un nouvel AO a été inséré.

Usage:
  python run_daily.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from boampgetter import BoampScraper
from place import PlaceScraper
from services.config_utils import load_config
from services.database import AOPersistence
from services.source_runner import run_scraper
from services.notifications import send_daily_summary_notification

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()


def _resolve_dce_storage_root(raw_path: str) -> Path:
    candidate = Path(raw_path.strip() or "dce_storage")
    if candidate.is_absolute():
        return candidate
    config_base = Path("config.local.cfg") if Path("config.local.cfg").exists() else Path("config.cfg")
    return config_base.resolve().parent / candidate


def main() -> int:
    config = load_config()
    persistence = AOPersistence()

    boamp_scraper = BoampScraper(config)
    place_scraper = PlaceScraper(config)

    boamp_records = run_scraper(boamp_scraper)
    place_records = run_scraper(place_scraper)

    boamp_inserted, boamp_updated = persistence.persist_records(boamp_records)
    place_inserted, place_updated = persistence.persist_records(place_records)
    dce_success = dce_failed = 0
    if place_inserted:
        storage_root = _resolve_dce_storage_root(config.get("DCE", "STORAGE_PATH", fallback="dce_storage"))
        dce_results = place_scraper.download_dce_for_new_records(place_inserted, storage_root)
        for reference, result in dce_results.items():
            persistence.db.update_dce_status(
                reference=reference,
                downloaded=result.downloaded,
                local_path=result.extracted_dir,
                error_message=result.error_message,
            )
            if result.downloaded:
                dce_success += 1
            else:
                dce_failed += 1

    total_inserts = len(boamp_inserted) + len(place_inserted)

    print("\n" + "=" * 60)
    print(f"  BOAMP : {len(boamp_inserted)} insert(s), {len(boamp_updated)} update(s)")
    print(f"  PLACE : {len(place_inserted)} insert(s), {len(place_updated)} update(s)")
    print(f"  TOTAL : {total_inserts} nouveau(x) AO inséré(s)")
    print("=" * 60)

    if total_inserts > 0:
        send_daily_summary_notification(len(boamp_inserted), len(place_inserted))
    else:
        print("Aucun nouvel AO — pas de notification.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
