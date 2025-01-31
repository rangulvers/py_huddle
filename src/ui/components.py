import uuid
import time
import pandas as pd
import streamlit as st
from typing import List, Dict, Any, Tuple
from src.config import REQUIRED_COLUMNS
from src.data.processing import DataProcessor
from src.pdf.analyzer import PDFAnalysis

class UIComponents:
    """Reusable UI components for the application."""


    @staticmethod
    def render_file_upload(
        label: str,
        help_text: str,
        accepted_types: List[str],
        key: str,
        validation_context: str
    ) -> bool:
        """
        Render file upload widget with validation.
        
        Returns:
            bool: True if file was successfully uploaded and validated
        """
        # Initialize status in session state if not present
        status_key = f"{key}_status"
        if status_key not in st.session_state:
            st.session_state[status_key] = False

        uploaded_file = st.file_uploader(
            label,
            type=accepted_types,
            help=help_text,
            key=key
        )

        if uploaded_file is not None and not st.session_state[status_key]:
            try:
                with st.spinner("Lese Datei..."):
                    # Read file based on file type
                    file_extension = uploaded_file.name.split('.')[-1].lower()
                    if file_extension == "csv":
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    if DataProcessor.validate_dataframe(df, validation_context):
                        # Store DataFrame in session state
                        if key == "player_upload":
                            st.session_state.player_birthdays_df = df
                            st.session_state.player_data_status = True
                        else:  # game_upload
                            st.session_state.uploaded_df = df
                            st.session_state.game_data_status = True
                        
                        st.session_state[status_key] = True
                        return True
                    else:
                        st.error(
                            f"Datei enthält nicht alle erforderlichen Spalten: "
                            f"{', '.join(REQUIRED_COLUMNS[validation_context])}"
                        )
            except Exception as e:
                logger.error(f"Error reading file: {e}")
                st.error(f"Fehler beim Lesen der Datei: {str(e)}")
        
        return st.session_state[status_key]

    @staticmethod
    def render_settings_sidebar():
        """Render settings in the sidebar."""
        with st.sidebar:
            st.header("⚙️ Einstellungen")
            
            # Club name for PDF
            st.session_state.pdf_club_name = st.text_input(
                "Vereinsname für PDF:",
                value=st.session_state.get("pdf_club_name", "")
            )
            
            # Event type
            st.session_state.art_der_veranstaltung = st.text_input(
                "Art der Veranstaltung:",
                value=st.session_state.get("art_der_veranstaltung", "Saison")
            )
            
            # Home gym address
            st.session_state.home_gym_address = st.text_input(
                "Adresse Heimhalle:",
                value=st.session_state.get("home_gym_address", "Weiherhausstraße 8c, 64646 Heppenheim")
            )

    @staticmethod
    def render_progress_bar(
        current: int,
        total: int,
        prefix: str = "",
        suffix: str = ""
    ):
        """Render a progress bar with current/total progress."""
        progress = min(1.0, current / total) if total > 0 else 0
        progress_bar = st.progress(progress)
        st.write(f"{prefix} {current}/{total} {suffix}")
        return progress_bar

    @staticmethod
    def render_analysis_results(analysis: PDFAnalysis):
        """Render PDF analysis results."""
        st.header("📊 Zusammenfassung")
        
        # Overview
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("PDFs erstellt", analysis.total_pdfs)
        with col2:
            st.metric("Spieler gesamt", analysis.total_players)
        with col3:
            st.metric("Fehlende Geburtstage", analysis.unknown_birthdays)
        with col4:
            st.metric("Lange Fahrten", analysis.long_distances)

        # Recommendations
        if analysis.recommendations:
            st.subheader("📝 Empfehlungen")
            for rec in analysis.recommendations:
                st.info(rec)

        # Issues
        if analysis.files_with_issues:
            st.subheader("⚠️ Zu prüfende PDFs")
            for issue in analysis.files_with_issues:
                st.warning(issue)

        # Detailed Statistics
        with st.expander("📈 Detaillierte Statistiken", expanded=False):
            # Liga Statistics
            if analysis.details.get("pdfs_by_liga"):
                st.subheader("PDFs pro Liga")
                liga_df = pd.DataFrame.from_dict(
                    analysis.details["pdfs_by_liga"], 
                    orient='index',
                    columns=['Anzahl']
                )
                st.dataframe(liga_df)

            # Monthly Statistics
            if analysis.details.get("pdfs_by_month"):
                st.subheader("PDFs pro Monat")
                month_df = pd.DataFrame.from_dict(
                    analysis.details["pdfs_by_month"],
                    orient='index',
                    columns=['Anzahl']
                )
                st.dataframe(month_df)

            # Distance Statistics
            if analysis.details.get("distance_stats"):
                st.subheader("Fahrstrecken-Statistiken")
                stats = analysis.details["distance_stats"]
                st.write(f"Gesamt: {stats['total_km']:.1f} km")
                st.write(f"Durchschnitt: {stats['avg_km']:.1f} km")
                st.write(f"Maximum: {stats['max_km']:.1f} km")
                st.write(f"Minimum: {stats['min_km']:.1f} km")

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