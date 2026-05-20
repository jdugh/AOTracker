#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Scraper - Classe abstraite pour tous les scrappers d'appels d'offre.

Chaque implémentation reçoit la config complète dans __init__ et en extrait
ce dont elle a besoin. La méthode scrape() retourne une List[AORecord]
sans aucune persistance.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, List

from services.database import AORecord


@dataclass
class DceDownloadResult:
    """Résultat d'un téléchargement DCE pour une référence donnée."""
    downloaded: bool
    extracted_dir: str = ""
    error_message: str = ""


class BaseScraper(ABC):
    """Classe abstraite pour tous les scrappers d'appels d'offre."""

    def __init__(self, config: ConfigParser):
        """Reçoit la configuration complète. Chaque sous-classe extrait ce dont elle a besoin."""
        self.config = config

    @abstractmethod
    def scrape(self) -> List[AORecord]:
        """
        Scrape les appels d'offre depuis la source.

        Retourne une liste d'AORecord sans les persister en base.
        La persistance est gérée par le caller (orchestrateur).
        """

    @staticmethod
    @abstractmethod
    def source_name() -> str:
        """Nom lisible de la source (ex: 'PLACE', 'BOAMP')."""

    def download_dce_for_new_records(
        self,
        references: List[str],
        storage_root: Path,
    ) -> Dict[str, DceDownloadResult]:
        """
        Hook optionnel de téléchargement DCE.

        Implémentation par défaut : source non supportée (ex: BOAMP aujourd'hui).
        """
        _ = (references, storage_root)
        return {}
