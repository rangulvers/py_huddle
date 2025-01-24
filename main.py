import streamlit as st
from loguru import logger
from src.ui.pages import MainPage
from src.ui.state import SessionState

def main():
    """Main entry point of the application."""
    try:
        # Configure logger
        logger.add(
            "app.log",
            rotation="500 MB",
            retention="10 days",
            level="DEBUG"
        )
        
        # Initialize session state
        SessionState.init_state()
        
        # Create and render main page
        page = MainPage()
        page.render()
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {str(e)}")

if __name__ == "__main__":
    main()