# At the top of your file, after imports:
import os
import re
import time
import math
import uuid
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from dotenv import load_dotenv
from loguru import logger
from pdfrw import PdfReader, PdfWriter, PdfDict

# Load environment variables
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────
# Constants and Configuration
# ─────────────────────────────────────────────────────────────────────────
REQUIRED_COLUMNS = {
    "spielerliste": {"Vorname", "Nachname", "Geburtsdatum"},
    "spieldaten": {"Liga", "SpielplanID", "Gast", "Halle"}
}

DEFAULT_RETRY_COUNT = 3
RETRY_DELAY = 1  # seconds

# Initialize session state for home gym address
if "home_gym_address" not in st.session_state:
    st.session_state.home_gym_address = os.environ.get("HOME_GYM_ADDRESS", "Heimatadresse nicht gesetzt")


class AppError(Exception):
    """Custom error class for application-specific exceptions."""
    pass

# ─────────────────────────────────────────────────────────────────────────
# State Management
# ─────────────────────────────────────────────────────────────────────────
def init_session_state():
    """Initialize or reset the session state variables."""
    defaults = {
        "step_1_done": False,
        "step_2_done": False,
        "step_3_done": False,
        "step_4_done": False,
        "liga_df": pd.DataFrame(),
        "uploaded_df": pd.DataFrame(),
        "match_details": pd.DataFrame(),
        "player_birthdays_df": pd.DataFrame(),
        "generated_files": [],
        "processing_start_time": None,
        "last_error": None,
        "generated_pdfs_info": []  # Add this line to store PDF generation info
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def reset_session_state():
    """Reset all session state variables to their defaults."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()

# ─────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────
def format_time_remaining(seconds: float) -> str:
    """Format remaining time in a human-readable way."""
    if seconds < 60:
        return f"{seconds:.0f} Sekunden"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f} Minuten"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} Stunden"

def estimate_time_remaining(start_time: float, current_idx: int, total_items: int) -> str:
    """Calculate and format estimated remaining time."""
    if current_idx == 0:
        return "Berechne..."
    
    elapsed = time.time() - start_time
    items_per_second = current_idx / elapsed
    remaining_items = total_items - current_idx
    remaining_seconds = remaining_items / items_per_second
    
    return format_time_remaining(remaining_seconds)

def validate_dataframe(df: pd.DataFrame, required_columns: set, context: str) -> bool:
    """Validate that a DataFrame has all required columns."""
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        st.error(
            f"Fehlerhafte {context}: Folgende Spalten fehlen: "
            f"{', '.join(missing_columns)}"
        )
        return False
    return True

def retry_with_backoff(func, *args, max_retries=DEFAULT_RETRY_COUNT, **kwargs):
    """Execute a function with exponential backoff retry logic."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = (2 ** attempt) * RETRY_DELAY
            logger.warning(f"Versuch {attempt + 1} fehlgeschlagen. Warte {wait_time}s...")
            time.sleep(wait_time)

def format_liga_display(name: str, alter: str, gender: str, liga_id: str) -> str:
    """Format liga information for display in the UI."""
    return (
        f"{name} | {alter} ({gender}) "
        f"<span style='color: gray; font-size: smaller;'>[ID: {liga_id}]</span>"
    )
# ─────────────────────────────────────────────────────────────────────────
# Google API Functions
# ─────────────────────────────────────────────────────────────────────────
def google_geocode_address(query: str) -> Optional[dict]:
    """
    Geocode an address using Google's Geocoding API.
    
    Args:
        query: The address string to geocode
        
    Returns:
        Optional[dict]: Location data including lat, lng, and formatted address,
                       or None if geocoding fails
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        st.error("Google API Key nicht gefunden. Bitte überprüfen Sie ihre Umgebungsvariablen.")
        return None

    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query,
        "key": google_api_key
    }

    try:
        response = retry_with_backoff(
            requests.get,
            endpoint,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(f"Geocoding fehlgeschlagen für '{query}' => {data.get('status')}")
            return None

        first_result = data["results"][0]
        location = first_result["geometry"]["location"]
        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "formatted_address": first_result["formatted_address"]
        }

    except Exception as exc:
        logger.error(f"Fehler bei Google Geocoding für '{query}': {exc}")
        st.error(f"Fehler bei der Adresssuche: {str(exc)}")
        return None

def google_distance_matrix(origins: str, destinations: str) -> float:
    """
    Calculate driving distance between two locations using Google's Distance Matrix API.
    
    Args:
        origins: Starting address
        destinations: Destination address
        
    Returns:
        float: Distance in kilometers, or 0.0 if calculation fails
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        st.error("Google API Key nicht gefunden. Bitte überprüfen Sie ihre Umgebungsvariablen.")
        return 0.0

    endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origins,
        "destinations": destinations,
        "key": google_api_key,
        "mode": "driving",
        "language": "de"
    }

    try:
        response = retry_with_backoff(
            requests.get,
            endpoint,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            logger.warning(f"DistanceMatrix-Fehler => {data.get('status')}")
            return 0.0

        elements = data.get("rows", [{}])[0].get("elements", [{}])[0]
        if elements.get("status") != "OK":
            logger.warning(f"Routenberechnung fehlgeschlagen: {elements.get('status')}")
            return 0.0

        distance_meters = elements["distance"]["value"]
        return distance_meters / 1000.0

    except Exception as exc:
        logger.error(f"Fehler bei Google DistanceMatrix: {exc}")
        st.error(f"Fehler bei der Entfernungsberechnung: {str(exc)}")
        return 0.0

def fetch_away_gym_info(opponent_team: str, hall_name: str) -> Tuple[str, float]:
    """
    Get location information and driving distance for an away game.
    
    Args:
        opponent_team: Name of the opponent team
        hall_name: Name of the gymnasium/venue
        
    Returns:
        Tuple[str, float]: (resolved_address, distance_in_km)
    """
    # First try with both team and hall
    query_str = f"{opponent_team} {hall_name} Germany"
    away_geo = google_geocode_address(query_str)
    
    # If that fails, try just the hall name
    if not away_geo:
        query_str = f"{hall_name} Germany"
        away_geo = google_geocode_address(query_str)
        if not away_geo:
            return hall_name, 0.0

    resolved_address = away_geo["formatted_address"]

    # Get home gym location
    home_geo = google_geocode_address(st.session_state.get("home_gym_address", ""))
    if not home_geo:
        logger.warning("Konnte Heimadresse nicht geocoden. 0.0 Distanz.")
        return resolved_address, 0.0

    # Calculate distance
    distance_km = google_distance_matrix(
        home_geo["formatted_address"],
        resolved_address
    )

    return resolved_address, distance_km

# ─────────────────────────────────────────────────────────────────────────
# Data Processing Functions
# ─────────────────────────────────────────────────────────────────────────
def parse_date_only(raw_date) -> str:
    """Convert various date formats to DD.MM.YYYY."""
    if pd.isna(raw_date):
        return "Unknown"

    if isinstance(raw_date, (pd.Timestamp, datetime)):
        return raw_date.strftime("%d.%m.%Y")

    if isinstance(raw_date, str):
        try:
            dt = datetime.strptime(raw_date.strip(), "%d.%m.%Y %H:%M:%S")
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            try:
                # Try parsing just the date part
                parts = raw_date.strip().split()[0]
                dt = datetime.strptime(parts, "%d.%m.%Y")
                return dt.strftime("%d.%m.%Y")
            except (ValueError, IndexError):
                return "Unknown"

    return "Unknown"

def normalize_liga_name(liga_name: str) -> str:
    """Clean up league names by removing parenthetical information."""
    if pd.isna(liga_name):
        return ""
    return re.sub(r"\s*\(.*?\)", "", str(liga_name)).strip()

def build_birthday_lookup(df: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    """
    Create a lookup dictionary for player birthdays.
    
    Args:
        df: DataFrame containing player information
        
    Returns:
        Dict mapping (lastname, firstname) to birthday string
    """
    if df.empty:
        return {}

    lookup = {}
    for _, row in df.iterrows():
        lastname = str(row.get("Nachname", "")).strip()
        firstname = str(row.get("Vorname", "")).strip()
        if lastname and firstname:  # Only add if we have both names
            raw_date = row.get("Geburtsdatum", "Unknown")
            lookup[(lastname, firstname)] = raw_date
    
    return lookup
# ─────────────────────────────────────────────────────────────────────────
# Basketball-Bund.net Data Fetching
# ─────────────────────────────────────────────────────────────────────────
def fetch_liga_data(club_name: str) -> pd.DataFrame:
    """
    Fetch league data for a given club from basketball-bund.net.
    
    Args:
        club_name: Name of the basketball club
        
    Returns:
        DataFrame containing league information
    """
    logger.debug("Rufe Ligadaten ab für {}", club_name)
    url = "https://www.basketball-bund.net/index.jsp?Action=100&Verband=6"
    
    payload = (
        f"search={club_name.replace(' ', '+')}"
        "&cbSpielklasseFilter=0&spieltyp_id=0&cbAltersklasseFilter=0"
        "&cbGeschlechtFilter=0&cbBezirkFilter=0&cbKreisFilter=0"
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = retry_with_backoff(
            requests.post,
            url,
            headers=headers,
            data=payload,
            timeout=10
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find the liga table
        form = soup.find("form", {"name": "ligaliste"})
        if not form:
            logger.warning("Kein Formular 'ligaliste' gefunden")
            st.error("Keine Liga-Informationen gefunden. Bitte überprüfen Sie den Vereinsnamen.")
            return pd.DataFrame()

        # Find the correct table with liga information
        target_table = None
        tables = soup.find_all("table", class_="sportView")
        for table in tables:
            headers = table.find_all("td", class_="sportViewHeader")
            if headers:
                header_texts = [h.get_text(strip=True) for h in headers]
                if {"Klasse", "Alter", "Liganame"}.issubset(header_texts):
                    target_table = table
                    break

        if not target_table:
            st.error("Keine Liga-Tabelle gefunden.")
            return pd.DataFrame()

        # Extract data from table
        data_list = []
        rows = target_table.find_all("tr")
        
        # Show progress while processing
        progress_text = st.empty()
        progress_bar = st.progress(0)
        total_rows = len(rows[1:])  # Skip header row
        
        for idx, row in enumerate(rows[1:], 1):
            progress_bar.progress(idx / total_rows)
            progress_text.text(f"Verarbeite Liga {idx}/{total_rows}...")
            
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            # Extract cell data
            klasse = cells[0].get_text(strip=True)
            alter = cells[1].get_text(strip=True)
            gender = cells[2].get_text(strip=True)
            bezirk = cells[3].get_text(strip=True)
            kreis = cells[4].get_text(strip=True)
            liga_name = cells[5].get_text(strip=True)
            liga_nr = cells[6].get_text(strip=True)

            # Extract Liga ID from link
            liga_id = None
            for link in cells[7].find_all("a", href=True):
                if "Action=102" in link["href"]:
                    liga_id = link["href"].split("liga_id=")[-1]
                    break

            data_list.append({
                "Klasse": klasse,
                "Alter": alter,
                "m/w": gender,
                "Bezirk": bezirk,
                "Kreis": kreis,
                "Liganame": normalize_liga_name(liga_name),
                "Liganr": liga_nr,
                "Liga_ID": liga_id
            })

        progress_bar.empty()
        progress_text.empty()

        return pd.DataFrame(data_list)

    except requests.exceptions.RequestException as e:
        logger.error(f"Netzwerkfehler beim Abrufen der Ligadaten: {e}")
        st.error("Fehler beim Verbinden mit basketball-bund.net. Bitte versuchen Sie es später erneut.")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Abrufen der Ligadaten: {e}")
        st.error("Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut.")
        return pd.DataFrame()

def fetch_game_details(spielplan_id: str, liga_id: str) -> Optional[dict]:
    """
    Fetch details for a specific game.
    
    Args:
        spielplan_id: ID of the game schedule
        liga_id: ID of the league
        
    Returns:
        Dictionary containing game details or None if fetch fails
    """
    logger.debug("Rufe Spieldetails ab: {}, {}", spielplan_id, liga_id)
    
    url = (
        "https://www.basketball-bund.net/public/ergebnisDetails.jsp?"
        f"type=1&spielplan_id={spielplan_id}&liga_id={liga_id}&defaultview=1"
    )

    try:
        response = retry_with_backoff(
            requests.get,
            url,
            timeout=10
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract game details
        game_details = {}
        ergebnisliste_form = soup.find("form", {"name": "ergebnisliste"})
        if ergebnisliste_form:
            rows = ergebnisliste_form.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 6:
                    try:
                        game_details = {
                            "Date": cells[2].get_text(strip=True).strip(),
                            "Home Team": cells[3].get_text(strip=True).strip(),
                            "Away Team": cells[4].get_text(strip=True).strip(),
                            "Home Score": cells[5].get_text(strip=True).split(" : ")[0].strip(),
                            "Away Score": cells[5].get_text(strip=True).split(" : ")[1].strip()
                        }
                    except IndexError:
                        continue
                    break

        # Extract player statistics
        player_list = []
        player_stats_form = soup.find("form", {"name": "spielerstatistikgast"})
        if player_stats_form:
            rows = player_stats_form.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    lastname = cells[0].get_text(strip=True)
                    firstname = cells[1].get_text(strip=True)
                    if lastname and firstname and lastname != "Nachname" and firstname != "Vorname":
                        player_list.append({
                            "Nachname": lastname,
                            "Vorname": firstname
                        })

        # Combine all information
        return {
            "Spielplan_ID": spielplan_id,
            "Liga_ID": liga_id,
            "Date": game_details.get("Date", "Unknown"),
            "Home Team": game_details.get("Home Team", "Unknown"),
            "Away Team": game_details.get("Away Team", "Unknown"),
            "Home Score": game_details.get("Home Score", "?"),
            "Away Score": game_details.get("Away Score", "?"),
            "Players": player_list
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Netzwerkfehler beim Abrufen der Spieldetails: {e}")
        return None
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Abrufen der Spieldetails: {e}")
        return None

def fetch_selected_games(df: pd.DataFrame, selected_ligas: list, club_name: str) -> pd.DataFrame:
    """
    Fetch details for selected games.
    
    Args:
        df: DataFrame containing game information
        selected_ligas: List of selected league IDs
        club_name: Name of the club
        
    Returns:
        DataFrame containing detailed game information
    """
    logger.debug("fetch_selected_games Verein: {}", club_name)

    with st.spinner("Lade Spieldetails..."):
        # Filter relevant games
        subset_df = df[
            df["Liga_ID"].isin(selected_ligas) & 
            df["Gast"].fillna("").str.contains(club_name, na=False)
        ].copy()

        if "Liga_ID" not in df.columns or "SpielplanID" not in df.columns:
            st.error("Fehlende Spalten 'Liga_ID' oder 'SpielplanID' in den Spieldaten.")
            return pd.DataFrame()

        total_relevant = len(subset_df)
        if total_relevant == 0:
            st.info("Keine passenden Spiele gefunden.")
            return pd.DataFrame()

        # Setup progress tracking
        progress_bar = st.progress(0.0)
        status_placeholder = st.empty()
        game_data = []
        processed_count = 0
        start_time = time.time()

        # Process each game
        for idx, row in subset_df.iterrows():
            liga_id = row.get("Liga_ID", "Unknown")
            spielplan_id = row.get("SpielplanID", "Unknown")

            # Update status with time estimation
            elapsed = time.time() - start_time
            if processed_count > 0:
                estimated_total = (elapsed / processed_count) * total_relevant
                remaining = estimated_total - elapsed
                time_str = format_time_remaining(remaining)
            else:
                time_str = "wird berechnet..."

            status_placeholder.info(
                f"""
                **Lade Spieldetails ({processed_count + 1}/{total_relevant})**
                - Spielplan: {spielplan_id}
                - Liga: {liga_id}
                - Geschätzte Restzeit: {time_str}
                """
            )

            details = fetch_game_details(spielplan_id, liga_id)
            if details:
                game_data.append(details)

            processed_count += 1
            progress_bar.progress(processed_count / total_relevant)
            time.sleep(0.25)  # Prevent server overload

        # Cleanup progress indicators
        status_placeholder.empty()
        progress_bar.empty()

        return pd.DataFrame(game_data)
    
# ─────────────────────────────────────────────────────────────────────────
# PDF Generation
# ─────────────────────────────────────────────────────────────────────────
def generate_pdf(
    game_details: dict,
    pdf_club_name: str,
    art_der_veranstaltung: str,
    template_path: str,
    hall: str,
    birthday_lookup: dict,
    liganame: str,
    distance_km: float,
    alter: str = "Unknown"
) -> str:
    """
    Generate a PDF file for travel expenses.
    
    Args:
        game_details: Dictionary containing game information
        pdf_club_name: Club name for the PDF
        art_der_veranstaltung: Type of event
        template_path: Path to the PDF template
        hall: Gym/venue information
        birthday_lookup: Dictionary mapping player names to birthdays
        liganame: League name
        distance_km: Distance in kilometers
        alter: Age group
        
    Returns:
        str: Path to the generated PDF file
    """
    logger.debug("PDF generieren für: {}", game_details)

    # Double the distance and round up for round trip
    distance_km = math.ceil(distance_km * 2)

    # Sort players by birthday availability
    all_players = game_details.get("Players", [])
    players_with_bday = []
    players_no_bday = []

    for player in all_players:
        ln, fn = player["Nachname"], player["Vorname"]
        raw_bdate = birthday_lookup.get((ln, fn), "Unknown")
        if raw_bdate != "Unknown":
            players_with_bday.append(player)
        else:
            players_no_bday.append(player)

    # Select final players (prioritize those with birthdays)
    final_players = players_with_bday[:5]
    if len(final_players) < 5:
        needed = 5 - len(final_players)
        final_players.extend(players_no_bday[:needed])

    # Mask sensitive data
    for idx, player_info in enumerate(final_players):
        if "*" in player_info["Nachname"]:
            final_players[idx] = {"Nachname": "Geblocked durch DSGVO", "Vorname": ""}

    # Generate filename
    liga_id = game_details.get("Liga_ID", "NoLigaID") or "NoLigaID"
    date_str = game_details["Date"].replace(":", "-").replace("/", "-").replace("\\", "-")
    filename = f"{liga_id}_{alter}_{date_str}.pdf"

    # Ensure output directory exists
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", filename)

    try:
        # Read template and process fields
        template_pdf = PdfReader(template_path)
        for page in template_pdf.pages:
            annotations = page.get("/Annots") or []
            for annotation in annotations:
                if "/T" not in annotation:
                    continue

                field_name = annotation["/T"][1:-1]
                
                # Process each field type
                if field_name == "Verein":
                    annotation.update(PdfDict(V=pdf_club_name))
                elif field_name == "Abteilung":
                    annotation.update(PdfDict(V="Basketball"))
                elif field_name == "Art der Veranstaltung":
                    annotation.update(PdfDict(V=art_der_veranstaltung))
                elif field_name == "Mannschaften":
                    annotation.update(PdfDict(V=liganame))
                elif field_name == "DatumRow1":
                    annotation.update(PdfDict(V=game_details["Date"]))
                elif field_name == "Name oder SpielortRow1":
                    annotation.update(PdfDict(V=hall))
                elif field_name.startswith("Name oder SpielortRow"):
                    match = re.search(r"Name oder SpielortRow(\d+)$", field_name)
                    if match:
                        row_number = int(match.group(1))
                        offset = 2
                        index = row_number - offset
                        if 0 <= index < len(final_players):
                            p_data = final_players[index]
                            annotation.update(PdfDict(V=f"{p_data['Nachname']}, {p_data['Vorname']}"))
                        else:
                            annotation.update(PdfDict(V=""))
                elif field_name.startswith("EinzelteilngebRow"):
                    match = re.search(r"EinzelteilngebRow(\d+)$", field_name)
                    if match:
                        row_number = int(match.group(1))
                        offset = 2
                        index = row_number - offset
                        if 0 <= index < len(final_players):
                            pl_data = final_players[index]
                            ln, fn = pl_data["Nachname"], pl_data["Vorname"]
                            raw_bday = birthday_lookup.get((ln, fn), "Unknown")
                            final_bday = parse_date_only(raw_bday) if raw_bday != "Unknown" else "Unknown"
                            annotation.update(PdfDict(V=final_bday))
                        else:
                            annotation.update(PdfDict(V=""))
                elif field_name.startswith("km"):
                    match = re.search(r"km  Hin und Rückfahrt Row(\d+)$", field_name)
                    if match:
                        row_number = int(match.group(1))
                        offset = 2
                        index = row_number - offset
                        if 0 <= index < len(final_players):
                            annotation.update(PdfDict(V=f"{distance_km:.1f}"))
                        else:
                            annotation.update(PdfDict(V=""))
                else:
                    annotation.update(PdfDict(V=""))

        # Write the final PDF
        PdfWriter().write(output_path, template_pdf)
        logger.info("PDF erzeugt: {}", output_path)
        return output_path

    except Exception as e:
        logger.error(f"Fehler beim PDF-Generieren: {e}")
        st.error(f"Fehler beim Erstellen des PDFs: {str(e)}")
        return ""




# ─────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────────────────────────────────
def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="Basketball-Fahrtkosten-App",
        page_icon="🏀",
        layout="wide"
    )

    # Initialize session state
    init_session_state()

    # Add reset button in sidebar
    if st.sidebar.button("🔄 Neu starten"):
        reset_session_state()
        st.experimental_rerun()

    st.title("Basketball-Fahrtkosten-App")

    # Show current progress
    progress_text = ""
    if st.session_state.step_1_done:
        progress_text += "✅ Liga-Daten geladen\n"
    if st.session_state.step_2_done:
        progress_text += "✅ Spieldaten hochgeladen\n"
    if st.session_state.step_3_done:
        progress_text += "✅ Spieldetails abgerufen\n"
    if st.session_state.step_4_done:
        progress_text += "✅ PDFs erstellt\n"

    if progress_text:
        st.sidebar.markdown("### Fortschritt\n" + progress_text)

    # Sidebar settings
    st.sidebar.header("PDF-Einstellungen")
    pdf_club_name = st.sidebar.text_input(
        "Verein (für PDF):",
        value=st.session_state.get("pdf_club_name", "Mein Basketball-Verein")
    )
    art_der_veranstaltung = st.sidebar.text_input(
        "Art der Veranstaltung:",
        value=st.session_state.get("art_der_veranstaltung", "Saison")
    )

    st.sidebar.header("Abfahrt Ort")
    home_gym_address = st.sidebar.text_input(
            "Heimatadresse:",
            value=st.session_state.home_gym_address  # Use session state value
        )
        # Update session state with new value
    st.session_state.home_gym_address = home_gym_address

    # Player list upload
    st.sidebar.header("Spieler-Liste")
    player_list_help = """
    Die Spielerliste muss eine CSV- oder Excel-Datei sein mit den Spalten:
    - Vorname
    - Nachname
    - Geburtsdatum
    """
    player_list_file = st.sidebar.file_uploader(
        "Spielerliste (CSV/Excel)",
        type=["csv", "xlsx", "xls"],
        help=player_list_help
    )

    if player_list_file is not None:
        with st.spinner("Lese Spielerliste..."):
            try:
                if player_list_file.name.endswith(".csv"):
                    df = pd.read_csv(player_list_file)
                else:
                    df = pd.read_excel(player_list_file)
                
                if validate_dataframe(df, REQUIRED_COLUMNS["spielerliste"], "Spielerliste"):
                    st.session_state.player_birthdays_df = df
                    st.sidebar.success("✅ Spielerliste erfolgreich geladen")
                else:
                    st.session_state.player_birthdays_df = pd.DataFrame()
            except Exception as e:
                st.sidebar.error(f"Fehler beim Lesen der Spielerliste: {str(e)}")
                st.session_state.player_birthdays_df = pd.DataFrame()

    birthday_lookup = build_birthday_lookup(st.session_state.player_birthdays_df)

    # Main workflow steps
    st.markdown("""
    Diese App hilft dabei, Fahrtkostenzuschüsse für Basketballspiele zu berechnen.
    Folgen Sie den Schritten unten:
    """)

    # Step 1: Fetch Liga Data
    st.header("1️⃣ Liga-Daten abrufen")
    club_name = st.text_input("Vereinsname:", value="TV Heppenheim")

    if not st.session_state.step_1_done:
        if st.button("Liga-Daten abrufen", key="fetch_liga"):
            with st.spinner("Hole Ligadaten..."):
                liga_data = fetch_liga_data(club_name)
                st.session_state.liga_df = liga_data

            if liga_data.empty:
                st.error("❌ Keine Einträge gefunden.")
            else:
                st.success(f"✅ {len(liga_data)} Liga-Einträge gefunden!")
                st.session_state.step_1_done = True

    # Step 2: Upload Game Data
    if st.session_state.step_1_done:
        st.header("2️⃣ Spieldaten hochladen")
        
        if st.session_state.uploaded_df.empty:
            upload_help = """
            Die Spieldaten-Datei muss folgende Spalten enthalten:
            - Liga
            - SpielplanID
            - Gast
            - Halle
            """
            match_file = st.file_uploader(
                "Spieldaten (CSV/Excel)",
                type=["csv", "xlsx", "xls"],
                help=upload_help,
                key="match_file_upload"
            )
            
            if match_file:
                try:
                    with st.spinner("Lese Spieldaten..."):
                        if match_file.name.endswith(".csv"):
                            df = pd.read_csv(match_file)
                        else:
                            df = pd.read_excel(match_file)
                        
                        if validate_dataframe(df, REQUIRED_COLUMNS["spieldaten"], "Spieldaten"):
                            st.session_state.uploaded_df = df
                            st.success("✅ Spieldaten erfolgreich geladen!")
                            st.session_state.step_2_done = True
                except Exception as e:
                    st.error(f"Fehler beim Lesen der Spieldaten: {str(e)}")
        else:
            st.success("✅ Spieldaten bereits vorhanden")
            if st.button("🔄 Andere Spieldaten laden"):
                st.session_state.uploaded_df = pd.DataFrame()
                st.session_state.step_2_done = False
                st.experimental_rerun()
            st.session_state.step_2_done = True

    # Step 3: Select Leagues and Fetch Game Details
    if st.session_state.step_2_done:
        st.header("3️⃣ Ligen auswählen & Spieldetails laden")
        
        df = st.session_state.uploaded_df

        if not st.session_state.liga_df.empty:
            # Create a mapping from Liga name to Liga_ID
            liga_map = pd.Series(
                st.session_state.liga_df["Liga_ID"].values,
                index=st.session_state.liga_df["Liganame"]
            ).to_dict()
            df["Liga_ID"] = df["Liga"].map(liga_map)

        # Get unique combinations of Liga info
        liga_info = (
            df.dropna(subset=["Liga_ID"])
            .drop_duplicates(subset=["Liga_ID"])
            .merge(st.session_state.liga_df, on="Liga_ID", how="left")
        )

        if liga_info.empty:
            st.warning("⚠️ Keine passenden Ligen gefunden.")
        else:
            # Create friendly display options
            options = []
            for _, row in liga_info.iterrows():
                liga_id_val = row["Liga_ID"]
                name_val = row.get("Liganame_x") or row.get("Liganame")
                alter_val = row.get("Alter_x") or row.get("Alter")
                gender_val = row.get("m/w", "")
                
                # Create a user-friendly display with all relevant info
                display_label = (
                    f"{name_val} | {alter_val} ({gender_val}) "
                    f"<span style='color: gray; font-size: smaller;'>[ID: {liga_id_val}]</span>"
                )
                
                options.append((liga_id_val, display_label))

            if not options:
                st.warning("⚠️ Keine Ligen zum Auswählen vorhanden.")
            else:
                # Create selection interface
                st.markdown("#### Verfügbare Ligen")
                display_labels = [opt[1] for opt in options]
                
                selected_display_labels = st.multiselect(
                    "Wähle die zu verarbeitenden Ligen:",
                    options=display_labels,
                    default=display_labels,
                    help="Wählen Sie die Ligen aus, für die PDFs erstellt werden sollen."
                )
                
                if st.button("🔄 Spieldetails laden", key="fetch_details"):
                    # Convert selected labels back to Liga_IDs
                    selected_liga_ids = []
                    for sel_label in selected_display_labels:
                        for (lid, lbl) in options:
                            if lbl == sel_label:
                                selected_liga_ids.append(lid)
                                break
                    
                    match_data = fetch_selected_games(df, selected_liga_ids, club_name)
                    st.session_state.match_details = match_data

                    if match_data.empty:
                        st.warning("⚠️ Keine Details gefunden.")
                    else:
                        st.success(f"✅ {len(match_data)} Spiele gefunden!")
                        st.session_state.step_3_done = True

    # Step 4: Generate PDFs
    if st.session_state.step_3_done and not st.session_state.match_details.empty:
        st.header("4️⃣ PDFs erzeugen")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button("3) PDFs erstellen"):
                template_path = "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf"
                success_count = 0
                st.session_state.generated_files = []
                st.session_state.generated_pdfs_info = []  # Reset the info list

                extended_liga_df = st.session_state.liga_df.set_index("Liga_ID", drop=False)


                with st.spinner("Erzeuge PDFs..."):
                    total_matches = len(st.session_state.match_details)
                    
                    # Progress tracking
                    progress_container = st.container()
                    with progress_container:
                        progress_text = st.empty()
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        start_time = time.time()

                        for idx, row in enumerate(st.session_state.match_details.itertuples(), start=1):
                            # Update progress
                            progress = idx / total_matches
                            progress_bar.progress(progress)
                            
                            # Calculate time estimates
                            elapsed = time.time() - start_time
                            estimated_total = elapsed / progress if progress > 0 else 0
                            remaining = max(0, estimated_total - elapsed)
                            
                            # Extract game info
                            liga_id = getattr(row, "Liga_ID", "Unknown")
                            liganame_val = "Unknown"
                            alter_val = "Unknown"

                            if liga_id in extended_liga_df.index:
                                liganame_val = extended_liga_df.loc[liga_id, "Liganame"]
                                alter_val = str(extended_liga_df.loc[liga_id, "Alter"])

                            # Get hall info
                            hall_name = "Unknown"
                            if "Halle" in df.columns:
                                hall_data = df.loc[
                                    df["SpielplanID"] == getattr(row, "Spielplan_ID"),
                                    "Halle"
                                ]
                                if not hall_data.empty:
                                    hall_name = hall_data.values[0]

                            home_team = getattr(row, "Home Team", "Unknown")

                            # Update status display
                            progress_text.markdown(f"""
                            ### PDF-Generierung läuft...
                            - Fortschritt: {idx}/{total_matches} ({progress:.1%})
                            - Geschätzte Restzeit: {format_time_remaining(remaining)}
                            """)
                            
                            status_text.markdown(f"""
                            **Aktuelles Spiel:**
                            - Liga: {liganame_val}
                            - Halle: {hall_name}
                            - Team: {home_team}
                            """)

                            # Get location and distance
                            resolved_address, dist_km = fetch_away_gym_info(home_team, hall_name)
                            logger.info(f"Distanz HOME -> '{resolved_address}' = {dist_km:.1f} km")

                            # Generate PDF
                            pdf_out_path = generate_pdf(
                                game_details=dict(row._asdict()),
                                pdf_club_name=pdf_club_name,
                                art_der_veranstaltung=art_der_veranstaltung,
                                template_path=template_path,
                                hall=f"{hall_name} ({resolved_address})",
                                birthday_lookup=birthday_lookup,
                                liganame=liganame_val,
                                alter=alter_val,
                                distance_km=dist_km
                            )
                            
                            pdf_info = {
                                "spielplan_id": getattr(row, "Spielplan_ID", "Unknown"),
                                "liga_id": liga_id,
                                "hall_name": hall_name,
                                "resolved_address": resolved_address,
                                "distance_km": dist_km,
                                "players": getattr(row, "Players", []),
                                "home_team": home_team,
                                "away_team": getattr(row, "Away Team", "Unknown"),
                                "date": getattr(row, "Date", "Unknown")
                            }
                            st.session_state.generated_pdfs_info.append(pdf_info)
                            
                            if pdf_out_path:
                                st.session_state.generated_files.append(pdf_out_path)
                                success_count += 1

                    # Clear progress displays
                    progress_container.empty()

                # Show final status
                if success_count > 0:
                    st.success(f"✅ {success_count} PDFs erfolgreich erstellt!")
                    st.session_state.step_4_done = True
                else:
                    st.error("❌ Keine PDFs konnten erstellt werden.")

        # Show download section if files were generated
        if st.session_state.generated_files:
            with col2:
                st.markdown("### 📥 Downloads")
                for pdf_path in st.session_state.generated_files:
                    fname = os.path.basename(pdf_path)
                    with open(pdf_path, "rb") as filehandle:
                        pdf_data = filehandle.read()
                    
                    st.download_button(
                        label=f"📄 {fname}",
                        data=pdf_data,
                        file_name=fname,
                        mime="application/pdf",
                        key=f"download_{uuid.uuid4()}"
                    )

# Add this to your main() function after PDFs are generated:
if st.session_state.step_4_done:
    st.header("📊 Zusammenfassung und Prüfempfehlungen")
    
    analysis = analyze_generated_pdfs(
        st.session_state.generated_pdfs_info,  # Use the stored info
        birthday_lookup,
        st.session_state.generated_files
    )
    
    # Display summary in columns
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📄 Generelle Informationen")
        st.markdown(f"""
        - **Erstellte PDFs:** {analysis['total_pdfs']}
        - **Erfasste Spieler:** {analysis['players_stats']['total']}
            - Mit Geburtsdatum: {analysis['players_stats']['with_birthday']}
            - Ohne Geburtsdatum: {analysis['players_stats']['without_birthday']}
            - Maskierte Spieler: {analysis['players_stats']['masked']}
        """)
        
        st.subheader("🚗 Fahrtstatistiken")
        st.markdown(f"""
        - **Längste Fahrt:** {analysis['distance_stats']['max']:.1f} km
        - **Durchschnitt:** {analysis['distance_stats']['avg']:.1f} km
        - **Gesamtkilometer:** {analysis['distance_stats']['total']:.1f} km
        """)
    
    with col2:
        # Show warnings and items to check
        st.subheader("⚠️ Zu überprüfen")
        
        # Missing birthdays
        if analysis["missing_birthdays"]:
            st.warning("**Fehlende Geburtsdaten:**")
            for player in analysis["missing_birthdays"]:
                st.markdown(f"- {player}")
        else:
            st.success("✅ Alle Spieler haben Geburtsdaten")
            
        # Long distances
        if analysis["long_distances"]:
            st.warning("**Lange Fahrtstrecken (>200km):**")
            for trip in analysis["long_distances"]:
                st.markdown(
                    f"- Spiel {trip['game_id']}: {trip['distance']:.1f} km "
                    f"({trip['location']})"
                )
        else:
            st.success("✅ Keine übermäßig langen Fahrtstrecken")
            
        # Unknown locations
        if analysis["unknown_locations"]:
            st.warning("**Nicht aufgelöste Adressen:**")
            for game_id in analysis["unknown_locations"]:
                st.markdown(f"- Spiel {game_id}")
        else:
            st.success("✅ Alle Adressen wurden erfolgreich aufgelöst")
    
    # Additional recommendations
    st.subheader("💡 Empfehlungen")
    recommendations = []
    
    if analysis["missing_birthdays"]:
        recommendations.append(
            "➡️ Ergänzen Sie fehlende Geburtsdaten in der Spielerliste"
        )
    
    if analysis["long_distances"]:
        recommendations.append(
            "➡️ Prüfen Sie die langen Fahrtstrecken auf Plausibilität"
        )
        
    if analysis["unknown_locations"]:
        recommendations.append(
            "➡️ Überprüfen Sie die Hallenaddressen für nicht aufgelöste Standorte"
        )
        
    if analysis["players_stats"]["masked"] > 0:
        recommendations.append(
            "➡️ Beachten Sie die maskierten Spieler (DSGVO)"
        )
        
    if recommendations:
        st.markdown("\n".join(recommendations))
    else:
        st.success("✅ Keine besonderen Empfehlungen - alles sieht gut aus!")


if __name__ == "__main__":
    main()