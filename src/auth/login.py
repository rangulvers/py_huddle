# src/auth/login.py
import requests
from typing import Tuple, Optional
from loguru import logger
from dataclasses import dataclass
import streamlit as st

@dataclass
class LoginCredentials:
    username: str
    password: str

class BBAuthenticator:
    """Handle authentication with basketball-bund.net."""
    
    BASE_URL = "https://www.basketball-bund.net"
    LOGIN_URL = f"{BASE_URL}/login.do"
    
    def __init__(self):
        self.session = requests.Session()
        self.is_authenticated = False

    def login(self, credentials: LoginCredentials) -> Tuple[bool, Optional[str]]:
        """Attempt to login to basketball-bund.net."""
        try:
            # Prepare headers exactly as browser sends them
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "en-US,en;q=0.9,de;q=0.8,cs;q=0.7,lb;q=0.6",
                "cache-control": "max-age=0",
                "content-type": "application/x-www-form-urlencoded",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1"
            }

            # Prepare login data
            login_data = {
                "username": credentials.username,
                "password": credentials.password
            }

            logger.debug("Making POST request for login")
            
            response = self.session.post(
                f"{self.LOGIN_URL}?reqCode=login",
                data=login_data,
                headers=headers,
                allow_redirects=False,  # Don't follow redirects automatically
                timeout=10
            )

            # Log response details for debugging
            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            # Check for redirect to userinfos.do
            if response.status_code == 302 and '/userinfos.do?reqCode=view' in response.headers.get('location', ''):
                self.is_authenticated = True
                logger.info("Login successful - got correct redirect")
                return True, None
            else:
                logger.error(f"Login failed - unexpected response: {response.status_code}")
                return False, "Login fehlgeschlagen - Bitte überprüfen Sie Ihre Anmeldedaten"

        except requests.RequestException as e:
            logger.error(f"Login request failed: {e}")
            return False, f"Verbindungsfehler: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            return False, f"Unerwarteter Fehler: {str(e)}"

    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        return self.is_authenticated