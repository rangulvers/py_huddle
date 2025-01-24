from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
import pandas as pd
from loguru import logger
import streamlit as st
from src.config import BASKETBALL_CONFIG, ERROR_MESSAGES

class BasketballClient:
    """Client for interacting with basketball-bund.net."""
    
    def __init__(self):
        self.base_url = BASKETBALL_CONFIG["base_url"]
        self.verband = BASKETBALL_CONFIG["verband"]

    def fetch_liga_data(self, club_name: str) -> pd.DataFrame:
        """
        Fetch league data for a club.
        
        Args:
            club_name: Name of the basketball club
            
        Returns:
            DataFrame with league information
        """
        logger.debug(f"Fetching liga data for club: {club_name}")
        
        url = f"{self.base_url}/index.jsp?Action=100&Verband={self.verband}"
        payload = self._build_liga_search_payload(club_name)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        logger.debug(f"Request URL: {url}")
        try:
            response = requests.post(url, headers=headers, data=payload)
            response.raise_for_status()
            return self._parse_liga_data(response.text)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching liga data: {e}")
            st.error(ERROR_MESSAGES["network_error"].format(error=str(e)))
            return pd.DataFrame()
        except Exception as e:
            logger.exception(f"Unexpected error fetching liga data: {e}")
            st.error(ERROR_MESSAGES["unexpected_error"].format(error=str(e)))
            return pd.DataFrame()

    def fetch_game_details(self, spielplan_id: str, liga_id: str) -> Optional[Dict]:
        """
        Fetch details for a specific game.
        
        Args:
            spielplan_id: Game schedule ID
            liga_id: League ID
            
        Returns:
            Dictionary with game details
        """
        logger.debug(f"Fetching game details: spielplan_id={spielplan_id}, liga_id={liga_id}")
        
        url = self._build_game_details_url(spielplan_id, liga_id)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return self._parse_game_details(response.text, spielplan_id, liga_id)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching game details: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error fetching game details: {e}")
            return None

    def _build_liga_search_payload(self, club_name: str) -> str:
        """Build search payload for liga data request."""
        return (
            f"search={club_name.replace(' ', '+')}"
            "&cbSpielklasseFilter=0"
            "&spieltyp_id=0"
            "&cbAltersklasseFilter=0"
            "&cbGeschlechtFilter=0"
            "&cbBezirkFilter=0"
            "&cbKreisFilter=0"
        )

    def _build_game_details_url(self, spielplan_id: str, liga_id: str) -> str:
        """Build URL for game details request."""
        return (
            f"{self.base_url}/public/ergebnisDetails.jsp?"
            f"type=1&spielplan_id={spielplan_id}&liga_id={liga_id}&defaultview=1"
        )

    def _parse_liga_data(self, html: str) -> pd.DataFrame:
        """Parse HTML response for liga data."""
        soup = BeautifulSoup(html, "html.parser")
        data_list = []

        form = soup.find("form", {"name": "ligaliste"})
        if not form:
            logger.warning("No 'ligaliste' form found")
            return pd.DataFrame()

        target_table = None
        tables = soup.find_all("table", class_="sportView")
        for table in tables:
            headers = table.find_all("td", class_="sportViewHeader")
            if headers:
                header_texts = [h.get_text(strip=True) for h in headers]
                if {"Klasse", "Alter", "Liganame"}.issubset(header_texts):
                    target_table = table
                    break

        if not target_table:
            logger.warning("No liga table found")
            return pd.DataFrame()

        rows = target_table.find_all("tr")
        for row in rows[1:]:  # Skip header row
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            liga_data = {
                "Klasse": cells[0].get_text(strip=True),
                "Alter": cells[1].get_text(strip=True),
                "m/w": cells[2].get_text(strip=True),
                "Bezirk": cells[3].get_text(strip=True),
                "Kreis": cells[4].get_text(strip=True),
                "Liganame": cells[5].get_text(strip=True),
                "Liganr": cells[6].get_text(strip=True),
                "Liga_ID": None
            }

            for link in cells[7].find_all("a", href=True):
                if "Action=102" in link["href"]:
                    liga_data["Liga_ID"] = link["href"].split("liga_id=")[-1]
                    break

            data_list.append(liga_data)

        return pd.DataFrame(data_list)

    def _parse_game_details(self, html: str, spielplan_id: str, liga_id: str) -> Optional[Dict]:
        """Parse HTML response for game details."""
        soup = BeautifulSoup(html, "html.parser")
        game_details = {}

        # Parse basic game information
        ergebnisliste_form = soup.find("form", {"name": "ergebnisliste"})
        if ergebnisliste_form:
            rows = ergebnisliste_form.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = row.find_all("td")
                if len(cells) >= 6:
                    try:
                        game_details = {
                            "Date": cells[2].get_text(strip=True),
                            "Home Team": cells[3].get_text(strip=True),
                            "Away Team": cells[4].get_text(strip=True),
                            "Home Score": cells[5].get_text(strip=True).split(" : ")[0],
                            "Away Score": cells[5].get_text(strip=True).split(" : ")[1]
                        }
                    except (IndexError, ValueError) as e:
                        logger.warning(f"Error parsing game details row: {e}")
                        continue
                    break

        # Parse player information
        player_list = []
        player_stats_form = soup.find("form", {"name": "spielerstatistikgast"})
        if player_stats_form:
            rows = player_stats_form.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = row.find_all("td")
                if len(cells) >= 2:
                    lastname = cells[0].get_text(strip=True)
                    firstname = cells[1].get_text(strip=True)
                    
                    if lastname and firstname and lastname != "Nachname" and firstname != "Vorname":
                        player = {
                            "Nachname": lastname,
                            "Vorname": firstname,
                            "is_masked": "*" in lastname
                        }
                        player_list.append(player)

        # Combine all information
        if game_details:
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

        return None