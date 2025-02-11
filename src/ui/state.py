import streamlit as st
from typing import Optional, Dict, Any
from src.config import HOME_GYM_ADDRESS, PDF_CONFIG

class SessionState:
    """Manage Streamlit session state."""
    
    @staticmethod
    def init_state() -> None:
        defaults: Dict[str, Any] = {
            "step_1_done": False,
            "step_2_done": False,
            "step_3_done": False,
            "step_4_done": False,
            "liga_df": None,
            "uploaded_df": None,
            "match_details": None,
            "player_birthdays_df": None,
            "generated_files": [],
            "generated_pdfs_info": [],
            "home_gym_address": HOME_GYM_ADDRESS,
            "pdf_club_name": PDF_CONFIG.get("pdf_club_name"),
            "art_der_veranstaltung": "Saison",
            "player_data_uploaded": False,
            "game_data_uploaded": False,
            "processing_start_time": None,
            "last_error": None,
            "current_operation": None
        }
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    @staticmethod
    def update_progress(step: int) -> None:
        st.session_state[f"step_{step}_done"] = True

    @staticmethod
    def reset_progress(step: Optional[int] = None) -> None:
        if step:
            st.session_state[f"step_{step}_done"] = False
        else:
            for i in range(1, 5):
                st.session_state[f"step_{i}_done"] = False