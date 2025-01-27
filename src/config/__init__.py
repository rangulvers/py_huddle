from dotenv import load_dotenv
from loguru import logger
import os

# Load environment variables from a .env file
load_dotenv()


# Default configuration values
HOME_GYM_ADDRESS = "Am Stadion 2, 64646 Heppenheim (Bergstraße)"

# Basketball-bund.net configuration
BASKETBALL_CONFIG = {
    "base_url": "https://www.basketball-bund.net",
    "verband": "6"  # Hessischer Basketball Verband
}

# Google Maps API configuration
GOOGLE_MAPS_CONFIG = {
    "api_key": os.getenv("GOOGLE_API_KEY")  # Replace with actual API key
}

logger.info(f"Google Maps API key: {GOOGLE_MAPS_CONFIG['api_key']}")

# Required columns for data validation
REQUIRED_COLUMNS = {
    "spielerliste": ["Vorname", "Nachname", "Geburtsdatum"],
    "spieldaten": ["Liga", "SpielplanID", "Gast", "Halle"]
}

# Error messages
ERROR_MESSAGES = {
    "network_error": "Netzwerkfehler: {error}",
    "unexpected_error": "Unerwarteter Fehler: {error}",
    "invalid_file": "Ungültige Datei: {error}",
    "missing_columns": "Fehlende Spalten: {columns}",
    "api_error": "API-Fehler: {error}"
}

PDF_CONFIG = {
    "template_path": "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf",
    "output_dir": "output/pdfs",
    "max_players": 5,
    "home_gym_address": "Am Stadion 2, 64646 Heppenheim (Bergstraße)"
}

# Application states
APP_STATES = {
    "INIT": "initial",
    "LIGA_DATA_LOADED": "liga_data_loaded",
    "FILES_UPLOADED": "files_uploaded",
    "GAMES_FETCHED": "games_fetched",
    "PDFS_GENERATED": "pdfs_generated"
}

# Field mappings for PDF
PDF_FIELD_MAPPINGS = {
    "club_name": "Verein",
    "event_type": "Art der Veranstaltung",
    "department": "Abteilung",
    "team": "Mannschaft",
    "date": "Datum",
    "location": "Name oder SpielortRow1",
    "distance": "Entfernung",
    "player1": "Spieler1",
    "player2": "Spieler2",
    "player3": "Spieler3",
    "player4": "Spieler4",
    "player5": "Spieler5"
}

# UI Text configurations
UI_TEXT = {
    "STEPS": {
        1: "Liga-Daten abrufen",
        2: "Daten hochladen",
        3: "Ligen auswählen & Spieldetails laden",
        4: "PDFs erzeugen"
    },
    "HEADERS": {
        "STEP_1": "1️⃣ Liga-Daten abrufen",
        "STEP_2": "2️⃣ Daten hochladen",
        "STEP_3": "3️⃣ Ligen auswählen & Spieldetails laden",
        "STEP_4": "4️⃣ PDFs erzeugen"
    },
    "BUTTONS": {
        "FETCH_LIGA": "Liga-Daten abrufen",
        "LOAD_FILES": "Dateien laden",
        "FETCH_DETAILS": "Spieldetails laden",
        "GENERATE_PDF": "PDFs erstellen"
    },
    "MESSAGES": {
        "SUCCESS": "✅ Erfolgreich",
        "ERROR": "❌ Fehler",
        "WARNING": "⚠️ Warnung",
        "INFO": "ℹ️ Info"
    }
}

# Validation settings
VALIDATION_CONFIG = {
    "max_retries": 3,
    "retry_delay": 1,  # seconds
    "timeout": 10,  # seconds
    "max_concurrent_requests": 5
}