# main.py
import streamlit as st
from loguru import logger
import os
import sys
from src.ui.pages import MainPage
from src.ui.state import SessionState
from src.utils.debugging import DebugManager
from src.auth.login import BBAuthenticator, LoginCredentials
from src.utils.logging import setup_logging

def main():
    """Main entry point of the application."""
    try:
        # Set page config
        st.set_page_config(
            page_title="Basketball Reisekosten Generator",
            page_icon="🏀",
            layout="wide"
        )

        # Check for debug mode from environment variable or command line argument
        debug_mode = (
            os.getenv("STREAMLIT_DEBUG", "false").lower() == "true" or
            "--debug" in sys.argv
        )

        # Setup logging only once
        if 'logging_initialized' not in st.session_state:
            setup_logging(debug_mode)
            st.session_state.logging_initialized = True
            logger.info(f"Starting application in {'debug' if debug_mode else 'normal'} mode")

        # Initialize debug manager if in debug mode and not already initialized
        if debug_mode and 'debug_manager' not in st.session_state:
            debug_manager = DebugManager()
            st.session_state.debug_manager = debug_manager
            logger.debug("Debug manager initialized")

        # Initialize session state
        SessionState.init_state()

        # Initialize authenticator in session state if not exists
        if 'authenticator' not in st.session_state:
            st.session_state.authenticator = BBAuthenticator()
            logger.debug("Authenticator initialized")

        st.title("Basketball Reisekosten Generator")

        # Rest of your code...
        # Create tabs for current season and archive
        tab1, tab2 = st.tabs(["Aktuelle Saison", "Archiv"])

        # Create main page instance
        page = MainPage()

        with tab1:
            # Regular season functionality
            page.render_current_season()

        with tab2:
            # Archive section
            if not st.session_state.get('is_logged_in', False):
                page.render_login_section()
            else:
                # Show archive functionality and logout button
                col1, col2 = st.columns([6, 1])
                with col1:
                    page.render_archive_section()
                with col2:
                    if st.button("Abmelden", use_container_width=True):
                        st.session_state.is_logged_in = False
                        st.session_state.authenticator = BBAuthenticator()
                        st.rerun()

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {str(e)}")


if __name__ == "__main__":
    with logger.catch():
        main()
