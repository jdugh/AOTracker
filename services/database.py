#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database layer — point unique de gestion des I/O SQLite pour AOTracker.

Contient :
  - AORecord      : dataclass représentant un appel d'offre normalisé
  - TrackerDatabase : accès bas niveau à la base SQLite
  - AOPersistence : couche de persistance (insert/update avec fusion mots-clés)
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class AORecord:
    """Appel d'offre normalisé, indépendant de la source."""
    reference: str
    acheteur: str = "N/C"
    montant: str = "N/C"
    duree: str = "N/C"
    deadline: str = "N/C"
    resume: str = "N/C"
    mot_cle: str = "N/C"
    date_parution: str = "N/C"
    data_source: str = "boamp"


# ---------------------------------------------------------------------------
# TrackerDatabase — accès bas niveau
# ---------------------------------------------------------------------------

class TrackerDatabase:
    """Gestion bas niveau de la base SQLite appels_offre."""

    def __init__(self, db_path: str = "tracker.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Crée la table et applique les migrations si nécessaire."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appels_offre (
                reference TEXT PRIMARY KEY,
                acheteur TEXT,
                montant TEXT,
                duree TEXT,
                deadline TEXT,
                resume TEXT,
                mot_cle TEXT,
                date_parution TEXT,
                statut TEXT DEFAULT 'non_lu',
                date_ajout TEXT,
                date_modification TEXT,
                data_source TEXT DEFAULT 'boamp',
                dce_downloaded INTEGER,
                dce_local_path TEXT DEFAULT '',
                dce_last_error TEXT DEFAULT ''
            )
        ''')

        # Migrations
        cursor.execute("PRAGMA table_info(appels_offre)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'data_source' not in columns:
            cursor.execute('ALTER TABLE appels_offre ADD COLUMN data_source TEXT DEFAULT "boamp"')
            cursor.execute('UPDATE appels_offre SET data_source = "boamp" WHERE data_source IS NULL')
        if 'commentaire' not in columns:
            cursor.execute('ALTER TABLE appels_offre ADD COLUMN commentaire TEXT DEFAULT ""')
        if 'dce_downloaded' not in columns:
            cursor.execute('ALTER TABLE appels_offre ADD COLUMN dce_downloaded INTEGER')
        if 'dce_local_path' not in columns:
            cursor.execute('ALTER TABLE appels_offre ADD COLUMN dce_local_path TEXT DEFAULT ""')
        if 'dce_last_error' not in columns:
            cursor.execute('ALTER TABLE appels_offre ADD COLUMN dce_last_error TEXT DEFAULT ""')

        # Les AO PLACE sont candidats au téléchargement DCE. BOAMP reste à NULL.
        cursor.execute(
            'UPDATE appels_offre SET dce_downloaded = 0 '
            'WHERE data_source = "place" AND dce_downloaded IS NULL'
        )

        conn.commit()
        conn.close()

    def insert_or_update(
        self,
        reference: str,
        acheteur: str,
        montant: str,
        duree: str,
        deadline: str,
        resume: str,
        mot_cle: str,
        date_parution: str,
        data_source: str = 'boamp',
    ) -> str:
        """Insère ou met à jour un AO. Retourne 'insert' ou 'update'."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT reference FROM appels_offre WHERE reference = ?', (reference,))
        existing = cursor.fetchone()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if existing:
            cursor.execute('''
                UPDATE appels_offre
                SET acheteur=?, montant=?, duree=?, deadline=?, resume=?, mot_cle=?,
                    date_parution=?, date_modification=?, data_source=?,
                    dce_downloaded = CASE
                        WHEN ? = 'place' AND dce_downloaded IS NULL THEN 0
                        ELSE dce_downloaded
                    END
                WHERE reference=?
            ''', (acheteur, montant, duree, deadline, resume, mot_cle,
                  date_parution, now, data_source, data_source, reference))
            result = 'update'
        else:
            cursor.execute('''
                INSERT INTO appels_offre
                (reference, acheteur, montant, duree, deadline, resume, mot_cle,
                 date_parution, statut, date_ajout, date_modification, data_source, dce_downloaded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'non_lu', ?, ?, ?, ?)
            ''', (reference, acheteur, montant, duree, deadline, resume, mot_cle,
                  date_parution, now, now, data_source, 0 if data_source == 'place' else None))
            result = 'insert'

        conn.commit()
        conn.close()
        return result

    def update_dce_status(
        self,
        reference: str,
        downloaded: bool,
        local_path: str = "",
        error_message: str = "",
    ) -> None:
        """Met à jour l'état du téléchargement DCE pour un AO."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'UPDATE appels_offre '
            'SET dce_downloaded=?, dce_local_path=?, dce_last_error=?, date_modification=? '
            'WHERE reference=?',
            (1 if downloaded else 0, local_path, error_message, now, reference),
        )
        conn.commit()
        conn.close()

    def update_statut(self, reference: str, statut: str) -> None:
        """Met à jour le statut d'un AO."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'UPDATE appels_offre SET statut=?, date_modification=? WHERE reference=?',
            (statut, now, reference),
        )
        conn.commit()
        conn.close()

    def update_commentaire(self, reference: str, commentaire: str) -> None:
        """Met à jour le commentaire d'un AO."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'UPDATE appels_offre SET commentaire=?, date_modification=? WHERE reference=?',
            (commentaire, now, reference),
        )
        conn.commit()
        conn.close()

    def get_by_reference(self, reference: str) -> Optional[dict]:
        """Récupère un AO par sa référence."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM appels_offre WHERE reference = ?', (reference,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all(self, filtre_statut: Optional[str] = None) -> List[dict]:
        """Récupère tous les AO, optionnellement filtrés par statut."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if filtre_statut:
            cursor.execute(
                'SELECT * FROM appels_offre WHERE statut = ? ORDER BY deadline ASC',
                (filtre_statut,),
            )
        else:
            cursor.execute('SELECT * FROM appels_offre ORDER BY deadline ASC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Récupère les statistiques de la base."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        stats = {}
        cursor.execute('SELECT COUNT(*) FROM appels_offre')
        stats['total'] = cursor.fetchone()[0]
        for statut in ('a_suivre', 'ne_pas_suivre', 'deja_lu', 'non_lu'):
            cursor.execute('SELECT COUNT(*) FROM appels_offre WHERE statut = ?', (statut,))
            stats[statut] = cursor.fetchone()[0]
        conn.close()
        return stats


# ---------------------------------------------------------------------------
# AOPersistence — couche de persistance avec fusion mots-clés
# ---------------------------------------------------------------------------

class AOPersistence:
    """Gestionnaire de persistance pour les AORecord."""

    def __init__(self, db_path: str = "tracker.db"):
        self.db = TrackerDatabase(db_path=db_path)

    def persist_records(self, records: List[AORecord]) -> Tuple[List[str], List[str]]:
        """
        Insère ou met à jour une liste d'AORecord.
        Fusionne les mots-clés avec les valeurs existantes.
        Retourne (references_inserees, references_updatees).
        """
        inserted_refs: List[str] = []
        updated_refs: List[str] = []
        for record in records:
            result = self._upsert(record)
            if result == 'insert':
                inserted_refs.append(record.reference)
            elif result == 'update':
                updated_refs.append(record.reference)
        return inserted_refs, updated_refs

    def _upsert(self, record: AORecord) -> str:
        """Insert/update un AORecord avec fusion des mots-clés."""
        combined_keywords = record.mot_cle
        existing = self.db.get_by_reference(record.reference)
        if existing and existing.get('mot_cle'):
            old_kw = {k.strip() for k in existing['mot_cle'].split(', ') if k.strip()}
            new_kw = {k.strip() for k in record.mot_cle.split(', ') if k.strip()}
            combined_keywords = ', '.join(sorted(old_kw | new_kw))

        return self.db.insert_or_update(
            reference=record.reference,
            acheteur=record.acheteur,
            montant=record.montant,
            duree=record.duree,
            deadline=record.deadline,
            resume=record.resume,
            mot_cle=combined_keywords,
            date_parution=record.date_parution,
            data_source=record.data_source,
        )
