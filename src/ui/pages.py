import io
import zipfile
import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger
import dotenv
from src.api.archive import BasketballArchive, ArchiveFilter
from src.ui.components import UIComponents, format_time_remaining
from src.ui.state import SessionState
from src.api.basketball import BasketballClient
from src.api.google_maps import GoogleMapsClient
from src.data.processing import DataProcessor
from src.pdf.generator import PDFGenerator
from src.pdf.analyzer import PDFAnalyzer
from src.auth.login import LoginCredentials
from src.auth.login import BBAuthenticator

class MainPage:
    """Main page of the application."""
    
    def __init__(self):
        """Initialize main page with required clients."""
        self.basketball_client = BasketballClient()
        self.google_maps_client = GoogleMapsClient()
        self.pdf_generator = PDFGenerator()
        self.pdf_analyzer = PDFAnalyzer()
        self.ui = UIComponents()
        
    def render_current_season(self) -> None:
        """Render the current season functionality."""
        st.title("🏀 Basketball Reisekosten Generator")
        # Show debug panel if in debug mode
        if "debug_manager" in st.session_state:
            st.session_state.debug_manager.render_debug_sidebar()
        # Initialize session state
        SessionState.init_state()
        
        # Render settings sidebar
        self.ui.render_settings_sidebar()
        
        # Render steps
        self._render_step_1()
        if st.session_state.step_1_done:
            self._render_step_2()
        if st.session_state.step_2_done:
            self._render_step_3()
        if st.session_state.step_3_done:
            self._render_step_4()

    def render_login_section(self) -> None:
        """Render the login section."""
        st.header("🔐 Login")
        
        with st.form("login_form"):
            st.write("Bitte melden Sie sich an, um auf das Archiv zuzugreifen:")
            dotenv.load_dotenv()
            
            username = st.text_input("Benutzername", value=os.getenv("BASKETBALL_BUND_USERNAME"))
            password = st.text_input("Passwort", type="password", value=os.getenv("BASKETBALL_BUND_PASSWORD"))
            
            submitted = st.form_submit_button("Anmelden")
            
            if submitted:
                if username and password:
                    credentials = LoginCredentials(username=username, password=password)
                    success, error = st.session_state.authenticator.login(credentials)
                    
                    if success:
                        st.session_state.is_logged_in = True
                        st.success("✅ Erfolgreich angemeldet!")
                        
                    else:
                        st.error(f"❌ Anmeldung fehlgeschlagen: {error}")
                else:
                    st.error("❌ Bitte Benutzername und Passwort eingeben!")

    def render(self) -> None:
        """Render the main page."""
        self.render_current_season()

    def _render_login_section(self):
        """Render the login section."""
        st.header("🔐 Login")
        
        # Initialize session state for login
        if 'is_logged_in' not in st.session_state:
            st.session_state.is_logged_in = False
        if 'authenticator' not in st.session_state:
            st.session_state.authenticator = BBAuthenticator()

        # Show login form if not logged in
        if not st.session_state.is_logged_in:
            with st.form("login_form"):
                st.write("Bitte melden Sie sich an, um auf das Archiv zuzugreifen:")
                username = st.text_input("Benutzername")
                password = st.text_input("Passwort", type="password")
                
                submitted = st.form_submit_button("Anmelden")
                
                if submitted:
                    if username and password:
                        credentials = LoginCredentials(username=username, password=password)
                        success, error = st.session_state.authenticator.login(credentials)
                        
                        if success:
                            st.session_state.is_logged_in = True
                            st.success("✅ Erfolgreich angemeldet!")
                            st.rerun()
                        else:
                            st.error(f"❌ Anmeldung fehlgeschlagen: {error}")
                    else:
                        st.error("❌ Bitte Benutzername und Passwort eingeben!")
        else:
            st.success("✅ Sie sind angemeldet")
            if st.button("Abmelden"):
                st.session_state.is_logged_in = False
                st.session_state.authenticator = BBAuthenticator()
                st.rerun()
  
    def render_archive_section(self):
  

        st.header("📚 Archiv")
        # Initialize archive-specific session state variables if not present.
        if "archive_search_done" not in st.session_state:
            st.session_state.archive_search_done = False
        if "archive_matching_leagues" not in st.session_state:
            st.session_state.archive_matching_leagues = []
        
        col1, col2 = st.columns(2)
        with col1:
            current_season = 2023
            season_options = list(range(current_season, current_season - 5, -1))
            st.session_state.archive_selected_season = st.selectbox(
                "Saison auswählen:",
                options=season_options,
                format_func=lambda x: f"{x}/{x+1}",
                key="archive_season"
            )
        with col2:
            st.session_state.archive_club_name = st.text_input(
                "Vereinsname:",
                help="Geben Sie den Vereinsnamen ein (z. B. TV Heppenheim).",
                value="TV Heppenheim",
                key="archive_clubname"
            )
        
        if st.button("Suche starten", use_container_width=True, key="archive_start"):
            if not st.session_state.archive_club_name:
                st.warning("Bitte geben Sie einen Vereinsnamen ein.")
                return
            try:
                progress_placeholder = st.empty()
                with st.spinner("Suche Ligen, in denen der Verein vertreten ist..."):
                    filter_params = ArchiveFilter(
                        season_id=str(st.session_state.archive_selected_season),
                        team_name=st.session_state.archive_club_name
                    )
                    archive_client = BasketballArchive(st.session_state.authenticator)
                    matching_leagues = archive_client.find_team_leagues(
                        filter_params,
                        progress_placeholder=progress_placeholder
                    )
                    progress_placeholder.empty()
                    st.session_state.archive_matching_leagues = matching_leagues
                    st.session_state.archive_search_done = True
                    if matching_leagues:
                        st.success(f"✅ {len(matching_leagues)} Liga(en) gefunden, in denen '{st.session_state.archive_club_name}' spielt.")
                    else:
                        st.warning(f"Keine Liga gefunden, in der '{st.session_state.archive_club_name}' vertreten ist.")
            except Exception as e:
                logger.error(f"Fehler in Archiv-Sektion: {e}")
                st.error("Fehler bei der Suche im Archiv.")
        
        if st.session_state.archive_search_done and st.session_state.archive_matching_leagues:
            # Build league options for the select box.
            league_options = {
                league["liga_id"]: f"{league['name']} ({league['spielklasse']} {league['altersklasse']})"
                for league in st.session_state.archive_matching_leagues
            }
            # Initialize the select box default only once.
            if "selected_league_ids" not in st.session_state:
                st.session_state.selected_league_ids = list(league_options.keys())
            
            selected_league_ids = st.multiselect(
                "Wählen Sie die Ligen aus, für die Sie PDFs erstellen möchten:",
                options=list(league_options.keys()),
                format_func=lambda x: league_options[x],
                default=st.session_state.selected_league_ids,
                key="selected_league_ids"
            )
            
            if selected_league_ids:
                all_away_games = {}
                for league in st.session_state.archive_matching_leagues:
                    if league["liga_id"] in selected_league_ids:
                        st.info(f"Suche Auswärtsspiele für Liga: {league_options[league['liga_id']]}")
                        away_games = BasketballArchive(st.session_state.authenticator).get_away_games(league, st.session_state.archive_club_name)
                        all_away_games[league["liga_id"]] = away_games
                        st.write(f"{len(away_games)} Auswärtsspiele gefunden.")
                        time.sleep(0.3)
                if st.button("PDFs generieren für ausgewählte Ligen", key="generate_pdfs"):
                    pdf_generator = PDFGenerator()
                    generated_pdfs = []
                    for league in st.session_state.archive_matching_leagues:
                        if league["liga_id"] in selected_league_ids:
                            away_games = all_away_games.get(league["liga_id"], [])
                            if away_games:
                                st.info(f"Erstelle PDF für Liga: {league_options[league['liga_id']]}")
                                pdf_info = pdf_generator.generate_archive_pdf(
                                    league_info=league,
                                    away_games=away_games,
                                    club_name=st.session_state.archive_club_name,
                                    event_type=st.session_state.art_der_veranstaltung
                                )
                                if pdf_info:
                                    generated_pdfs.append(pdf_info)
                                    key = f"pdf_{league['liga_id']}"
                                    with open(pdf_info.filepath, 'rb') as pdf_file:
                                        st.session_state[key] = pdf_file.read()
                                    st.download_button(
                                        label=f"PDF herunterladen – {league_options[league['liga_id']]}",
                                        data=st.session_state[key],
                                        file_name=os.path.basename(pdf_info.filepath),
                                        mime="application/pdf",
                                        use_container_width=True
                                    )
                                else:
                                    st.error(f"Fehler beim Generieren des PDFs für {league_options[league['liga_id']]}")
                            else:
                                st.warning(f"Keine Auswärtsspiele für {league_options[league['liga_id']]} gefunden.")
                    if generated_pdfs:
                        st.success("PDF-Erstellung abgeschlossen.")
            else:
                st.info("Bitte wählen Sie mindestens eine Liga aus.")
            
    def _render_step_1(self):
        """Render Step 1: Fetch Liga Data."""
        st.header("1️⃣ Liga-Daten abrufen")
        club_name = st.text_input("Vereinsname:", value="TV Heppenheim")
        
        # Store the club name in session state
        st.session_state.club_name = club_name

        if not st.session_state.step_1_done:
            if st.button("Liga-Daten abrufen"):
                with st.spinner("Hole Ligadaten..."):
                    liga_data = self.basketball_client.fetch_liga_data(club_name)
                    st.session_state.liga_df = liga_data

                if liga_data.empty:
                    st.error("❌ Keine Einträge gefunden.")
                else:
                    st.success(f"✅ {len(liga_data)} Liga-Einträge gefunden!")
                    SessionState.update_progress(1)

    def _render_step_2(self):
        """Render Step 2: Upload Game Data and Player List."""
        st.header("2️⃣ Daten hochladen")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("2.1 Spielerliste hochladen")
            player_list_help = """
            Die Spielerliste muss eine CSV- oder Excel-Datei sein mit den Spalten:
            - Vorname
            - Nachname
            - Geburtsdatum
            """
            
            if not st.session_state.get("player_data_status", False):
                player_list_success = self.ui.render_file_upload(
                    label="Spielerliste (CSV/Excel)",
                    help_text=player_list_help,
                    accepted_types=["csv", "xlsx", "xls"],
                    key="player_upload",
                    validation_context="spielerliste"
                )
            else:
                st.success("✅ Spielerliste geladen")
                if st.button("🔄 Andere Spielerliste laden"):
                    st.session_state.player_birthdays_df = None
                    st.session_state.player_data_status = False
                    st.session_state.player_upload_status = False
                    st.experimental_rerun()

        with col2:
            st.subheader("2.2 Spieldaten hochladen")
            game_data_help = """
            Die Spieldaten-Datei muss folgende Spalten enthalten:
            - Liga
            - SpielplanID
            - Gast
            - Halle
            """
            
            if not st.session_state.get("game_data_status", False):
                game_data_success = self.ui.render_file_upload(
                    label="Spieldaten (CSV/Excel)",
                    help_text=game_data_help,
                    accepted_types=["csv", "xlsx", "xls"],
                    key="game_upload",
                    validation_context="spieldaten"
                )
            else:
                st.success("✅ Spieldaten geladen")
                if st.button("🔄 Andere Spieldaten laden"):
                    st.session_state.uploaded_df = None
                    st.session_state.game_data_status = False
                    st.session_state.game_upload_status = False
                    st.experimental_rerun()

        # Check if both files are loaded
        if (st.session_state.get("player_data_status", False) and 
            st.session_state.get("game_data_status", False)):
            st.success("✅ Alle erforderlichen Daten wurden geladen!")
            
            # Display data previews
            with st.expander("📊 Datenvorschau", expanded=False):
                st.subheader("Spielerliste")
                st.dataframe(st.session_state.player_birthdays_df.head())
                
                st.subheader("Spieldaten")
                st.dataframe(st.session_state.uploaded_df.head())
                
            SessionState.update_progress(2)
        else:
            st.warning("⚠️ Bitte laden Sie beide Dateien hoch, um fortzufahren.")

    def _render_step_3(self):
        """Render Step 3: Select Leagues and Fetch Details."""
        st.header("3️⃣ Ligen auswählen & Spieldetails laden")
        
        df = st.session_state.uploaded_df
        liga_df = st.session_state.liga_df
        club_name = st.session_state.get("club_name", "TV Heppenheim")

        if not liga_df.empty:
            # Create Liga mapping
            liga_map = pd.Series(
                liga_df["Liga_ID"].values,
                index=liga_df["Liganame"]
            ).to_dict()
            df["Liga_ID"] = df["Liga"].map(liga_map)

            # Get unique Liga combinations
            liga_info = (
                df.dropna(subset=["Liga_ID"])
                .drop_duplicates(subset=["Liga_ID"])
                .merge(liga_df, on="Liga_ID", how="left")
            )

            if liga_info.empty:
                st.warning("⚠️ Keine passenden Ligen gefunden.")
            else:
                # Create display options
                options = []
                for _, row in liga_info.iterrows():
                    liga = DataProcessor.create_liga(row)
                    options.append((liga.liga_id, liga.display_name))

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
                        # Convert labels back to IDs
                        selected_liga_ids = []
                        for sel_label in selected_display_labels:
                            for (lid, lbl) in options:
                                if lbl == sel_label:
                                    selected_liga_ids.append(lid)
                                    break

                        # Filter games
                        filtered_df = DataProcessor.filter_relevant_games(
                            df, 
                            selected_liga_ids,
                            club_name
                        )

                        if not filtered_df.empty:
                            with st.spinner("Lade Spieldetails..."):
                                total_games = len(filtered_df)
                                progress_container = st.container()
                                
                                with progress_container:
                                    progress_bar = st.progress(0)
                                    status_text = st.empty()
                                    game_data = []
                                    
                                    for idx, row in filtered_df.iterrows():
                                        # Calculate progress
                                        current_idx = len(game_data)
                                        progress = min(1.0, current_idx / total_games)
                                        progress_bar.progress(progress)
                                        
                                        status_text.markdown(f"""
                                        **Lade Spiel {current_idx + 1}/{total_games}**
                                        - Liga: {row.get('Liga', 'Unknown')}
                                        - SpielplanID: {row.get('SpielplanID', 'Unknown')}
                                        """)

                                        try:
                                            details = self.basketball_client.fetch_game_details(
                                                row['SpielplanID'],
                                                row['Liga_ID']
                                            )
                                            if details:
                                                # Add hall information
                                                details['hall_name'] = row.get('Halle', 'Unknown')
                                                
                                                # Get location info
                                                hall_address, distance = self.google_maps_client.get_gym_location(
                                                    row.get('Gast', ''),
                                                    row.get('Halle', '')
                                                )
                                                details['hall_address'] = hall_address
                                                details['distance'] = distance
                                                
                                                game_data.append(details)
                                        except Exception as e:
                                            logger.error(f"Error fetching game details: {e}")
                                            st.error(f"Fehler beim Laden der Spieldetails: {str(e)}")
                                            continue

                                    # Final progress update
                                    progress_bar.progress(1.0)
                                    
                                    # Clear progress indicators
                                    time.sleep(0.5)
                                    progress_container.empty()

                                if game_data:
                                    st.session_state.match_details = pd.DataFrame(game_data)
                                    st.success(f"✅ {len(game_data)} Spiele gefunden!")
                                    SessionState.update_progress(3)
                                    
                                    # Show preview of loaded data
                                    with st.expander("📊 Vorschau der geladenen Spiele", expanded=False):
                                        st.dataframe(
                                            st.session_state.match_details[
                                                ['Spielplan_ID', 'Liga_ID', 'Date', 
                                                 'Home Team', 'Away Team']
                                            ]
                                        )
                                else:
                                    st.error("❌ Keine Spieldetails gefunden.")
                        else:
                            st.warning("⚠️ Keine passenden Spiele gefunden.")
        else:
            st.error("❌ Keine Liga-Daten vorhanden. Bitte führen Sie Schritt 1 aus.")
    def _render_step_4(self):
        """Render Step 4: Generate PDFs."""
        st.header("4️⃣ PDFs erzeugen")
        
        # Initialize PDF storage in session state if not exists
        if 'generated_pdfs' not in st.session_state:
            st.session_state.generated_pdfs = []

        # PDF Generation Section
        with st.container():
            if st.button("🔄 PDFs generieren", use_container_width=True):
                match_details = st.session_state.match_details
                
                if match_details is None or match_details.empty:
                    st.error("❌ Keine Spieldaten vorhanden.")
                    return

                logger.debug("Starting PDF generation process")
                logger.debug(f"Match details shape: {match_details.shape}")
                logger.debug(f"Columns available: {match_details.columns}")

                # Clear previous PDFs
                st.session_state.generated_pdfs = []
                
                # Build birthday lookup
                birthday_lookup = DataProcessor.build_birthday_lookup(
                    st.session_state.player_birthdays_df
                )
                logger.debug(f"Built birthday lookup with {len(birthday_lookup)} entries")

                # Get settings
                club_name = st.session_state.pdf_club_name
                event_type = st.session_state.art_der_veranstaltung
                logger.debug(f"Using club_name: {club_name}, event_type: {event_type}")

                with st.spinner("Generiere PDFs..."):
                    total_games = len(match_details)
                    progress_container = st.container()
                    
                    with progress_container:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        start_time = time.time()
                        
                        for idx, row in match_details.iterrows():
                            logger.debug(f"Processing game {idx + 1}/{total_games}")
                            logger.debug(f"Game data: {row.to_dict()}")

                            # Calculate progress and update UI
                            progress = (idx + 1) / total_games
                            progress_bar.progress(progress)
                            
                            elapsed_time = time.time() - start_time
                            if idx > 0:
                                time_per_item = elapsed_time / idx
                                remaining_items = total_games - idx
                                remaining_time = time_per_item * remaining_items
                                time_text = format_time_remaining(remaining_time)
                            else:
                                time_text = "Berechne..."

                            status_text.markdown(f"""
                            **Generiere PDF {idx + 1}/{total_games}**  
                            Geschätzte Restzeit: {time_text}  
                            Liga: {row.get('Liga_ID', 'Unknown')}  
                            Spiel: {row.get('Spielplan_ID', 'Unknown')}
                            """)

                            # Get Liga info
                            liga_df_filtered = st.session_state.liga_df[
                                st.session_state.liga_df['Liga_ID'] == row['Liga_ID']
                            ]
                            
                            if liga_df_filtered.empty:
                                logger.warning(f"No Liga info found for Liga_ID: {row['Liga_ID']}")
                                continue

                            liga_info = DataProcessor.create_liga(liga_df_filtered.iloc[0])
                            logger.debug(f"Created Liga info: {liga_info}")

                            # Generate PDF
                            pdf_info = self.pdf_generator.generate_pdf(
                                game_details=row,
                                liga_info=liga_info,
                                club_name=club_name,
                                event_type=event_type,
                                birthday_lookup=birthday_lookup
                            )
                            
                            if pdf_info:
                                st.session_state.generated_pdfs.append(pdf_info)
                                logger.debug(f"Successfully generated PDF: {pdf_info.filepath}")
                            else:
                                logger.error(f"Failed to generate PDF for game {idx + 1}")

        # Results Section (only show if PDFs were generated)
        if st.session_state.generated_pdfs:
            st.write("---")
            
            # Summary Tabs
            tab1, tab2, tab3 = st.tabs(["📊 Übersicht", "📥 Download", "ℹ️ Details"])
            
            with tab1:
                # Statistics Row
                stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                
                total_pdfs = len(st.session_state.generated_pdfs)
                complete_pdfs = sum(1 for d in st.session_state.generated_pdfs if not d.has_unknown_birthdays and d.distance)
                incomplete_pdfs = total_pdfs - complete_pdfs

                # Calculate total distance (safely)
                total_distance = 0
                for pdf in st.session_state.generated_pdfs:
                    try:
                        if isinstance(pdf.distance, (int, float)):
                            total_distance += float(pdf.distance) * 2
                        elif isinstance(pdf.distance, str):
                            total_distance += float(pdf.distance.replace(',', '.')) * 2
                    except (ValueError, AttributeError, TypeError) as e:
                        logger.debug(f"Could not process distance for PDF: {e}")
                        continue

                with stat_col1:
                    st.metric("Generierte PDFs", total_pdfs)
                with stat_col2:
                    st.metric("Vollständig", complete_pdfs)
                with stat_col3:
                    st.metric("Unvollständig", incomplete_pdfs)
                with stat_col4:
                    if total_distance > 0:
                        st.metric("Gesamtkilometer", f"{total_distance:.1f} km")

                # Summary Table
                st.write("### Detaillierte Übersicht")
                
                # Create summary data
                summary_data = []
                for pdf_info in st.session_state.generated_pdfs:
                    missing = []
                    if pdf_info.has_unknown_birthdays:
                        missing.append("Geburtsdaten")
                    if not pdf_info.distance:
                        missing.append("Entfernung")
                    
                    summary_data.append([
                        "⚠️" if missing else "✅",
                        pdf_info.team,
                        pdf_info.date,
                        ", ".join(missing) if missing else "Keine"
                    ])

                # Display as dataframe
                df = pd.DataFrame(
                    summary_data,
                    columns=["Status", "Liga", "Datum", "Fehlende Daten"]
                )
                st.dataframe(df, use_container_width=True)

            with tab2:
                download_col1, download_col2 = st.columns([2, 1])
                
                with download_col1:
                    st.write("### Einzelne PDFs")
                    for pdf_info in st.session_state.generated_pdfs:
                        try:
                            with open(pdf_info.filepath, 'rb') as pdf_file:
                                pdf_data = pdf_file.read()
                            
                            filename = os.path.basename(pdf_info.filepath)
                            st.download_button(
                                label=f"📄 {pdf_info.team} - {pdf_info.date}",
                                data=pdf_data,
                                file_name=filename,
                                mime="application/pdf",
                                key=f"download_{pdf_info.liga_id}_{pdf_info.date}",
                                use_container_width=True
                            )
                        except Exception as e:
                            logger.error(f"Error creating download button: {e}")
                            st.error(f"Fehler beim Laden von {filename}")

                with download_col2:
                    st.write("### Alle PDFs")
                    if len(st.session_state.generated_pdfs) > 1:
                        try:
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for pdf_info in st.session_state.generated_pdfs:
                                    if os.path.exists(pdf_info.filepath):
                                        zip_file.write(
                                            pdf_info.filepath, 
                                            os.path.basename(pdf_info.filepath)
                                        )
                            
                            st.download_button(
                                label="��� Als ZIP herunterladen",
                                data=zip_buffer.getvalue(),
                                file_name="reisekosten_pdfs.zip",
                                mime="application/zip",
                                key="download_all_pdfs",
                                use_container_width=True
                            )
                        except Exception as e:
                            logger.error(f"Error creating ZIP: {e}")
                            st.error("Fehler beim Erstellen der ZIP-Datei")

            with tab3:
                st.write("### Status-Erklärung")
                st.write("✅ - Alle Daten vollständig")
                st.write("⚠️ - Fehlende Daten (siehe Spalte 'Fehlende Daten')")
                
                if any(pdf.has_unknown_birthdays for pdf in st.session_state.generated_pdfs):
                    st.warning("⚠️ Es fehlen Geburtsdaten für einige Spieler")
                if any(not pdf.distance for pdf in st.session_state.generated_pdfs):
                    st.warning("⚠️ Es fehlen Entfernungsangaben für einige Spiele")