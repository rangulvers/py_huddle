import os
import re
import time
import math
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Tuple, Optional
from dotenv import load_dotenv
from loguru import logger
from pdfrw import PdfReader, PdfWriter, PdfDict
import uuid

# Load environment variables (e.g., GOOGLE_API_KEY)
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────
# 1) Constants
# ─────────────────────────────────────────────────────────────────────────
HOME_GYM_ADDRESS = os.environ.get("HOME_GYM_ADDRESS", "Heimatadresse nicht gesetzt")

# ─────────────────────────────────────────────────────────────────────────
# 2) Google Geocoding & Distance Matrix
# ─────────────────────────────────────────────────────────────────────────
def google_geocode_address(query: str) -> Optional[dict]:
    """
    Calls Google Geocoding API to convert 'query' into lat/lng plus a
    formatted_address. Returns:
        {
            "lat": float,
            "lng": float,
            "formatted_address": str
        }
    or None if the request fails or the status is not OK.
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query,
        "key": google_api_key
    }

    logger.debug(f"Geocoding for '{query}' with key {google_api_key}")

    try:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(
                f"Geocoding fehlgeschlagen für '{query}' => {data.get('status')}"
            )
            return None

        first_result = data["results"][0]
        location = first_result["geometry"]["location"]
        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "formatted_address": first_result["formatted_address"]
        }

    except Exception as exc:
        logger.warning(f"Fehler bei Google Geocoding für '{query}': {exc}")
        return None


def google_distance_matrix(origins: str, destinations: str) -> float:
    """
    Calls Google's Distance Matrix API to compute driving distance (in km)
    from 'origins' to 'destinations'. Returns the distance (float) or 0.0
    on failure.
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origins,
        "destinations": destinations,
        "key": google_api_key,
        "mode": "driving",
        "language": "de"
    }

    try:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            logger.warning(f"DistanceMatrix-Fehler => {data.get('status')}")
            return 0.0

        # Example: data["rows"][0]["elements"][0]["distance"]["value"] => in meters
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return distance_meters / 1000.0

    except Exception as exc:
        logger.warning(f"Fehler bei Google DistanceMatrix: {exc}")
        return 0.0


def fetch_away_gym_info(opponent_team: str, hall_name: str) -> Tuple[str, float]:
    """
    1) Combine opponent_team + hall_name => geocode via Google Geocoding.
    2) Geocode HOME_GYM_ADDRESS.
    3) Call Google Distance Matrix to find driving distance.
    Returns (resolved_address, distance_km).
    If geocoding fails, returns (hall_name, 0.0).
    """
    query_str = f"{opponent_team} {hall_name} Germany"
    away_geo = google_geocode_address(query_str)
    if not away_geo:
        return hall_name, 0.0

    resolved_address = away_geo["formatted_address"]

    home_geo = google_geocode_address(HOME_GYM_ADDRESS)
    if not home_geo:
        logger.warning("Konnte HOME_GYM_ADDRESS nicht geocoden. 0.0 Distanz.")
        return resolved_address, 0.0

    distance_km = google_distance_matrix(home_geo["formatted_address"], resolved_address)
    return resolved_address, distance_km

# ─────────────────────────────────────────────────────────────────────────
# 3) Helpers
# ─────────────────────────────────────────────────────────────────────────
def parse_date_only(raw_date) -> str:
    """
    Utility function to handle strings/Timestamps, returning "DD.MM.YYYY".
    If parsing fails, returns "Unknown".
    """
    import pandas as pd

    if isinstance(raw_date, (pd.Timestamp, datetime)):
        return raw_date.strftime("%d.%m.%Y")

    if isinstance(raw_date, str):
        try:
            dt = datetime.strptime(raw_date.strip(), "%d.%m.%Y %H:%M:%S")
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            parts = raw_date.strip().split()
            return parts[0] if parts else "Unknown"

    return "Unknown"

def normalize_liga_name(liga_name: str) -> str:
    """
    Removes trailing parentheses groups and strips whitespace from liga_name.
    """
    logger.debug("Normalisiere Liganame: {}", liga_name)
    return re.sub(r"\s*\(.*?\)", "", str(liga_name)).strip()

def build_birthday_lookup(dataframe: pd.DataFrame) -> dict:
    """
    Build a dictionary mapping (Nachname, Vorname) -> Geburtsdatum (str).
    """
    lookup = {}
    for _, row in dataframe.iterrows():
        lastname = str(row.get("Nachname", "")).strip()
        firstname = str(row.get("Vorname", "")).strip()
        raw_date = row.get("Geburtsdatum", "Unknown")
        lookup[(lastname, firstname)] = raw_date
    return lookup

# ─────────────────────────────────────────────────────────────────────────
# 4) Fetching Data
# ─────────────────────────────────────────────────────────────────────────
def fetch_liga_data(club_name: str) -> pd.DataFrame:
    """
    Fetches league data for the given club name from basketball-bund.net.
    Returns a DataFrame with columns:
        "Klasse", "Alter", "m/w", "Bezirk", "Kreis", "Liganame", "Liganr", "Liga_ID"
    """
    logger.debug("Rufe Ligadaten ab für {}", club_name)
    url = "https://www.basketball-bund.net/index.jsp?Action=100&Verband=6"
    payload = (
        f"search={club_name.replace(' ', '+')}"
        "&cbSpielklasseFilter=0&spieltyp_id=0&cbAltersklasseFilter=0"
        "&cbGeschlechtFilter=0&cbBezirkFilter=0&cbKreisFilter=0"
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(url, headers=headers, data=payload)
    soup = BeautifulSoup(response.text, "html.parser")

    form = soup.find("form", {"name": "ligaliste"})
    if not form:
        logger.warning("Kein Formular 'ligaliste' gefunden")
        return pd.DataFrame()

    target_table = None
    tables = soup.find_all("table", class_="sportView")
    for table_element in tables:
        headers_in_table = table_element.find_all("td", class_="sportViewHeader")
        if headers_in_table:
            header_texts = [h.get_text(strip=True) for h in headers_in_table]
            if {"Klasse", "Alter", "Liganame"}.issubset(header_texts):
                target_table = table_element
                break

    data_list = []
    if target_table:
        rows = target_table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            klasse = cells[0].get_text(strip=True)
            alter = cells[1].get_text(strip=True)
            gender = cells[2].get_text(strip=True)
            bezirk = cells[3].get_text(strip=True)
            kreis = cells[4].get_text(strip=True)
            liga_name = cells[5].get_text(strip=True)
            liga_nr = cells[6].get_text(strip=True)

            liga_id = None
            links = cells[7].find_all("a", href=True)
            for link in links:
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
    return pd.DataFrame(data_list)


def fetch_game_details(spielplan_id: str, liga_id: str) -> Optional[dict]:
    """
    Fetches details for a single game (given spielplan_id and liga_id).
    Returns a dict with keys like "Date", "Home Team", "Away Team", "Players", etc.
    or None on failure.
    """
    logger.debug("Rufe Spieldetails ab: {}, {}", spielplan_id, liga_id)
    url = (
        "https://www.basketball-bund.net/public/ergebnisDetails.jsp?"
        f"type=1&spielplan_id={spielplan_id}&liga_id={liga_id}&defaultview=1"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as exc:
        logger.warning(f"Fehler beim Abrufen Spieldetails: {exc}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    game_details = {}

    try:
        ergebnisliste_form = soup.find("form", {"name": "ergebnisliste"})
        if ergebnisliste_form:
            rows = ergebnisliste_form.find_all("tr")
            for row in rows[1:]:  # skip header
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
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

        player_stats_form = soup.find("form", {"name": "spielerstatistikgast"})
        player_list = []
        if player_stats_form:
            rows = player_stats_form.find_all("tr")
            for row in rows[1:]:  # skip header
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                lastname = cells[0].get_text(strip=True)
                firstname = cells[1].get_text(strip=True)
                if lastname and firstname and lastname != "Nachname" and firstname != "Vorname":
                    player_list.append({"Nachname": lastname, "Vorname": firstname})

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
    except Exception as exc:
        logger.error(f"Fehler beim Parsen: {exc}")
        return None


def fetch_selected_games(df: pd.DataFrame, selected_ligas: list, club_name: str) -> pd.DataFrame:
    """
    Loops over the uploaded DataFrame, extracts rows that match
    the selected leagues AND contain the club_name in 'Gast',
    then fetches their game details via fetch_game_details.
    Returns a DataFrame of all found games.
    """
    logger.debug("fetch_selected_games Verein: {}", club_name)

    # The spinner is optional but gives a top-level "loading" indicator
    with st.spinner("Spieldetails werden geladen..."):
        game_data = []

        # Filter rows we actually want to process: "Liga_ID" in selected_ligas & 'Gast' contains club_name
        # This helps us show a progress bar only for the relevant subset
        subset_df = df[
            df["Liga_ID"].isin(selected_ligas) & 
            df["Gast"].fillna("").str.contains(club_name, na=False)
        ].copy()

        # If these columns don't exist, bail out
        if "Liga_ID" not in df.columns or "SpielplanID" not in df.columns:
            st.warning("Fehlende Spalten 'Liga_ID' oder 'SpielplanID'.")
            return pd.DataFrame()
        
        # Create a progress bar for only this subset
        total_relevant = len(subset_df)
        if total_relevant == 0:
            st.info("Keine Spiele gefunden (keine passenden Zeilen).")
            return pd.DataFrame()
        
        progress_bar = st.progress(0.0)
        status_placeholder = st.empty()

        # We'll increment a counter each time we call fetch_game_details
        processed_count = 0

        for idx, row in subset_df.iterrows():
            # Retrieve info
            liga_id = row.get("Liga_ID", "Unknown")
            spielplan_id = row.get("SpielplanID", "Unknown")

            # Now we only update the text/placeholder when we call fetch_game_details
            status_placeholder.info(
                f"Lade Spieldetails für Spielplan {spielplan_id}, Liga {liga_id} "
                f"({processed_count + 1}/{total_relevant})..."
            )

            details = fetch_game_details(spielplan_id, liga_id)
            if details:
                game_data.append(details)

            processed_count += 1
            progress_bar.progress(processed_count / total_relevant)

            # Optionally add a small sleep to avoid flooding the server
            time.sleep(0.25)

        # Clear spinner & placeholders after we’re done, or just keep it as is
        status_placeholder.empty()
        progress_bar.empty()

    # Final output
    if not game_data:
        st.info("Keine Spiele gefunden.")
    
    return pd.DataFrame(game_data)

# ─────────────────────────────────────────────────────────────────────────
# 5) generate_pdf
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
    Generates a single PDF file from the given template, placing relevant info
    such as game details, players, and distance. Returns the path to the output PDF.
    """
    logger.debug("PDF generieren für: {}", game_details)

    # Double the distance_km and round up
    distance_km = math.ceil(distance_km * 2)

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

    # We only want up to 5 players:
    final_players = players_with_bday[:5]
    if len(final_players) < 5:
        needed = 5 - len(final_players)
        final_players.extend(players_no_bday[:needed])

    # Mask names containing "*"
    for idx, player_info in enumerate(final_players):
        if "*" in player_info["Nachname"]:
            final_players[idx] = {"Nachname": "Geblocked durch DSGVO", "Vorname": ""}

    liga_id = game_details.get("Liga_ID", "NoLigaID") or "NoLigaID"
    date_str = game_details["Date"].replace(":", "-").replace("/", "-").replace("\\", "-")
    filename = f"{liga_id}_{alter}_{date_str}.pdf"

    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", filename)

    template_pdf = PdfReader(template_path)
    for page in template_pdf.pages:
        annotations = page.get("/Annots") or []
        for annotation in annotations:
            if "/T" not in annotation:
                continue

            field_name = annotation["/T"][1:-1]

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
                # Any other fields we leave empty
                annotation.update(PdfDict(V=""))

    PdfWriter().write(output_path, template_pdf)
    logger.info("PDF erzeugt: {}", output_path)
    return output_path

# ─────────────────────────────────────────────────────────────────────────
# 6) Streamlit Workflow
# ─────────────────────────────────────────────────────────────────────────
if "step_1_done" not in st.session_state:
    st.session_state.step_1_done = False
if "step_2_done" not in st.session_state:
    st.session_state.step_2_done = False
if "step_3_done" not in st.session_state:
    st.session_state.step_3_done = False
if "step_4_done" not in st.session_state:
    st.session_state.step_4_done = False

if "liga_df" not in st.session_state:
    st.session_state.liga_df = pd.DataFrame()
if "uploaded_df" not in st.session_state:
    st.session_state.uploaded_df = pd.DataFrame()
if "match_details" not in st.session_state:
    st.session_state.match_details = pd.DataFrame()
if "player_birthdays_df" not in st.session_state:
    st.session_state.player_birthdays_df = pd.DataFrame()
if "generated_files" not in st.session_state:
    st.session_state.generated_files = []

st.title("Basketball-Fahrtkosten-App")

st.markdown(
    """
    Diese App hilft dabei, Fahrtkostenzuschüsse für Basketballspiele zu berechnen.
    """
)

# Sidebar
st.sidebar.header("PDF-Einstellungen")
pdf_club_name = st.sidebar.text_input("Verein (für PDF):", "Mein Basketball-Verein")
art_der_veranstaltung = st.sidebar.text_input("Art der Veranstaltung:", "Saison")

# Reisekosten Einstellungen
st.sidebar.header("Abfahrt Ort")
HOME_GYM_ADDRESS = st.sidebar.text_input("Heimatadresse:", HOME_GYM_ADDRESS)

# Spieler-Liste
st.sidebar.header("Spieler-Liste")
player_list_file = st.sidebar.file_uploader("Spielerliste (CSV/Excel)", type=["csv", "xlsx", "xls"])


if player_list_file is not None:
    with st.spinner("Lese Spielerliste..."):
        if player_list_file.name.endswith(".csv"):
            st.session_state.player_birthdays_df = pd.read_csv(player_list_file)
        else:
            st.session_state.player_birthdays_df = pd.read_excel(player_list_file)
    
    required_columns = {"Vorname", "Nachname", "Geburtsdatum"}
    if required_columns.issubset(st.session_state.player_birthdays_df.columns):
        st.sidebar.success("Spielerliste erfolgreich geladen.")
    else:
        st.sidebar.error("Die Spielerliste muss die Spalten 'Vorname', 'Nachname' und 'Geburtsdatum' enthalten.")

birthday_lookup = build_birthday_lookup(st.session_state.player_birthdays_df)

# STEP 1
st.subheader("Schritt 1: Liga-Daten abrufen")
club_name = st.text_input("Vereinsname:", "TV Heppenheim")

if not st.session_state.step_1_done:
    if st.button("1) Liga-Daten abrufen"):
        with st.spinner("Hole Ligadaten..."):
            liga_data = fetch_liga_data(club_name)
            st.session_state.liga_df = liga_data

        if liga_data.empty:
            st.warning("Keine Einträge gefunden.")
        else:
            st.success(f"{len(liga_data)} Liga-Einträge gefunden.")
            st.session_state.step_1_done = True

# STEP 2
if st.session_state.step_1_done:
    st.subheader("Schritt 2: Spieldaten hochladen")
    if st.session_state.uploaded_df.empty:
        match_file = st.file_uploader("Spieldaten (CSV/Excel)", type=["csv", "xlsx", "xls"])
        if match_file:
            with st.spinner("Lese Spieldaten..."):
                if match_file.name.endswith(".csv"):
                    st.session_state.uploaded_df = pd.read_csv(match_file)
                else:
                    st.session_state.uploaded_df = pd.read_excel(match_file)
            st.success("Spieldaten erfolgreich geladen!")
            st.session_state.step_2_done = True
    else:
        st.success("Spieldaten bereits vorhanden.")
        st.session_state.step_2_done = True

# STEP 3
# Step 3: Ligen auswählen & Spieldetails laden
if st.session_state.step_2_done:
    st.subheader("Schritt 3: Ligen auswählen & Spieldetails laden")

    df = st.session_state.uploaded_df

    # 1) Combine Liganame + Alter + Liga_ID into a friendly label
    #    Make sure your df has columns "Liganame", "Liga_ID", and "Alter".
    #    If something’s missing, handle gracefully.
    if not st.session_state.liga_df.empty:
        # Map the "Liga" column in the uploaded df to "Liga_ID" in the liga_df
        liga_map = pd.Series(
            st.session_state.liga_df["Liga_ID"].values,
            index=st.session_state.liga_df["Liganame"]
        ).to_dict()
        df["Liga_ID"] = df["Liga"].map(liga_map)

    # Grab unique sets of (Liga_ID, Liganame, Alter)  
    liga_info = (
        df.dropna(subset=["Liga_ID"])
        .drop_duplicates(subset=["Liga_ID"])
        .merge(st.session_state.liga_df, on="Liga_ID", how="left")
        # st.session_state.liga_df should also have columns [Liganame, Alter, Liga_ID]
    )

    if liga_info.empty:
        st.info("Keine passenden Ligen gefunden.")
    else:
        # Build (liga_id -> display_label) pairs
        options = []
        for _, row in liga_info.iterrows():
            liga_id_val = row["Liga_ID"]
            name_val = row.get("Liganame_x") or row.get("Liganame")
            alter_val = row.get("Alter_x") or row.get("Alter")
            
            # Build a friendly label like: "Oberliga Herren (ID: 12345, Alter: Herren)"
            # Adjust to your actual columns
            display_label = f"{name_val} (ID: {liga_id_val}, Alter: {alter_val})"
            
            options.append((liga_id_val, display_label))

        if not options:
            st.info("Keine Ligen zum Auswählen vorhanden.")
        else:
            # Extract just the display labels for the multiselect
            display_labels = [opt[1] for opt in options]
            
            # Use the same list as both the choices and the default
            # (or filter if you prefer a smaller default)
            selected_display_labels = st.multiselect(
                "Wähle Ligen:",
                options=display_labels,
                default=display_labels
            )
            
            if st.button("2) Spieldetails laden"):
            
                    # Convert display labels back to actual Liga_IDs
                selected_liga_ids = []
                for sel_label in selected_display_labels:
                    for (lid, lbl) in options:
                        if lbl == sel_label:
                            selected_liga_ids.append(lid)
                            break
                    
                match_data = fetch_selected_games(df, selected_liga_ids, club_name)
                st.session_state.match_details = match_data

                # After loading completes
                if match_data.empty:
                    st.info("Keine Details gefunden.")
                else:
                    st.success(f"{len(match_data)} Spiele gefunden.")
                    st.session_state.step_3_done = True

# STEP 4
if st.session_state.step_3_done and not st.session_state.match_details.empty:
    st.subheader("Schritt 4: PDFs erzeugen")
    if st.button("3) PDFs erstellen"):
        template_path = "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf"
        success_count = 0
        st.session_state.generated_files = []

        extended_liga_df = st.session_state.liga_df.set_index("Liga_ID", drop=False)

        with st.spinner("Erzeuge PDFs..."):
            total_matches = len(st.session_state.match_details)
            # Create a progress bar
            pdf_progress_bar = st.progress(0)
            # A placeholder text element to update each iteration
            current_pdf_text = st.empty()

            success_count = 0

            for idx, row in enumerate(st.session_state.match_details.itertuples(), start=1):
                # Retrieve info from the row
                liga_id = getattr(row, "Liga_ID", "Unknown")
                liganame_val = "Unknown"
                alter_val = "Unknown"

                if liga_id in extended_liga_df.index:
                    liganame_val = extended_liga_df.loc[liga_id, "Liganame"]
                    alter_val = str(extended_liga_df.loc[liga_id, "Alter"])

                hall_name = "Unknown"
                if "Halle" in df.columns:
                    hall_data = df.loc[df["SpielplanID"] == getattr(row, "Spielplan_ID"), "Halle"]
                    if not hall_data.empty:
                        hall_name = hall_data.values[0]

                home_team = getattr(row, "Home Team", "Unknown")

                # Update the text so the user knows which game is being processed
                current_pdf_text.info(
                    f"Verarbeite Spiel {idx}/{total_matches} - "
                    f"Liga: {liga_id} / {liganame_val} - Halle: {hall_name}"
                )

                # Combine => geocode
                resolved_address, dist_km = fetch_away_gym_info(home_team, hall_name)
                logger.info(f"Distanz HOME -> '{resolved_address}' = {dist_km:.1f} km")

                pdf_out_path = generate_pdf(
                    game_details=dict(row._asdict()),  # row is a namedtuple, convert to dict
                    pdf_club_name=pdf_club_name,
                    art_der_veranstaltung=art_der_veranstaltung,
                    template_path=template_path,
                    hall=f"{hall_name} ({resolved_address})",
                    birthday_lookup=birthday_lookup,
                    liganame=liganame_val,
                    alter=alter_val,
                    distance_km=dist_km
                )
                st.session_state.generated_files.append(pdf_out_path)
                success_count += 1

                # Update progress bar after each iteration
                pdf_progress_bar.progress(idx / total_matches)

        # After loop finishes
        st.success(f"{success_count} PDFs erstellt.")
        current_pdf_text.empty()  # Clear the info message

        # Download Buttons
        for pdf_path in st.session_state.generated_files:
            fname = os.path.basename(pdf_path)
            with open(pdf_path, "rb") as filehandle:
                pdf_data = filehandle.read()
            st.download_button(
                label=f"Download {fname}",
                data=pdf_data,
                file_name=fname,
                mime="application/pdf",
                key=uuid.uuid4()  # ensure unique key
            )

        st.session_state.step_4_done = True

# Abschluss
if st.session_state.step_4_done:
    st.subheader("Fertig!")
    st.write(
        "Alle PDFs wurden erstellt. Du kannst sie einzeln herunterladen. "
    )