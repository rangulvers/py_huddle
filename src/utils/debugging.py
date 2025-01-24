import streamlit as st
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, field
import json
from collections import deque
import time
from loguru import logger

@dataclass
class DebugEntry:
    id: str
    timestamp: str
    category: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

class DebugManager:
    """Manage debug information and display."""
    
    def __init__(self):
        """Initialize debug manager."""
        logger.debug("Initializing DebugManager")
        # Use a key specific to debug entries
        if 'debug_entries_list' not in st.session_state:
            st.session_state.debug_entries_list = deque(maxlen=1000)  # Limit to last 1000 entries
            logger.debug("Created new debug entries list in session state")
        
        # Counter for unique IDs
        if 'debug_entry_counter' not in st.session_state:
            st.session_state.debug_entry_counter = 0
            logger.debug("Initialized debug entry counter")

    def add_entry(self, category: str, message: str, details: Dict[str, Any] = None):
        """Add a debug entry."""
        # Increment counter for unique ID
        st.session_state.debug_entry_counter += 1
        
        entry = DebugEntry(
            id=f"entry_{st.session_state.debug_entry_counter}_{int(time.time()*1000)}",
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            category=category,
            message=message,
            details=details or {}
        )
        
        # Add to deque and force streamlit to recognize the change
        st.session_state.debug_entries_list.append(entry)
        
        # Log to loguru
        logger.debug(f"{entry.category}: {entry.message}")
        if details:
            logger.debug(f"Details: {json.dumps(details, indent=2)}")

    def render_debug_sidebar(self):
        """Render debug information in sidebar."""
        with st.sidebar:
            st.header("🐛 Debug Information")
            
            # Add auto-refresh checkbox
            auto_refresh = st.checkbox("Auto-refresh", value=True)
            
            if auto_refresh:
                st.empty()  # This will force a rerun periodically
            
            # Add filters
            categories = list(set(entry.category for entry in st.session_state.debug_entries_list))
            selected_categories = st.multiselect(
                "Filter by Category",
                categories,
                default=categories
            )
            
            # Add search
            search_term = st.text_input("Search in messages", "")
            
            # Clear button
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Clear Debug Log"):
                    logger.debug("Clearing debug log")
                    st.session_state.debug_entries_list.clear()
                    st.session_state.debug_entry_counter = 0
                    st.experimental_rerun()
            with col2:
                if st.button("Export Log"):
                    logger.debug("Exporting debug log")
                    self._export_debug_log()
            
            # Display entries
            st.markdown("### Debug Log")
            st.markdown(f"Total entries: {len(st.session_state.debug_entries_list)}")
            
            # Create a container for the log entries
            log_container = st.container()
            
            with log_container:
                for entry in reversed(list(st.session_state.debug_entries_list)):
                    if (entry.category in selected_categories and 
                        (not search_term or search_term.lower() in entry.message.lower())):
                        with st.expander(
                            f"[{entry.timestamp}] {entry.category}",
                            expanded=False
                        ):
                            st.markdown(f"**Message:** {entry.message}")
                            if entry.details:
                                st.markdown("**Details:**")
                                try:
                                    st.json(entry.details)
                                except Exception as e:
                                    logger.warning(f"Error displaying JSON details: {e}")
                                    st.code(str(entry.details))

    def log_request(self, url: str, method: str, headers: Dict = None, params: Dict = None, data: Dict = None):
        """Log API request details."""
        logger.debug(f"Logging API request: {method} {url}")
        self.add_entry(
            category="API Request",
            message=f"{method} {url}",
            details={
                "headers": headers or {},
                "params": params or {},
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            }
        )

    def log_response(self, response, context: str):
        """Log API response details."""
        logger.debug(f"Logging API response: {context}")
        self.add_entry(
            category="API Response",
            message=f"{context} - Status: {response.status_code}",
            details={
                "url": response.url,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "elapsed": str(response.elapsed),
                "content_type": response.headers.get('content-type', 'unknown'),
                "timestamp": datetime.now().isoformat()
            }
        )

    def log_data_processing(self, context: str, data: Any):
        """Log data processing details."""
        logger.debug(f"Logging data processing: {context}")
        details = {
            "type": str(type(data)),
            "summary": self._get_data_summary(data),
            "timestamp": datetime.now().isoformat()
        }
        
        self.add_entry(
            category="Data Processing",
            message=context,
            details=details
        )

    def _get_data_summary(self, data: Any) -> Dict:
        """Get summary of data based on its type."""
        try:
            if hasattr(data, 'shape'):  # DataFrame
                return {
                    "shape": str(data.shape),
                    "columns": list(data.columns),
                    "dtypes": {str(k): str(v) for k, v in data.dtypes.items()},
                    "sample": data.head(3).to_dict() if not data.empty else "empty"
                }
            elif isinstance(data, (list, tuple)):
                return {
                    "length": len(data),
                    "type": str(type(data)),
                    "sample": str(data[:3]) if data else "empty"
                }
            elif isinstance(data, dict):
                return {
                    "keys": list(data.keys()),
                    "value_types": {k: str(type(v)) for k, v in data.items()},
                    "sample": {k: str(v) for k, v in list(data.items())[:3]}
                }
            return {"raw": str(data)}
        except Exception as e:
            logger.error(f"Error creating data summary: {e}")
            return {"error": f"Error creating summary: {str(e)}"}

    def _export_debug_log(self):
        """Export debug log as JSON."""
        logger.debug("Exporting debug log")
        export_data = [
            {
                "id": entry.id,
                "timestamp": entry.timestamp,
                "category": entry.category,
                "message": entry.message,
                "details": entry.details
            }
            for entry in st.session_state.debug_entries_list
        ]
        
        st.download_button(
            "Download Debug Log",
            data=json.dumps(export_data, indent=2),
            file_name=f"debug_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )