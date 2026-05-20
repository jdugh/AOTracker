#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrateur quotidien — lance les deux scrapers (BOAMP + PLACE)
et envoie une notification Pushbullet si au moins un nouvel AO a été inséré.

Usage:
  python run_daily.py
"""

import os

from dotenv import load_dotenv

from boampgetter import BoampScraper
from place import PlaceScraper
from services.config_utils import load_config
from services.database import AOPersistence
from services.source_runner import run_scraper
from services.notifications import send_daily_summary_notification

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()


def main() -> int:
    config = load_config()
    persistence = AOPersistence()

    boamp_records = run_scraper(BoampScraper(config))
    place_records = run_scraper(PlaceScraper(config))

    boamp_inserts, boamp_updates = persistence.persist_records(boamp_records)
    place_inserts, place_updates  = persistence.persist_records(place_records)

    total_inserts = boamp_inserts + place_inserts

    print("\n" + "=" * 60)
    print(f"  BOAMP : {boamp_inserts} insert(s), {boamp_updates} update(s)")
    print(f"  PLACE : {place_inserts} insert(s), {place_updates} update(s)")
    print(f"  TOTAL : {total_inserts} nouveau(x) AO inséré(s)")
    print("=" * 60)

    if total_inserts > 0:
        send_daily_summary_notification(boamp_inserts, place_inserts)
    else:
        print("Aucun nouvel AO — pas de notification.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
