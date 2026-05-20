#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper "PLACE" (marches-publics.gouv.fr) — consultations en cours.

Toutes les données utiles sont extraites directement depuis la page de liste.
Le site utilise le framework PRADO (PHP) : pagination via POST.
"""

from __future__ import annotations

import re
import sys
import time
import calendar
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from configparser import ConfigParser

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from services.scraper import BaseScraper
from services.database import AORecord
from services.config_utils import parse_list_value


# ---------------------------------------------------------------------------
# Dataclass résultat (module-level — helper interne)
# ---------------------------------------------------------------------------

@dataclass
class Consultation:
    consultation_id: str
    detail_url: str
    reference: Optional[str] = None
    intitule: Optional[str] = None
    organisme: Optional[str] = None
    procedure: Optional[str] = None
    categorie: Optional[str] = None
    lieu_execution: Optional[str] = None
    deadline: Optional[str] = None


# ---------------------------------------------------------------------------
# PlaceScraper
# ---------------------------------------------------------------------------

class PlaceScraper(BaseScraper):
    """Scraper pour PLACE (marches-publics.gouv.fr) basé sur les codes CPV."""

    # --- Constantes de classe ---
    _BASE = "https://www.marches-publics.gouv.fr"
    _SEARCH_URL = _BASE + "/?page=Entreprise.EntrepriseAdvancedSearch&searchAnnCons"
    _PRADO_NEXT_PAGE_TARGET = "ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2"
    _PRADO_NEXT_PAGE_ID     = "ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2"

    _MONTHS_FR: Dict[str, str] = {
        "jan": "01", "fév": "02", "fev": "02",
        "mar": "03", "avr": "04",
        "mai": "05",
        "juin": "06",
        "juil": "07", "jui": "07",
        "aoû": "08", "aou": "08",
        "sep": "09", "sept": "09",
        "oct": "10", "nov": "11",
        "déc": "12", "dec": "12",
        "janvier": "01", "février": "02", "fevrier": "02",
        "mars": "03", "avril": "04",
        "juillet": "07", "août": "08", "aout": "08",
        "septembre": "09", "octobre": "10",
        "novembre": "11", "décembre": "12", "decembre": "12",
    }

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        raw_codes = config.get("PLACE", "CPV_CODES", fallback="")
        self._cpv_codes: List[str] = parse_list_value(raw_codes)
        self._max_pages: int = config.getint("PLACE", "MAX_PAGES", fallback=200)
        self._sleep: float = config.getfloat("PLACE", "SLEEP", fallback=0.3)

    def scrape(self) -> List[AORecord]:
        session = self._make_session()
        dates = self._compute_search_dates()
        cpv_str = ", ".join(self._cpv_codes)
        print(f"\nScraping PLACE | CPV {cpv_str} | max {self._max_pages or 'illimité'} pages")
        print(f"Dates : {dates['dateMiseEnLigneStart']} -> {dates['dateMiseEnLigneEnd']}\n")

        seen, cpv_map = self._scrape_all_cpv(session)
        print(f"\n{len(seen)} consultations uniques trouvées")

        records: List[AORecord] = []
        for cid, consultation in seen.items():
            codes = cpv_map.get(cid, [])
            mot_cle = ", ".join(f"CPV {code}" for code in codes)
            records.append(AORecord(
                reference=cid,
                acheteur=consultation.organisme or "N/C",
                montant="N/C",
                duree="N/C",
                deadline=consultation.deadline or "N/C",
                resume=consultation.intitule or "N/C",
                mot_cle=mot_cle or "N/C",
                date_parution="N/C",
                data_source="place",
            ))
        return records

    @staticmethod
    def source_name() -> str:
        return "PLACE"

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; place-export/1.0; +https://www.marches-publics.gouv.fr/)",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        return s

    def _fetch_html(self, session: requests.Session, url: str, timeout: int = 30) -> str:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text

    # -----------------------------------------------------------------------
    # Dates helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1
        max_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(d.day, max_day))

    @staticmethod
    def _compute_search_dates() -> Dict[str, str]:
        today = date.today()
        six_months_later = PlaceScraper._add_months(today, 6)
        six_months_ago   = PlaceScraper._add_months(today, -6)
        fmt = "%d/%m/%Y"
        return {
            "dateMiseEnLigneStart":        today.strftime(fmt),
            "dateMiseEnLigneEnd":          six_months_later.strftime(fmt),
            "dateMiseEnLigneCalculeStart": six_months_ago.strftime(fmt),
            "dateMiseEnLigneCalculeEnd":   today.strftime(fmt),
        }

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_detail_url(consultation_id: str, org_acronyme: str) -> str:
        return (
            f"{PlaceScraper._BASE}/app.php/entreprise/consultation"
            f"/{consultation_id}?orgAcronyme={org_acronyme}"
        )

    # -----------------------------------------------------------------------
    # Recherche avancée (POST)
    # -----------------------------------------------------------------------

    def _build_search_payload(self, prado_fields: Dict[str, str], cpv_code: str) -> Dict[str, str]:
        dates = self._compute_search_dates()
        payload = {
            **prado_fields,
            "ctl0$CONTENU_PAGE$AdvancedSearch$keywordSearch": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$orgNameAM": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$organismesNames": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$choixInclusionDescendancesServices": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$inclureDescendances": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$type_rechercheEntite": "floue",
            "ctl0$CONTENU_PAGE$AdvancedSearch$reference": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$procedureType": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$categorie": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$inclureConsultationExterieur": "on",
            "ctl0$CONTENU_PAGE$AdvancedSearch$clauseSociales": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$ateliersProteges": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$siae": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$ess": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$clauseSocialesCommerceEquitable": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$clauseSocialesInsertionActiviteEconomique": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$clauseEnvironnementale": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$idsSelectedGeoN2": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$numSelectedGeoN2": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$referentielCPV$cpvPrincipale": cpv_code,
            "ctl0$CONTENU_PAGE$AdvancedSearch$referentielCPV$cpvSecondaires": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$referentielCPV$rechercheFloue": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$referentielCPV$cpvSimple": "view",
            "ctl0$CONTENU_PAGE$AdvancedSearch$dateMiseEnLigneStart": dates["dateMiseEnLigneStart"],
            "ctl0$CONTENU_PAGE$AdvancedSearch$dateMiseEnLigneEnd": dates["dateMiseEnLigneEnd"],
            "ctl0$CONTENU_PAGE$AdvancedSearch$dateMiseEnLigneCalculeStart": dates["dateMiseEnLigneCalculeStart"],
            "ctl0$CONTENU_PAGE$AdvancedSearch$dateMiseEnLigneCalculeEnd": dates["dateMiseEnLigneCalculeEnd"],
            "ctl0$CONTENU_PAGE$AdvancedSearch$keywordSearchBottom": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$rechercheFloue": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$floueBottom": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$lancerRecherche": "Lancer la recherche",
            "ctl0$CONTENU_PAGE$AdvancedSearch$orgNamesRestreinteSearch": "0",
            "ctl0$CONTENU_PAGE$AdvancedSearch$refRestreinteSearch": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$accesRestreinteSearch": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$rechercheName": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$RadioGroup": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$tousLesJours": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$formatAlerte": "",
            "ctl0$CONTENU_PAGE$AdvancedSearch$formatHtml": "",
            "ctl0$atexoUtah$javaVersion": "",
            "PRADO_POSTBACK_TARGET": "ctl0$CONTENU_PAGE$AdvancedSearch$lancerRecherche",
        }
        return payload

    def _perform_search(self, session: requests.Session, cpv_code: str) -> Tuple[str, str]:
        search_page_url = self._BASE + "/?page=Entreprise.EntrepriseAdvancedSearch"
        html = self._fetch_html(session, search_page_url)
        action, prado_fields = self._get_prado_form_state(html)
        payload = self._build_search_payload(prado_fields, cpv_code)
        post_url = urljoin(search_page_url, action) if action else self._SEARCH_URL
        r = session.post(post_url, data=payload, timeout=30)
        r.raise_for_status()
        return r.text, post_url

    # -----------------------------------------------------------------------
    # Pagination PRADO
    # -----------------------------------------------------------------------

    def _get_prado_form_state(self, html: str) -> Tuple[str, Dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        form = soup.find("form", id="ctl0_ctl1")
        if not form:
            return ("", {})
        action = str(form.get("action") or "")
        fields: Dict[str, str] = {}
        exclude_types = {"submit", "button", "image", "reset"}
        for inp in form.find_all("input"):
            itype = (inp.get("type") or "text").lower()
            if itype in exclude_types:
                continue
            name = inp.get("name")
            if name:
                fields[name] = inp.get("value", "")
        return (action, fields)

    def _has_next_page(self, html: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return soup.find("a", id=self._PRADO_NEXT_PAGE_ID) is not None

    def _post_next_page(
        self,
        session: requests.Session,
        html: str,
        current_url: str,
    ) -> Tuple[str, str]:
        action, fields = self._get_prado_form_state(html)
        fields["PRADO_POSTBACK_TARGET"] = self._PRADO_NEXT_PAGE_TARGET
        post_url = urljoin(current_url, action) if action else current_url
        time.sleep(self._sleep)
        r = session.post(post_url, data=fields, timeout=30)
        r.raise_for_status()
        return r.text, post_url

    # -----------------------------------------------------------------------
    # Extraction depuis la page de liste
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_place_date(day: str, month: str, year: str, time_str: str = "00:00") -> str:
        mon_num = PlaceScraper._MONTHS_FR.get(month.lower().rstrip("."), "00")
        return f"{year}-{mon_num}-{day.zfill(2)} {time_str}:00"

    def _extract_consultations_from_list(self, html: str) -> List[Consultation]:
        soup = BeautifulSoup(html, "lxml")
        results: List[Consultation] = []

        for row in soup.find_all("div", class_="item_consultation"):
            ref_inp = row.find("input", {"name": re.compile(r"\$refCons$")})
            if not ref_inp:
                continue
            cid = ref_inp.get("value", "").strip()
            if not cid:
                continue
            org_inp = row.find("input", {"name": re.compile(r"\$orgCons$")})
            org_val = org_inp.get("value", "").strip() if org_inp else ""

            c = Consultation(
                consultation_id=cid,
                detail_url=self._build_detail_url(cid, org_val),
            )

            bloc = row.find("div", class_="objet-line")
            if bloc:
                smalls = bloc.find_all("div", class_="small")
                if smalls:
                    c.reference = smalls[0].get_text(strip=True)
                truncate = bloc.find("div", class_="truncate")
                if truncate:
                    full_title = truncate.get("title")
                    if not full_title:
                        span = truncate.find("span")
                        if span:
                            full_title = span.get("title") or span.get_text(strip=True)
                    if not full_title:
                        full_title = truncate.get_text(strip=True)
                    c.intitule = full_title.strip() if full_title else None

            denom = row.find("div", id=re.compile(r"panelBlocDenomination"))
            if denom:
                small = denom.find("span", class_="small")
                if small:
                    c.organisme = small.get_text(strip=True)

            cat_div = row.find("div", class_="cons_categorie")
            if cat_div:
                c.categorie = cat_div.get_text(strip=True)

            proc_div = row.find("div", class_="cons_procedure")
            if proc_div:
                abbr = proc_div.find("abbr")
                c.procedure = (
                    (abbr.get("title") or abbr.get_text(strip=True)).strip()
                    if abbr else proc_div.get_text(strip=True)
                )

            lieu_div = row.find("div", id=re.compile(r"panelBlocLieuxExec"))
            if lieu_div:
                c.lieu_execution = lieu_div.get_text(strip=True)

            date_end = row.find("div", class_="cons_dateEnd")
            if date_end:
                cloture = date_end.find("div", class_="cloture-line")
                if cloture:
                    day_el   = cloture.find("div", class_="day")
                    month_el = cloture.find("div", class_="month")
                    year_el  = cloture.find("div", class_="year")
                    time_el  = cloture.find("label")
                    day_v   = day_el.find("span").get_text(strip=True)   if day_el   else "01"
                    month_v = month_el.find("span").get_text(strip=True) if month_el else "Jan."
                    year_v  = year_el.find("span").get_text(strip=True)  if year_el  else "2000"
                    tstr    = time_el.get_text(strip=True)               if time_el  else "00:00"
                    c.deadline = self._parse_place_date(day_v, month_v, year_v, tstr)

            results.append(c)

        return results

    # -----------------------------------------------------------------------
    # Scraping par CPV
    # -----------------------------------------------------------------------

    def _scrape_cpv(self, session: requests.Session, cpv_code: str) -> Dict[str, Consultation]:
        seen: Dict[str, Consultation] = {}
        try:
            html, url = self._perform_search(session, cpv_code)
        except Exception as e:
            print(f"Impossible d'acceder a PLACE : {e}", file=sys.stderr)
            return seen
        time.sleep(self._sleep)

        limit = float("inf") if self._max_pages == 0 else self._max_pages

        for page_num in range(1, int(limit) + 1 if limit != float("inf") else 10 ** 9):
            consultations = self._extract_consultations_from_list(html)
            if not consultations:
                break
            for c in consultations:
                if c.consultation_id not in seen:
                    seen[c.consultation_id] = c
            if not self._has_next_page(html):
                break
            if page_num >= limit:
                break
            try:
                html, url = self._post_next_page(session, html, url)
            except Exception as e:
                print(f"Pagination impossible page {page_num + 1}: {e}", file=sys.stderr)
                break

        return seen

    def _scrape_all_cpv(
        self, session: requests.Session
    ) -> Tuple[Dict[str, Consultation], Dict[str, List[str]]]:
        all_seen: Dict[str, Consultation] = {}
        cpv_map: Dict[str, List[str]] = {}

        for cpv_code in tqdm(
            self._cpv_codes, desc="Progression", unit="CPV", colour="green", ncols=100
        ):
            seen = self._scrape_cpv(session, cpv_code)
            for cid, c in seen.items():
                if cid not in all_seen:
                    all_seen[cid] = c
                    cpv_map[cid] = [cpv_code]
                else:
                    cpv_map[cid].append(cpv_code)

        return all_seen, cpv_map
