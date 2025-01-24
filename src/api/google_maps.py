from typing import Tuple, Optional
import requests
from loguru import logger
import streamlit as st
from src.config import GOOGLE_MAPS_CONFIG

class GoogleMapsClient:
    """Client for interacting with Google Maps APIs."""
    
    def __init__(self):
        self.api_key = GOOGLE_MAPS_CONFIG["api_key"]
        self.base_url = "https://maps.googleapis.com/maps/api"

    def get_location_info(
        self, 
        team_name: str, 
        hall_name: str
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        Get location information and distance for a team's hall.
        
        Args:
            team_name: Name of the team
            hall_name: Name of the hall
            
        Returns:
            Tuple of (formatted_address, distance_in_km)
        """
        try:
            # Get coordinates for the hall
            search_query = f"{team_name} {hall_name}"
            coordinates = self._geocode_address(search_query)
            
            if not coordinates:
                logger.warning(f"Could not geocode address: {search_query}")
                return None, None

            # Get formatted address
            formatted_address = coordinates.get("formatted_address")
            
            # Calculate distance from home gym
            distance = self._calculate_distance(
                st.session_state.get('home_gym_address'),
                formatted_address
            )

            return formatted_address, distance

        except Exception as e:
            logger.error(f"Error getting location info: {e}")
            return None, None

    def _geocode_address(self, address: str) -> Optional[dict]:
        """
        Geocode an address using Google's Geocoding API.
        
        Args:
            address: Address to geocode
            
        Returns:
            Dictionary with location information
        """
        try:
            url = f"{self.base_url}/geocode/json"
            params = {
                "address": address,
                "key": self.api_key
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data["status"] == "OK" and data["results"]:
                return {
                    "lat": data["results"][0]["geometry"]["location"]["lat"],
                    "lng": data["results"][0]["geometry"]["location"]["lng"],
                    "formatted_address": data["results"][0]["formatted_address"]
                }
            
            logger.warning(f"Geocoding failed: {data['status']}")
            return None

        except Exception as e:
            logger.error(f"Error geocoding address: {e}")
            return None

    def _calculate_distance(
        self, 
        origin: str, 
        destination: str
    ) -> Optional[float]:
        """
        Calculate driving distance between two addresses.
        
        Args:
            origin: Starting address
            destination: Ending address
            
        Returns:
            Distance in kilometers
        """
        try:
            url = f"{self.base_url}/distancematrix/json"
            params = {
                "origins": origin,
                "destinations": destination,
                "mode": "driving",
                "key": self.api_key
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if (data["status"] == "OK" and 
                data["rows"] and 
                data["rows"][0]["elements"] and 
                data["rows"][0]["elements"][0]["status"] == "OK"):
                
                # Convert meters to kilometers
                return data["rows"][0]["elements"][0]["distance"]["value"] / 1000
            
            logger.warning(f"Distance calculation failed: {data['status']}")
            return None

        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            return None