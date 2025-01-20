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

# ─────────────────────────────────────────────────────────────────────────
# 1) Erweiterte fetch_liga_data (liefert Liga_ID, Liganame, etc.)
# ─────────────────────────────────────────────────────────────────────────
def normalize_liga_name(liga_name: str) -> str:
    logger.debug("Normalisiere Liganame: {}", liga_name)
    return re.sub(r"\s*\(.*?\)", "", str(liga_name)).strip()

def fetch_liga_data(club_name: str) -> pd.DataFrame:
    """
    Ruft Daten von basketball-bund.net ab und gibt ein DataFrame mit Spalten zurück:
    [Klasse, Alter, m/w, Bezirk, Kreis, Liganame, Liganr, Liga_ID].
    """
    logger.debug("Rufe Ligadaten ab für Verein: {}", club_name)
    url = "https://www.basketball-bund.net/index.jsp?Action=100&Verband=6"

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/x-www-form-urlencoded",
        "upgrade-insecure-requests": "1",
    }

    payload = f"search={club_name.replace(' ', '+')}&cbSpielklasseFilter=0&spieltyp_id=0&cbAltersklasseFilter=0&cbGeschlechtFilter=0&cbBezirkFilter=0&cbKreisFilter=0"
    response = requests.post(url, headers=headers, data=payload)
    soup = BeautifulSoup(response.text, "html.parser")

    form = soup.find("form", {"name": "ligaliste"})
    if not form:
        logger.warning("Kein Formular mit Namen 'ligaliste' gefunden")
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
        for row in rows[1:]:  # Überspringe Kopfzeile
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


# ─────────────────────────────────────────────────────────────────────────
# 2) fetch_game_details und fetch_selected_games
# ─────────────────────────────────────────────────────────────────────────
def fetch_game_details(spielplan_id: str, liga_id: str) -> dict:
    logger.debug("Rufe Spieldetails ab: spielplan_id={}, liga_id={}", spielplan_id, liga_id)
    url = f"https://www.basketball-bund.net/public/ergebnisDetails.jsp?type=1&spielplan_id={spielplan_id}&liga_id={liga_id}&defaultview=1"

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "user-agent": "Mozilla/5.0"
    }

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        logger.warning("Fehler beim Abrufen der Spieldetails für {} - {}", spielplan_id, liga_id)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    game_details = {}

    try:
        ergebnisliste_form = soup.find("form", {"name": "ergebnisliste"})
        if ergebnisliste_form:
            rows = ergebnisliste_form.find_all("tr")
            for row in rows[1:]:  # Überspringe Kopf
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
                    except IndexError as e:
                        logger.error("IndexError beim Auslesen der Spieldetails: {}", e)
                        continue
                    break

        # Spielerstatistiken
        player_stats_form = soup.find("form", {"name": "spielerstatistikgast"})
        player_list = []
        if player_stats_form:
            rows = player_stats_form.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    try:
                        lastname = cells[0].get_text(strip=True).strip()
                        firstname = cells[1].get_text(strip=True).strip()
                        if lastname and firstname and lastname != "Nachname" and firstname != "Vorname":
                            player_list.append({"Nachname": lastname, "Vorname": firstname})
                    except IndexError as e:
                        logger.error("IndexError beim Auslesen der Spielerstatistiken: {}", e)
                        continue

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

    except Exception as e:
        logger.error("Allgemeiner Fehler beim Abrufen der Spieldaten: {}", e)
        return None

def fetch_selected_games(df: pd.DataFrame, selected_ligas: list, club_name: str) -> pd.DataFrame:
    logger.debug("Rufe ausgewählte Spiele ab für Verein: {}", club_name)
    game_data = []
    total = len(df)
    progress_bar = st.progress(0)
    counter = 0

    for idx, row in df.iterrows():
        counter += 1
        progress_bar.progress(counter / total)
        if "Liga_ID" not in df.columns or "SpielplanID" not in df.columns:
            st.warning("Es fehlen die Spalten 'Liga_ID' oder 'SpielplanID' in der Tabelle.")
            return pd.DataFrame()

        liga_id = row.get("Liga_ID")
        spielplan_id = row.get("SpielplanID")
        guest_team = row.get("Gast")

        if pd.notna(spielplan_id) and pd.notna(liga_id) and liga_id in selected_ligas and club_name in guest_team:
            details = fetch_game_details(spielplan_id, liga_id)
            if details:
                game_data.append(details)

        time.sleep(0.3)

    progress_bar.empty()
    if not game_data:
        st.info("Keine passenden Spiele gefunden für die gewählten Filter.")
    else:
        st.success(f"{len(game_data)} Spieldetails abgerufen!")
    return pd.DataFrame(game_data)


# ─────────────────────────────────────────────────────────────────────────
# 3) parse_date_only
# ─────────────────────────────────────────────────────────────────────────
def parse_date_only(raw_date) -> str:
    """
    Wandelt raw_date in das Format 'DD.MM.YYYY' um, wenn möglich.
    Berücksichtigt Timestamps, datetime-Objekte und Strings in 
    'DD.MM.YYYY HH:MM:SS' oder 'DD.MM.YYYY'.
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


# ─────────────────────────────────────────────────────────────────────────
# 4) generate_pdf (inkl. Liganame)
# ─────────────────────────────────────────────────────────────────────────
def generate_pdf(game_details: dict,
                 pdf_club_name: str,
                 art_der_veranstaltung: str,
                 template_path: str,
                 hall: str,
                 birthday_lookup: dict,
                 liganame: str,
                 alter: str = "Unknown") -> str:
    """
    Erzeugt ein PDF im Ordner "output" mit dem Namen "ligaID_alter_date.pdf".
    1) Bis zu 5 Spieler, zuerst jene mit bekanntem Geburtsdatum. 
    2) 'Mannschaften' umfasst jetzt auch den Liganamen: "Home vs Away / {liganame}".
    """
    logger.debug("Erzeuge PDF für Spiel: {}", game_details)

    # Spieler in 2 Gruppen (Geburtsdatum bekannt vs unbekannt)
    all_players = game_details["Players"]
    players_with_bday = []
    players_no_bday = []
    for pl in all_players:
        ln, fn = pl["Nachname"], pl["Vorname"]
        raw_gdate = birthday_lookup.get((ln, fn), "Unknown")
        if raw_gdate != "Unknown":
            players_with_bday.append(pl)
        else:
            players_no_bday.append(pl)

    # Finale Liste mit max. 5 Spielern
    final_players = players_with_bday[:5]
    if len(final_players) < 5:
        needed = 5 - len(final_players)
        final_players.extend(players_no_bday[:needed])

    # Maskiere Spieler mit "*"
    for idx, p in enumerate(final_players):
        if "*" in p["Nachname"]:
            final_players[idx] = {"Nachname": "Geblocked durch DSGVO", "Vorname": ""}

    liga_id = game_details.get("Liga_ID", "NoLigaID") or "NoLigaID"
    date_str = game_details["Date"].replace(":", "-").replace("/", "-").replace("\\", "-")
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
            if field_name == "Verein":
                annotation.update(PdfDict(V=pdf_club_name))
            elif field_name == "Abteilung":
                annotation.update(PdfDict(V="Basketball"))
            elif field_name == "Art der Veranstaltung":
                annotation.update(PdfDict(V=art_der_veranstaltung))
            elif field_name == "Mannschaften":
                # Zeige Heim vs Gast / Liganame
   
                annotation.update(PdfDict(V=liganame))
            elif field_name == "DatumRow1":
                annotation.update(PdfDict(V=game_details['Date']))
            elif field_name == "Name oder SpielortRow1":
                annotation.update(PdfDict(V=hall))
            elif field_name.startswith("Name oder SpielortRow"):
                m = re.search(r"Name oder SpielortRow(\d+)$", field_name)
                if m:
                    row_number = int(m.group(1))
                    offset = 2
                    index = row_number - offset
                    if 0 <= index < len(final_players):
                        p = final_players[index]
                        annotation.update(PdfDict(V=f"{p['Nachname']}, {p['Vorname']}"))
                    else:
                        annotation.update(PdfDict(V=""))
            elif field_name.startswith("EinzelteilngebRow"):
                m = re.search(r"EinzelteilngebRow(\d+)$", field_name)
                if m:
                    row_number = int(m.group(1))
                    offset = 2
                    index = row_number - offset
                    if 0 <= index < len(final_players):
                        p = final_players[index]
                        ln, fn = p["Nachname"], p["Vorname"]
                        raw_bday = birthday_lookup.get((ln, fn), "Unknown")
                        final_bday = parse_date_only(raw_bday) if raw_bday != "Unknown" else "Unknown"
                        annotation.update(PdfDict(V=final_bday))
                    else:
                        annotation.update(PdfDict(V=""))
            else:
                annotation.update(PdfDict(V=""))

    PdfWriter().write(output_path, template)
    logger.info("PDF erzeugt: {}", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 5) Streamlit-Schritte (auf Deutsch) mit Download-Links
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
    st.session_state.uploaded_df = None
if "match_details" not in st.session_state:
    st.session_state.match_details = pd.DataFrame()
if "player_birthdays_df" not in st.session_state:
    st.session_state.player_birthdays_df = pd.DataFrame()

if "generated_files" not in st.session_state:
    st.session_state.generated_files = []

st.title("Basketball-Fahrtkosten-App")

st.markdown("""
Diese Anwendung ruft erweiterte Ligadaten (Klasse, Alter, Liganame usw.) ab,
lädt Teamlisten hoch und erzeugt PDF-Formulare mit:
• maximal 5 Spielern (Geburtsdatum prioritär).  
• Liganame in der Zeile "Mannschaften".  
• Download-Links für jedes erzeugte PDF.
""")

# Seiteneinstellungen (PDF)
st.sidebar.header("PDF-Einstellungen")
pdf_club_name = st.sidebar.text_input("Verein (für PDF):", "Mein Basketball-Verein")
art_der_veranstaltung = st.sidebar.text_input("Art der Veranstaltung:", "Saison")

# Spieler-Geburtsdaten-Liste
st.sidebar.header("Spieler-Geburtsdaten-Liste")
player_list_file = st.sidebar.file_uploader("Spielerliste hochladen (CSV/Excel)", type=["csv", "xlsx", "xls"])

def build_birthday_lookup(df: pd.DataFrame) -> dict:
    lookup = {}
    for _, row in df.iterrows():
        ln = (row.get("Nachname", "")).strip() if pd.notna(row.get("Nachname")) else ""
        fn = (row.get("Vorname", "")).strip() if pd.notna(row.get("Vorname")) else ""
        raw_date = row.get("Geburtsdatum", "Unknown")
        lookup[(ln, fn)] = raw_date
    return lookup

if player_list_file is not None:
    with st.spinner("Lade Spielerliste..."):
        if player_list_file.name.endswith(".csv"):
            st.session_state.player_birthdays_df = pd.read_csv(player_list_file)
        else:
            st.session_state.player_birthdays_df = pd.read_excel(player_list_file)
    st.sidebar.success("Spielerliste erfolgreich hochgeladen!")

birthday_lookup = build_birthday_lookup(st.session_state.player_birthdays_df)

# ─────────────────────────────────────────────────────────────────────────
# Schritt 1: Liga-Daten abrufen
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Schritt 1: Liga-Daten abrufen")
club_name = st.text_input("Vereinsname eingeben:", value="TV Heppenheim", key="club_name_de")
if not st.session_state.step_1_done:
    if st.button("1) Liga-Daten abrufen"):
        with st.spinner("Rufe erweiterte Ligadaten ab..."):
            st.session_state.liga_df = fetch_liga_data(club_name)
        if st.session_state.liga_df.empty:
            st.warning("Keine Daten für diesen Verein gefunden.")
        else:
            st.success(f"{len(st.session_state.liga_df)} Liga-Einträge gefunden.")
            st.session_state.step_1_done = True

# ─────────────────────────────────────────────────────────────────────────
# Schritt 2: Spieldaten-Datei hochladen
# ─────────────────────────────────────────────────────────────────────────
if st.session_state.step_1_done:
    st.subheader("Schritt 2: Spieldaten-Datei hochladen")
    if st.session_state.uploaded_df is None:
        match_file = st.file_uploader("Spieldaten (CSV/Excel)", type=["csv", "xlsx", "xls"], key="match_file_de")
        if match_file:
            with st.spinner("Lese Spieldaten..."):
                if match_file.name.endswith(".csv"):
                    st.session_state.uploaded_df = pd.read_csv(match_file)
                else:
                    st.session_state.uploaded_df = pd.read_excel(match_file)
            st.success("Spieldaten erfolgreich geladen!")
            st.session_state.step_2_done = True
    else:
        st.success("Spieldaten sind bereits geladen.")
        st.session_state.step_2_done = True

# ─────────────────────────────────────────────────────────────────────────
# Schritt 3: Spiele abrufen
# ─────────────────────────────────────────────────────────────────────────
if st.session_state.step_2_done and st.session_state.uploaded_df is not None:
    st.subheader("Schritt 3: Ligen auswählen & Spieldetails abrufen")
    df = st.session_state.uploaded_df

    # Liga-ID anhand st.session_state.liga_df suchen
    if not st.session_state.liga_df.empty:
        liga_map = pd.Series(st.session_state.liga_df.Liga_ID.values,
                             index=st.session_state.liga_df.Liganame).to_dict()
        df["Liga_ID"] = df["Liga"].map(liga_map)

    available_ligas = df["Liga_ID"].dropna().unique().tolist()
    if not available_ligas:
        st.info("Keine passenden Liga-IDs in der Spieldatei. Prüfe die Daten.")
    else:
        selected_ligas = st.multiselect("Wähle Ligen aus:", available_ligas, default=available_ligas)
        if st.button("2) Spieldetails abrufen"):
            with st.spinner("Hole Spieldetails..."):
                st.session_state.match_details = fetch_selected_games(df, selected_ligas, club_name)
            if not st.session_state.match_details.empty:
                st.success(f"{len(st.session_state.match_details)} Spiele abgerufen!")
                st.session_state.step_3_done = True
            else:
                st.info("Keine Spieldetails für die gewählten Ligen gefunden.")

# ─────────────────────────────────────────────────────────────────────────
# Schritt 4: PDFs erzeugen & Download-Links anzeigen
# ─────────────────────────────────────────────────────────────────────────
if st.session_state.step_3_done and not st.session_state.match_details.empty:
    st.subheader("Schritt 4: PDF-Dateien erzeugen")
    if st.button("3) PDFs erstellen"):
        template_path = "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf"
        success_count = 0
        st.session_state.generated_files = []

        # Index st.session_state.liga_df nach Liga_ID
        df_liga_extended = st.session_state.liga_df.set_index("Liga_ID", drop=False)

        with st.spinner("Erzeuge PDFs..."):
            for idx, row in st.session_state.match_details.iterrows():
                liga_id = row.get("Liga_ID", "Unknown")
                liganame_val = "Unknown"
                alter_val = "Unknown"
                if liga_id in df_liga_extended.index:
                    liganame_val = df_liga_extended.loc[liga_id, "Liganame"]
                    alter_val = str(df_liga_extended.loc[liga_id, "Alter"])

                hall = "Unknown"
                if "Halle" in df.columns:
                    hall_data = df.loc[df["SpielplanID"] == row["Spielplan_ID"], "Halle"]
                    if not hall_data.empty:
                        hall = hall_data.values[0]

                output_pdf = generate_pdf(
                    game_details=row,
                    pdf_club_name=pdf_club_name,
                    art_der_veranstaltung=art_der_veranstaltung,
                    template_path=template_path,
                    hall=hall,
                    birthday_lookup=birthday_lookup,
                    liganame=liganame_val,
                    alter=alter_val
                )
                st.session_state.generated_files.append(output_pdf)
                logger.debug("PDF erzeugt: {}", output_pdf)
                success_count += 1

        st.success(f"{success_count} PDFs wurden im Ordner 'output' erzeugt.")

        # Download-Buttons für jede erzeugte PDF-Datei
        for pdf_path in st.session_state.generated_files:
            fname = os.path.basename(pdf_path)
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()

            st.download_button(
                label=f"Herunterladen: {fname}",
                data=pdf_data,
                file_name=fname,
                mime="application/pdf"
            )

        st.session_state.step_4_done = True

# Zusammenfassung
if st.session_state.step_4_done:
    st.subheader("Alle Schritte abgeschlossen")
    st.write("Die PDF-Dateien wurden erfolgreich erzeugt und können oben heruntergeladen werden!")