# Compatibility shim — web_app.py imports TrackerDatabase from here.
# La logique est dans services/database.py.
from services.database import AORecord, AOPersistence, TrackerDatabase

__all__ = ["AORecord", "AOPersistence", "TrackerDatabase"]

