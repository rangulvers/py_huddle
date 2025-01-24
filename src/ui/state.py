import streamlit as st
from typing import Optional
from src.config import HOME_GYM_ADDRESS

class SessionState:
    """Manage Streamlit session state."""
    
    @staticmethod
    def init_state():
        """Initialize or reset all session state variables."""
        defaults = {
            # Workflow steps
            "step_1_done": False,
            "step_2_done": False,
            "step_3_done": False,
            "step_4_done": False,
            
            # Data storage
            "liga_df": None,
            "uploaded_df": None,
            "match_details": None,
            "player_birthdays_df": None,
            "generated_files": [],
            "generated_pdfs_info": [],
            
            # Settings
            "home_gym_address": HOME_GYM_ADDRESS,
            "pdf_club_name": "Mein Basketball-Verein",
            "art_der_veranstaltung": "Saison",
            
            # File upload flags
            "player_data_uploaded": False,
            "game_data_uploaded": False,
            
            # Processing info
            "processing_start_time": None,
            "last_error": None,
            "current_operation": None
        }
        
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    @staticmethod
    def update_progress(step: int):
        """Update progress for a step."""
        step_key = f"step_{step}_done"
        if step_key in st.session_state:
            st.session_state[step_key] = True

    @staticmethod
    def reset_progress(step: Optional[int] = None):
        """Reset progress for a specific step or all steps."""
        if step:
            step_key = f"step_{step}_done"
            if step_key in st.session_state:
                st.session_state[step_key] = False
        else:
            for i in range(1, 5):
                st.session_state[f"step_{i}_done"] = False