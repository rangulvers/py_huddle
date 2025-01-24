import streamlit as st
from loguru import logger
import os
import sys
from src.ui.pages import MainPage
from src.ui.state import SessionState
from src.utils.debugging import DebugManager

def setup_logging(debug_mode: bool):
    """Configure logging based on debug mode."""
    # Remove any existing handlers
    logger.remove()
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Add console handler with appropriate level
    log_level = "DEBUG" if debug_mode else "INFO"
    logger.add(
        "logs/app.log",
        rotation="500 MB",
        retention="10 days",
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        lambda msg: print(msg),
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    )

def main():
    """Main entry point of the application."""
    try:
        # Check for debug mode from environment variable or command line argument
        debug_mode = (
            os.getenv("STREAMLIT_DEBUG", "false").lower() == "true" or
            "--debug" in sys.argv
        )
        
        # Setup logging
        setup_logging(debug_mode)
        logger.info(f"Starting application in {'debug' if debug_mode else 'normal'} mode")
        
        # Initialize debug manager if in debug mode
        if debug_mode:
            debug_manager = DebugManager()
            st.session_state.debug_manager = debug_manager
            logger.debug("Debug manager initialized")
        
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