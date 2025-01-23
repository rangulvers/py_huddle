import streamlit as st
from src.ui.pages import MainPage
from src.config import APP_CONFIG
import logging
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger.add(
    "app.log",
    rotation="500 MB",
    retention="10 days",
    level="DEBUG"
)

def main():
    """Application entry point."""
    try:
        # Initialize and render main page
        page = MainPage()
        page.render()
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        st.error(
            "Ein unerwarteter Fehler ist aufgetreten. "
            "Bitte versuchen Sie es später erneut oder kontaktieren Sie den Support."
        )

if __name__ == "__main__":
    main()