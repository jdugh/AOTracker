
# AOTracker

Public procurement scraper for French BOAMP and PLACE sources with SQLite persistence.

## What is it?

AOTracker automates the search for public procurement calls (AO) in France from two sources:
- **BOAMP**: Official Bulletin of Public Procurement Announcements (OpenData API)
- **PLACE**: Public Procurement Dematerialization Platform (web scraping)

The script searches daily for new AOs matching your keywords (BOAMP) and CPV codes (PLACE), stores them in an SQLite database, and sends you a Pushbullet notification if new AOs are found.

## Installation

### Requirements
- Python 3.7+
- pip

### Steps

```bash
# 1. Clone or download the project
cd AOTracker

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure the project
cp config.local.cfg.example config.local.cfg
# Edit config.local.cfg with your BOAMP keywords and PLACE CPV codes
```

## Quickstart

### Configuration

Edit `config.local.cfg` (not versioned):

```ini
[BOAMP]
KEYWORDS =
    Python
    Docker
    Sqlite

[PLACE]
CPV_CODES =
    72000000
    30220000

[DCE]
STORAGE_PATH = dce_storage

[Affichage]
Historique = 10

[Deadline]
ROUGE = 10
JAUNE = 20
```

### Optional: Pushbullet Notifications

To receive notifications, create a `.env` file at the root:

```
API_KEY=your_pushbullet_key
PUSHBULLET_DEVICE_IDEN=your_optional_device_id
```

### Run the scraper

```bash
python run_daily.py
```

The script:
1. Scrapes BOAMP and PLACE
2. Inserts/updates AOs in the database (`tracker.db`)
3. Downloads DCE archives for newly inserted AOs (PLACE only) into `STORAGE_PATH/<scraper_source_name>/<reference>/`
4. Extracts ZIP archives (including nested ZIP files)
5. Sends a notification if new AOs are found

## Architecture

```
AOTracker/
├── services/
│   ├── scraper.py          # BaseScraper (ABC)
│   ├── database.py         # AORecord + TrackerDatabase + AOPersistence
│   ├── config_utils.py     # Config loading
│   ├── notifications.py    # Pushbullet
│   └── source_runner.py    # Standardized execution
├── boampgetter.py          # BoampScraper (keywords)
├── place.py                # PlaceScraper (CPV codes)
├── web_app.py              # Flask API (query the DB)
├── run_daily.py            # Orchestrator
└── tracker.db              # SQLite (generated)
```

### Flow

1. **run_daily.py** loads config and creates scrapers
2. **BoampScraper** + **PlaceScraper** inherit from **BaseScraper** and return `List[AORecord]`
3. **AOPersistence** merges keywords (set union) and persists to SQLite
4. **send_daily_summary_notification** sends a Pushbullet notification

## Web API (optional)

```bash
python web_app.py
# Access: http://localhost:5000
```

## License

MIT
