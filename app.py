import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import re
from loguru import logger
from pdfrw import PdfReader, PdfWriter, PdfDict
from datetime import datetime
from typing import Tuple, Optional
from dotenv import load_dotenv
# Load environment variables from a .env file
load_dotenv()
# -------------------------------------------------------------------------
# 1) Constants
# -------------------------------------------------------------------------
HOME_GYM_ADDRESS = "Am Stadion 2, 64646 Heppenheim (Bergstraße)"
# e.g. your real home gym address

# -------------------------------------------------------------------------
# 2) Google Geocoding & Distance Matrix
# -------------------------------------------------------------------------
def google_geocode_address(query: str) -> Optional[dict]:
    """
    Calls Google Geocoding API to convert 'query' into lat/lng plus a formatted_address.
    Returns a dict { 'lat': float, 'lng': float, 'formatted_address': str } or None on failure.
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")

    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query,
        "key": google_api_key
    }
    
    logger.debug(f"Geocoding for '{query}' with key {google_api_key}")

    try:
        resp = requests.get(endpoint, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(f"Geocoding fehlgeschlagen für '{query}' => {data.get('status')}")
            return None

        first = data["results"][0]
        location = first["geometry"]["location"]  # lat/lng
        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "formatted_address": first["formatted_address"]
        }
    except Exception as e:
        logger.warning(f"Fehler bei Google Geocoding für '{query}': {e}")
        return None

def google_distance_matrix(origins: str, destinations: str) -> float:
    """
    Calls Google's Distance Matrix API to compute driving distance (in kilometers)
    from 'origins' to 'destinations' (both are string addresses).
    Returns the distance in KM, or 0.0 if something fails.
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
        resp = requests.get(endpoint, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK":
            logger.warning(f"DistanceMatrix-Fehler => {data.get('status')}")
            return 0.0

        # Usually: data["rows"][0]["elements"][0]["distance"]["value"] => meters
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        distance_km = distance_meters / 1000.0
        return distance_km
    except Exception as e:
        logger.warning(f"Fehler bei Google DistanceMatrix: {e}")
        return 0.0

def fetch_away_gym_info(opponent_team: str, hall_name: str) -> Tuple[str, float]:
    """
    1) Combine opponent_team + hall_name => Geocode via Google Geocoding.
    2) Also geocode HOME_GYM_ADDRESS.
    3) Call Google Distance Matrix to find driving distance between them.
    Returns (resolved_address, distance_km).
    If geocoding fails, returns (hall_name, 0.0).
    """
    # Combine them into one query, e.g. "Team Tigers Albert-Einstein-Schule Germany"
    query_str = f"{opponent_team} {hall_name} Germany"
    away_geo = google_geocode_address(query_str)
    if not away_geo:
        return (hall_name, 0.0)
    resolved_address = away_geo["formatted_address"]

    # Optionally, geocode HOME_GYM_ADDRESS if you want an exact address for distance
    home_geo = google_geocode_address(HOME_GYM_ADDRESS)
    if not home_geo:
        logger.warning("Konnte HOME_GYM_ADDRESS nicht geocoden. 0.0 Distanz.")
        return (resolved_address, 0.0)

    # Distance from home to away
    distance_km = google_distance_matrix(home_geo["formatted_address"], resolved_address)

    return (resolved_address, distance_km)


# -------------------------------------------------------------------------
# 3) parse_date_only
# -------------------------------------------------------------------------
def parse_date_only(raw_date) -> str:
    """
    Example utility that handles strings or Timestamps, returning "DD.MM.YYYY".
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
            if parts:
                return parts[0]
            return "Unknown"
    return "Unknown"

# -------------------------------------------------------------------------
# 4) fetch_liga_data, fetch_game_details, fetch_selected_games
#    (same structure as your previous code)
# -------------------------------------------------------------------------
def normalize_liga_name(liga_name: str) -> str:
    logger.debug("Normalisiere Liganame: {}", liga_name)
    return re.sub(r"\s*\(.*?\)", "", str(liga_name)).strip()

def fetch_liga_data(club_name: str) -> pd.DataFrame:
    logger.debug("Rufe Ligadaten ab für {}", club_name)
    url = "https://www.basketball-bund.net/index.jsp?Action=100&Verband=6"
    payload = (
        f"search={club_name.replace(' ', '+')}"
        "&cbSpielklasseFilter=0&spieltyp_id=0&cbAltersklasseFilter=0"
        "&cbGeschlechtFilter=0&cbBezirkFilter=0&cbKreisFilter=0"
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(url, headers=headers, data=payload)
    soup = BeautifulSoup(resp.text, "html.parser")

    form = soup.find("form", {"name": "ligaliste"})
    if not form:
        logger.warning("Kein Formular 'ligaliste' gefunden")
        return pd.DataFrame()

    tables = soup.find_all("table", class_="sportView")
    target_table = None
    for t in tables:
        headers_in_table = t.find_all("td", class_="sportViewHeader")
        if headers_in_table:
            header_texts = [h.get_text(strip=True) for h in headers_in_table]
            if "Klasse" in header_texts and "Alter" in header_texts and "Liganame" in header_texts:
                target_table = t
                break

    data_list = []
    if target_table:
        rows = target_table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) >= 8:
                klasse = cells[0].get_text(strip=True)
                alter = cells[1].get_text(strip=True)
                gender = cells[2].get_text(strip=True)
                bezirk = cells[3].get_text(strip=True)
                kreis = cells[4].get_text(strip=True)
                liganame = cells[5].get_text(strip=True)
                liganr = cells[6].get_text(strip=True)
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
                    "Liganame": normalize_liga_name(liganame),
                    "Liganr": liganr,
                    "Liga_ID": liga_id
                })
    return pd.DataFrame(data_list)

def fetch_game_details(spielplan_id: str, liga_id: str) -> dict:
    logger.debug("Rufe Spieldetails ab: {}, {}", spielplan_id, liga_id)
    url = f"https://www.basketball-bund.net/public/ergebnisDetails.jsp?type=1&spielplan_id={spielplan_id}&liga_id={liga_id}&defaultview=1"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen Spieldetails: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    game_details = {}
    try:
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
                            "Away Score": cells[5].get_text(strip=True).split(" : ")[1].strip(),
                        }
                    except IndexError:
                        continue
                    break

        player_stats_form = soup.find("form", {"name":"spielerstatistikgast"})
        player_list = []
        if player_stats_form:
            rows = player_stats_form.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    lastname = cells[0].get_text(strip=True)
                    firstname = cells[1].get_text(strip=True)
                    if lastname and firstname and lastname!="Nachname" and firstname!="Vorname":
                        player_list.append({"Nachname": lastname, "Vorname": firstname})

        return {
            "Spielplan_ID": spielplan_id,
            "Liga_ID": liga_id,
            "Date": game_details.get("Date","Unknown"),
            "Home Team": game_details.get("Home Team","Unknown"),
            "Away Team": game_details.get("Away Team","Unknown"),
            "Home Score": game_details.get("Home Score","?"),
            "Away Score": game_details.get("Away Score","?"),
            "Players": player_list
        }
    except Exception as e:
        logger.error(f"Fehler beim Parsen: {e}")
        return None

def fetch_selected_games(df: pd.DataFrame, selected_ligas: list, club_name: str) -> pd.DataFrame:
    logger.debug("fetch_selected_games Verein: {}", club_name)
    game_data = []
    total = len(df)
    progress_bar = st.progress(0)
    counter = 0

    for _, row in df.iterrows():
        counter += 1
        progress_bar.progress(counter/total)
        if "Liga_ID" not in df.columns or "SpielplanID" not in df.columns:
            st.warning("Fehlende Spalten 'Liga_ID' oder 'SpielplanID'.")
            return pd.DataFrame()

        liga_id = row.get("Liga_ID")
        spielplan_id = row.get("SpielplanID")
        guest_team = row.get("Gast")

        if pd.notna(spielplan_id) and pd.notna(liga_id) and liga_id in selected_ligas and club_name in guest_team:
            details = fetch_game_details(spielplan_id, liga_id)
            if details:
                game_data.append(details)
        time.sleep(0.25)

    progress_bar.empty()
    if not game_data:
        st.info("Keine Spiele gefunden.")
    else:
        st.success(f"{len(game_data)} Spieldetails gefunden!")
    return pd.DataFrame(game_data)

# -------------------------------------------------------------------------
# 5) generate_pdf
# -------------------------------------------------------------------------
def generate_pdf(game_details: dict,
                 pdf_club_name: str,
                 art_der_veranstaltung: str,
                 template_path: str,
                 hall: str,
                 birthday_lookup: dict,
                 liganame: str,
                 distance_km: float,
                 alter: str ="Unknown") -> str:
    logger.debug("PDF generieren für: {}", game_details)
    all_players = game_details.get("Players", [])
    players_with_bday = []
    players_no_bday = []

    for p in all_players:
        ln, fn = p["Nachname"], p["Vorname"]
        raw_gdate = birthday_lookup.get((ln, fn), "Unknown")
        if raw_gdate != "Unknown":
            players_with_bday.append(p)
        else:
            players_no_bday.append(p)

    final_players = players_with_bday[:5]
    if len(final_players)<5:
        needed = 5 - len(final_players)
        final_players.extend(players_no_bday[:needed])

    # Mask names with "*"
    for idx, plyr in enumerate(final_players):
        if "*" in plyr["Nachname"]:
            final_players[idx] = {"Nachname":"Geblocked durch DSGVO", "Vorname":""}

    liga_id = game_details.get("Liga_ID","NoLigaID") or "NoLigaID"
    date_str = game_details["Date"].replace(":","-").replace("/","-").replace("\\","-")
    filename = f"{liga_id}_{alter}_{date_str}.pdf"

    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", filename)

    template = PdfReader(template_path)
    for page in template.pages:
        annotations = page.get('/Annots') or []
        for annotation in annotations:
            if '/T' not in annotation:
                continue
            field_name = annotation['/T'][1:-1]
            if field_name=="Verein":
                annotation.update(PdfDict(V=pdf_club_name))
            elif field_name=="Abteilung":
                annotation.update(PdfDict(V="Basketball"))
            elif field_name=="Art der Veranstaltung":
                annotation.update(PdfDict(V=art_der_veranstaltung))
            elif field_name=="Mannschaften":
                annotation.update(PdfDict(V=liganame))
            elif field_name=="DatumRow1":
                annotation.update(PdfDict(V=game_details["Date"]))
            elif field_name=="Name oder SpielortRow1":
                annotation.update(PdfDict(V=hall))
            elif field_name.startswith("Name oder SpielortRow"):
                m = re.search(r"Name oder SpielortRow(\d+)$", field_name)
                if m:
                    row_number = int(m.group(1))
                    offset = 2
                    index = row_number - offset
                    if 0 <= index< len(final_players):
                        player_data = final_players[index]
                        annotation.update(PdfDict(V=f"{player_data['Nachname']}, {player_data['Vorname']}"))
                    else:
                        annotation.update(PdfDict(V=""))
            elif field_name.startswith("EinzelteilngebRow"):
                m = re.search(r"EinzelteilngebRow(\d+)$", field_name)
                if m:
                    row_number = int(m.group(1))
                    offset = 2
                    index = row_number - offset
                    if 0<=index<len(final_players):
                        pdta = final_players[index]
                        ln, fn = pdta["Nachname"], pdta["Vorname"]
                        raw_bday = birthday_lookup.get((ln, fn),"Unknown")
                        final_bday = parse_date_only(raw_bday) if raw_bday!="Unknown" else "Unknown"
                        annotation.update(PdfDict(V=final_bday))
                    else:
                        annotation.update(PdfDict(V=""))
            else:
                # empty
                annotation.update(PdfDict(V=""))

    PdfWriter().write(output_path, template)
    logger.info("PDF erzeugt: {}", output_path)
    return output_path

# -------------------------------------------------------------------------
# 6) Streamlit Workflow
# -------------------------------------------------------------------------
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

st.title("Basketball-Fahrtkosten-App - Google Geocode & Distance Matrix")

st.markdown("""
Diese Version verwendet ausschließlich die Google-APIs:  
• Google Geocoding API, um die (Team + Halle)-Angabe in lat/lng + formattierte Adresse umzuwandeln.  
• Google Distance Matrix API, um die Fahrdistanz zwischen unserer Heimhalle und der Auswärtshalle zu berechnen.  
""")

# Sidebar
st.sidebar.header("PDF-Einstellungen")
pdf_club_name = st.sidebar.text_input("Verein (für PDF):","Mein Basketball-Verein")
art_der_veranstaltung = st.sidebar.text_input("Art der Veranstaltung:","Saison")

# Spieler-Liste
st.sidebar.header("Spieler-Geburtsdaten-Liste")
player_list_file = st.sidebar.file_uploader("Spielerliste (CSV/Excel)", type=["csv","xlsx","xls"])

def build_birthday_lookup(df: pd.DataFrame):
    lookup = {}
    for _, row in df.iterrows():
        ln = str(row.get("Nachname","")).strip()
        fn = str(row.get("Vorname","")).strip()
        raw_date = row.get("Geburtsdatum","Unknown")
        lookup[(ln, fn)] = raw_date
    return lookup

if player_list_file is not None:
    with st.spinner("Lese Spielerliste..."):
        if player_list_file.name.endswith(".csv"):
            st.session_state.player_birthdays_df = pd.read_csv(player_list_file)
        else:
            st.session_state.player_birthdays_df = pd.read_excel(player_list_file)
    st.sidebar.success("Spielerliste erfolgreich geladen.")

birthday_lookup = build_birthday_lookup(st.session_state.player_birthdays_df)

# STEP 1
st.subheader("Schritt 1: Liga-Daten abrufen")
club_name = st.text_input("Vereinsname:", "TV Heppenheim")
if not st.session_state.step_1_done:
    if st.button("1) Liga-Daten abrufen"):
        with st.spinner("Hole Ligadaten..."):
            ld = fetch_liga_data(club_name)
            st.session_state.liga_df = ld
        if ld.empty:
            st.warning("Keine Einträge gefunden.")
        else:
            st.success(f"{len(ld)} Liga-Einträge gefunden.")
            st.session_state.step_1_done = True

# STEP 2
if st.session_state.step_1_done:
    st.subheader("Schritt 2: Spieldaten hochladen")
    if st.session_state.uploaded_df.empty:
        match_file = st.file_uploader("Spieldaten (CSV/Excel)", type=["csv","xlsx","xls"])
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
if st.session_state.step_2_done and not st.session_state.uploaded_df.empty:
    st.subheader("Schritt 3: Ligen auswählen & Spieldetails laden")
    df = st.session_state.uploaded_df

    if not st.session_state.liga_df.empty:
        liga_map = pd.Series(st.session_state.liga_df.Liga_ID.values,
                             index=st.session_state.liga_df.Liganame).to_dict()
        df["Liga_ID"] = df["Liga"].map(liga_map)

    avail_ligas = df["Liga_ID"].dropna().unique().tolist()
    if not avail_ligas:
        st.info("Keine passenden Liga-IDs gefunden.")
    else:
        selected_ligas = st.multiselect("Wähle Ligen:", avail_ligas, default=avail_ligas)
        if st.button("2) Spieldetails laden"):
            with st.spinner("Hole Spieldetails..."):
                md = fetch_selected_games(df, selected_ligas, club_name)
                st.session_state.match_details = md
            if md.empty:
                st.info("Keine Details gefunden.")
            else:
                st.success(f"{len(md)} Spiele gefunden.")
                st.session_state.step_3_done = True

# STEP 4
if st.session_state.step_3_done and not st.session_state.match_details.empty:
    st.subheader("Schritt 4: PDFs erzeugen")
    if st.button("3) PDFs erstellen"):
        template_path = "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf"
        success_count = 0
        st.session_state.generated_files = []

        df_liga_extended = st.session_state.liga_df.set_index("Liga_ID", drop=False)

        with st.spinner("Erzeuge PDFs..."):
            for idx, row in st.session_state.match_details.iterrows():
                liga_id = row.get("Liga_ID","Unknown")
                liganame_val = "Unknown"
                alter_val = "Unknown"
                if liga_id in df_liga_extended.index:
                    liganame_val = df_liga_extended.loc[liga_id,"Liganame"]
                    alter_val = str(df_liga_extended.loc[liga_id,"Alter"])

                hall_name = "Unknown"
                if "Halle" in df.columns:
                    hall_data = df.loc[df["SpielplanID"]==row["Spielplan_ID"], "Halle"]
                    if not hall_data.empty:
                        hall_name = hall_data.values[0]

                home_team = row.get("Home Team","Unknown")

                # 1) combine => geocode
                resolved_address, distance_km = fetch_away_gym_info(home_team, hall_name)

                logger.info(f"Distanz HOME -> '{resolved_address}' = {distance_km:.1f} km")

                pdf_out = generate_pdf(
                    game_details=row,
                    pdf_club_name=pdf_club_name,
                    art_der_veranstaltung=art_der_veranstaltung,
                    template_path=template_path,
                    hall=f"{hall_name} ({resolved_address})",
                    birthday_lookup=birthday_lookup,
                    liganame=liganame_val,
                    alter=alter_val,
                    distance_km=distance_km
                )
                st.session_state.generated_files.append(pdf_out)
                success_count += 1

        st.success(f"{success_count} PDFs erstellt.")

        # Download Buttons
        for pdf_path in st.session_state.generated_files:
            fname = os.path.basename(pdf_path)
            with open(pdf_path,"rb") as f:
                pdf_data = f.read()
            st.download_button(
                label=f"Download {fname}",
                data=pdf_data,
                file_name=fname,
                mime="application/pdf",
                key=f"download_{fname}"
            )

        st.session_state.step_4_done = True

if st.session_state.step_4_done:
    st.subheader("Fertig!")
    st.write("Alle PDFs wurden erstellt. Die Adressen wurden via Google Geocoding aufgelöst, und die Distanz via Google Distance Matrix ermittelt.")