#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper BOAMP — Appels d'offre depuis l'API OpenData BOAMP.

Recherche par mots-clés via l'API v2.1 et retourne une liste d'AORecord.
"""

import sys
from datetime import datetime, timedelta
from typing import Dict, List
from configparser import ConfigParser

import requests
from tqdm import tqdm

from services.scraper import BaseScraper
from services.database import AORecord
from services.config_utils import parse_list_value


class BoampScraper(BaseScraper):
    """Scraper pour BOAMP basé sur les mots-clés."""

    _API_URL = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        raw_keywords = config.get("BOAMP", "KEYWORDS", fallback="")
        self._keywords: List[str] = parse_list_value(raw_keywords)
        self._history_days: int = config.getint("Affichage", "Historique", fallback=10)
        # État réinitialisé à chaque appel scrape()
        self._search_response: dict = {}
        self._ad_cache: Dict[str, list] = {}

    def scrape(self) -> List[AORecord]:
        self._search_response = {}
        self._ad_cache = {}

        date_begin = datetime.now() - timedelta(days=self._history_days)
        date_begin_str = date_begin.strftime("%Y/%m/%d")

        print(f"\nRecherche d'appels d'offre depuis le {date_begin_str}...\n")

        for keyword in tqdm(
            self._keywords, desc="Progression", unit="mot-cle", colour="green", ncols=100
        ):
            self._search(date_begin_str, keyword)
            for ad in self._extract_valid_ads():
                self._collect_ad(ad, keyword)

        print("Termine !\n")
        return self._build_records()

    @staticmethod
    def source_name() -> str:
        return "BOAMP"

    # -----------------------------------------------------------------------
    # Méthodes privées
    # -----------------------------------------------------------------------

    def _search(self, date_parution: str, keyword: str) -> int:
        date_formatted = date_parution.replace("/", "-")
        where_clause = (
            f"dateparution >= '{date_formatted}' "
            f"AND (objet LIKE '%{keyword}%' OR nomacheteur LIKE '%{keyword}%')"
        )
        params = {"where": where_clause, "limit": 100}
        response = requests.get(self._API_URL, params=params, timeout=30).json()
        results = response.get("results", [])
        self._search_response = {
            "nbItemsRetournes": len(results),
            "total_count": response.get("total_count", 0),
            "item": [{"value": r.get("idweb"), "data": r} for r in results],
        }
        return self._search_size()

    def _search_size(self) -> int:
        return self._search_response.get("nbItemsRetournes", 0)

    def _extract_valid_ads(self) -> list:
        """Retourne les AOs dont la deadline est dans le futur."""
        valid = []
        for i in range(self._search_size()):
            annonce = self._search_response["item"][i].get("data", {})
            if not annonce:
                continue
            try:
                date_str = annonce.get("datelimitereponse")
                if date_str:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                    if dt > now:
                        valid.append(annonce)
            except Exception:
                pass
        return valid

    def _collect_ad(self, json_desc: dict, keyword: str) -> None:
        """
        Met l'AO en cache. Si déjà présent, fusionne les mots-clés sans doublon.
        Pas de persistance DB — c'est la responsabilité du caller.
        """
        idweb = str(json_desc.get("idweb", ""))
        if not idweb:
            return

        if idweb in self._ad_cache:
            existing = set(self._ad_cache[idweb][7].split(", "))
            if keyword not in existing:
                existing.add(keyword)
                self._ad_cache[idweb][7] = ", ".join(sorted(existing))
            return

        objet   = str(json_desc.get("objet", "N/C"))
        acheteur = str(json_desc.get("nomacheteur", "N/C"))

        date_limite = json_desc.get("datelimitereponse")
        if date_limite:
            try:
                dt = datetime.fromisoformat(date_limite.replace("Z", "+00:00"))
                deadline = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                deadline = "N/C"
        else:
            deadline = "N/C"

        date_pub = json_desc.get("dateparution")
        if date_pub:
            try:
                dt = datetime.fromisoformat(date_pub if "T" in date_pub else date_pub + "T00:00:00")
                date_parution = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date_parution = "N/C"
        else:
            date_parution = "N/C"

        # index: 0=acheteur, 1=objet, 2=montant, 3=resume, 4=deadline, 5=duree, 6=date_parution, 7=mot_cle
        self._ad_cache[idweb] = [acheteur, objet, "N/C", objet, deadline, "N/C", date_parution, keyword]

    def _build_records(self) -> List[AORecord]:
        records: List[AORecord] = []
        for idweb, data in self._ad_cache.items():
            resume = data[1] if data[1] != "None" and len(data[1]) >= 10 else data[3]
            records.append(AORecord(
                reference=idweb,
                acheteur=data[0],
                montant=data[2],
                duree=data[5],
                deadline=data[4],
                resume=resume,
                mot_cle=data[7],
                date_parution=data[6],
                data_source="boamp",
            ))
        return records
