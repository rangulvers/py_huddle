from typing import Tuple, Optional, Dict
import requests
from loguru import logger
import streamlit as st
from src.config import GOOGLE_MAPS_CONFIG
from requests.exceptions import RequestException
from time import sleep

class GoogleMapsAPIError(Exception):
    """Custom exception for Google Maps API errors."""
    pass

class GoogleMapsClient:
    """Client for interacting with Google Maps APIs."""

    def __init__(self):
        self.api_key = GOOGLE_MAPS_CONFIG["api_key"]
        self.base_url = "https://maps.googleapis.com/maps/api"
        self.debug = "debug_manager" in st.session_state
        self.max_retries = GOOGLE_MAPS_CONFIG.get("max_retries", 3)
        self.retry_delay = GOOGLE_MAPS_CONFIG.get("retry_delay", 1)

    def get_gym_location(
        self,
        team_name: str,
        hall_name: str
    ) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Get detailed location information for a gym.

        Args:
            team_name: Name of the team
            hall_name: Name of the hall
        """
        try:
            if not team_name:
                raise ValueError("Team name and hall name are required")

            # Create a simple, direct search query just like typing in Google Maps
            search_query = f"{hall_name} {team_name}"
            logger.debug(f"Searching for location with query: {search_query}")

            if self.debug:
                st.session_state.debug_manager.log_request(
                    url=f"{self.base_url}/place/textsearch/json",
                    method="GET",
                    params={
                        "query": search_query,
                        "region": "de",
                        "language": "de"
                        # Removed type restriction to match Google Maps behavior
                    }
                )

            # Try to find the place
            place_result = self._find_place(search_query)

            if place_result:
                logger.debug(f"Found place: {place_result.get('name', '')}")
                # Get detailed place information
                place_details = self._get_place_details(place_result['place_id'])

                if place_details:
                    logger.debug(f"Got place details: {place_details['formatted_address']}")
                    return (
                        place_details['formatted_address'],
                        {
                            'address': place_details['formatted_address'],
                            'place_id': place_details['place_id'],
                            'location': place_details['geometry']['location'],
                            'name': place_details.get('name', hall_name)
                        }
                    )

            logger.warning(f"Could not find place for: {search_query}")
            return None, None

        except ValueError as e:
            logger.error(f"Invalid input: {e}")
            raise
        except RequestException as e:
            logger.error(f"Network error: {e}")
            raise GoogleMapsAPIError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting gym location: {e}")
            raise GoogleMapsAPIError(f"Error getting gym location: {e}")

    def calculate_distance(
        self,
        origin_address: str,
        destination_address: str
    ) -> Optional[float]:
        """
        Calculate driving distance between two addresses.

        Args:
            origin_address: Starting address
            destination_address: Ending address

        Returns:
            Distance in kilometers or None if calculation fails

        Raises:
            GoogleMapsAPIError: If there's an error with the API
        """
        try:
            if not origin_address or not destination_address:
                raise ValueError("Both origin and destination addresses are required")

            if self.debug:
                st.session_state.debug_manager.log_request(
                    url=f"{self.base_url}/distancematrix/json",
                    method="GET",
                    params={
                        "origins": origin_address,
                        "destinations": destination_address,
                        "mode": "driving",
                        "region": "de"
                    }
                )

            for attempt in range(self.max_retries):
                try:
                    url = f"{self.base_url}/distancematrix/json"
                    params = {
                        "origins": origin_address,
                        "destinations": destination_address,
                        "mode": "driving",
                        "key": self.api_key
                    }

                    response = requests.get(url, params=params)

                    if self.debug:
                        st.session_state.debug_manager.log_response(
                            response,
                            "Distance Matrix Calculation"
                        )

                    response.raise_for_status()
                    data = response.json()

                    if data["status"] == "OVER_QUERY_LIMIT":
                        if attempt < self.max_retries - 1:
                            sleep(self.retry_delay * (attempt + 1))
                            continue
                        raise GoogleMapsAPIError("API quota exceeded")

                    if (data["status"] == "OK" and
                        data["rows"] and
                        data["rows"][0]["elements"] and
                        data["rows"][0]["elements"][0]["status"] == "OK"):

                        # Convert meters to kilometers
                        distance = data["rows"][0]["elements"][0]["distance"]["value"] / 1000
                        logger.debug(f"Calculated distance: {distance:.1f}km")
                        return distance

                    error_msg = f"Distance calculation failed: {data['status']}"
                    logger.warning(error_msg)
                    raise GoogleMapsAPIError(error_msg)

                except RequestException as e:
                    if attempt < self.max_retries - 1:
                        sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise GoogleMapsAPIError(f"Network error: {e}")

        except ValueError as e:
            logger.error(f"Invalid input: {e}")
            raise
        except GoogleMapsAPIError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error calculating distance: {e}")
            raise GoogleMapsAPIError(f"Error calculating distance: {e}")

    def _find_place(self, query: str) -> Optional[Dict]:
        """Find a place using the Places API Text Search."""
        try:
            if not query:
                raise ValueError("Search query is required")

            url = f"{self.base_url}/place/textsearch/json"
            params = {
                "query": query,
                "key": self.api_key,
                "region": "de",
                "language": "de"
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Log full response for debugging (be sure to redact the API key in production!)
            logger.debug(f"Google Places response for query '{query}': {data}")

            if data["status"] == "OK" and data["results"]:
                return data["results"][0]

            return None

        except Exception as e:
            logger.error(f"Error finding place for query {query}: {e}")
            raise

    def _get_place_details(self, place_id: str) -> Optional[Dict]:
        """Get detailed place information using the Places API Details."""
        try:
            if not place_id:
                raise ValueError("Place ID is required")

            url = f"{self.base_url}/place/details/json"
            params = {
                "place_id": place_id,
                "key": self.api_key,
                "fields": "formatted_address,geometry,name,place_id"
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data["status"] == "OK":
                return data["result"]

            return None

        except RequestException as e:
            logger.error(f"Network error getting place details: {e}")
            raise GoogleMapsAPIError(f"Network error getting place details: {e}")
        except Exception as e:
            logger.error(f"Error getting place details: {e}")
            raise GoogleMapsAPIError(f"Error getting place details: {e}")
