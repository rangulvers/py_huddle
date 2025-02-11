from math import ceil
import os
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from pdfrw import PdfReader, PdfWriter, PdfDict
from loguru import logger
from src.config import PDF_CONFIG, PDF_FIELD_MAPPINGS
from src.data.models import PDFInfo, Liga
from src.api.google_maps import GoogleMapsClient


class PDFGenerator:
    """Generate PDF documents from template."""

    def __init__(self):
        """Initialize PDF generator with template path."""
        self.template_path = PDF_CONFIG["template_path"]
        self.output_dir = PDF_CONFIG["output_dir"]
        self.max_players = PDF_CONFIG["max_players"]
        self.google_maps_client = GoogleMapsClient()  # Add this line

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    def generate_pdf(
        self,
        game_details: Dict,
        liga_info: Liga,
        club_name: str,
        event_type: str,
        birthday_lookup: Dict[str, str]
    ) -> Optional[PDFInfo]:
        """Generate PDF for a game."""
        try:
            logger.debug(f"Starting PDF generation for game: {game_details.get('Spielplan_ID', 'Unknown')}")

            # Extract date and liga_id
            date = game_details.get('Date', 'Unknown')
            liga_id = liga_info.liga_id if liga_info else 'Unknown'

            # Create filename
            filename = f"{liga_id}_{date}_{liga_info.liganame}.pdf"
            filepath = os.path.join(self.output_dir, filename)

            # Read template
            template = PdfReader(self.template_path)


            logger.debug(liga_info)
            # Basic form fields
            data = {
                "(Verein)": club_name,
                "(Art der Veranstaltung)": event_type,
                "(Abteilung)": "Basketball",
                "(Mannschaften)": f"{liga_info.liganame}"
            }

            # Row 1: Game information
            data["(DatumRow1)"] = date

            # Get the home team's location since we're traveling there
            home_team = game_details.get('Home Team', '')
            home_hall = game_details.get('hall_name', 'Unknown')
            logger.debug(f"Processing away game at {home_team}'s venue")
            logger.debug(f"Home team: {home_team}")
            logger.debug(f"Home hall: {home_hall}")

            try:
                # Try to get location information using Google Maps
                formatted_address, location_details = self.google_maps_client.get_gym_location(
                    home_team,
                    home_hall
                )

                if formatted_address:
                    try:
                        # Calculate distance from our home gym
                        home_gym_address = PDF_CONFIG.get("home_gym_address")
                        distance = self.google_maps_client.calculate_distance(
                            home_gym_address,
                            formatted_address
                        )

                        data["(Name oder SpielortRow1)"] = formatted_address
                        if distance is not None:
                            round_trip_distance = ceil(distance * 2)
                            # data["(km  Hin und Rückfahrt Row1)"] = f"{round_trip_distance}"
                            data["(Summe km)"] = f"{round_trip_distance * 5}"
                            logger.debug(f"Set round-trip distance: {round_trip_distance} km")
                    except Exception as e:
                        logger.error(f"Error calculating distance: {e}")
                        data["(Name oder SpielortRow1)"] = formatted_address
                else:
                    # Fallback: Use basic location information
                    logger.warning(f"Using fallback location for {home_team} - {home_hall}")
                    data["(Name oder SpielortRow1)"] = f"{home_team} - {home_hall}"

            except Exception as e:
                logger.error(f"Error with location lookup: {e}")
                # Fallback: Use basic location information
                data["(Name oder SpielortRow1)"] = f"{home_team} - {home_hall}"

            logger.debug("Added game information to row 1")
            logger.debug(f"Date: {date}")
            logger.debug(f"Location: {data['(Name oder SpielortRow1)']}")

            # Process players starting from row 2
            players = game_details.get('Players', [])
            logger.debug(f"Processing {len(players)} players")
            has_unknown_birthdays = False

            # Maximum 5 players, using rows 2-6
            for idx, player in enumerate(players[:5], start=2):
                try:
                    if player.get('is_masked', False):
                        name_text = "Geblocked durch DSGVO"
                        birthday_text = ""
                    else:
                        name = f"{player['Nachname']}, {player['Vorname']}"
                        birthday_text, found = self._lookup_birthday(player, birthday_lookup)  # Use the new method
                        if not found:
                            has_unknown_birthdays = True

                        name_text = name

                    # Add name to Name oder Spielort field
                    data[f"(Name oder SpielortRow{idx})"] = name_text + "  " # stupid hack to prevent text clipping
                    # Add birthday to Einzelteilngeb field
                    data[f"(EinzelteilngebRow{idx})"] = birthday_text + "    " # stupid hack to prevent text clipping
                    data[f"(km  Hin und Rückfahrt Row{idx})"] = f"{round_trip_distance}"

                    logger.debug(f"Added to row {idx}:")
                    logger.debug(f"  Name: {name_text}")
                    logger.debug(f"  Birthday: {birthday_text}")
                    logger.debug(f"  Distance: {round_trip_distance}")

                except Exception as e:
                    logger.error(f"Error processing player for row {idx}: {e}")
                    continue

            # Fill form fields
            field_update_count = 0
            for page in template.pages:
                if page.Annots:
                    for annotation in page.Annots:
                        if annotation.T:
                            field_name = str(annotation.T)
                            if field_name in data:
                                value = data[field_name]
                                annotation.update(
                                    PdfDict(
                                        V=value,
                                        AP=None,
                                        AS=None,
                                        DV=value
                                    )
                                )
                                field_update_count += 1
                                logger.debug(f"Updated field {field_name} with value: {value}")

            logger.debug(f"Updated {field_update_count} fields in the PDF")

            # Save PDF
            writer = PdfWriter()
            writer.write(filepath, template)
            logger.debug(f"Saved PDF to: {filepath}")

            return PDFInfo(
                filepath=filepath,
                liga_id=liga_id,
                date=date,
                team=liga_info.liganame,
                players=players[:5],
                distance=game_details.get('distance'),
                has_unknown_birthdays=has_unknown_birthdays
            )

        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            return None

    def generate_archive_pdf(
        self,
        league_info: Dict,
        away_games: List[Dict],
        event_type: str,
        club_name: str
    ) -> Optional[PDFInfo]:
        """Generate PDF for archive games in a league."""
        try:
            logger.debug(f"Starting archive PDF generation for league: {league_info['name']}")

            # Create filename
            filename = f"archive_{league_info['liga_id']}_{league_info['season_id']}_{league_info['name']}.pdf"
            filepath = os.path.join(self.output_dir, filename)

            # Read template
            template = PdfReader(self.template_path)

            if league_info['bereich'] == "männlich":
                league_info['gender_short'] = "M"
            elif league_info['bereich'] == "weiblich":
                league_info['gender_short']  = "W"

            logger.debug(league_info)

            # Basic form fields
            data = {
                "(Verein)": club_name,
                "(Art der Veranstaltung)": event_type,
                "(Abteilung)": "Basketball",
                "(Mannschaften)": f"{league_info['gender_short']}{league_info['name']} {league_info['season_id']}/{int(league_info['season_id'])+1}"
            }

            total_distance = 0
            games_processed = 0

            # Process up to 5 away games (template limitation)
            for idx, game in enumerate(away_games, start=1):
                try:
                    # Get location and distance for the home team's venue
                    home_team = game['home_team']
                    logger.debug(f"Processing away game at {home_team}")

                    try:
                        # Try to get location information using Google Maps
                        formatted_address, location_details = self.google_maps_client.get_gym_location(
                            home_team,
                            ""  # No specific hall name from archive
                        )

                        if formatted_address:
                            try:
                                # SKIP FOR ARCHIVE AS DATA IS NOT AVAILABLE
                                # # Calculate distance from our home gym
                                home_gym_address = PDF_CONFIG.get("home_gym_address")
                                distance = self.google_maps_client.calculate_distance(
                                    home_gym_address,
                                    formatted_address
                                )

                                data[f"(Name oder SpielortRow{idx})"] = f" {formatted_address} ({home_team}) "
                                logger.debug(f"Set location: {formatted_address}")
                                if distance is not None:
                                    round_trip_distance = ceil(distance * 2) * 5 # 5 players
                                    data[f"(km  Hin und Rückfahrt Row{idx})"] = f"{round_trip_distance}"
                                    total_distance += round_trip_distance
                                    logger.debug(f"Set round-trip distance: {round_trip_distance} km")
                            except Exception as e:
                                logger.error(f"Error calculating distance: {e}")
                                data[f"(Name oder SpielortRow{idx})"] = formatted_address
                        else:
                            # Fallback: Use basic location information
                            logger.warning(f"Using fallback location for {home_team}")
                            data[f"(Name oder SpielortRow{idx})"] = home_team

                    except Exception as e:
                        logger.error(f"Error with location lookup: {e}")
                        data[f"(Name oder SpielortRow{idx})"] = home_team

                    # Add game date
                    data[f"(DatumRow{idx})"] = game['datum']

                    games_processed += 1
                    logger.debug(f"Added game {idx}: {home_team} on {game['datum']}")

                except Exception as e:
                    logger.error(f"Error processing game for row {idx}: {e}")
                    continue

            # Add total distance
            if total_distance > 0:
                data["(Summe km)"] = f"{total_distance}"

            # Fill form fields
            field_update_count = 0
            for page in template.pages:
                if page.Annots:
                    for annotation in page.Annots:
                        if annotation.T:
                            field_name = str(annotation.T)
                            if field_name in data:
                                value = data[field_name]
                                annotation.update(
                                    PdfDict(
                                        V=value,
                                        AP=None,
                                        AS=None,
                                        DV=value
                                    )
                                )
                                field_update_count += 1
                                logger.debug(f"Updated field {field_name} with value: {value}")

            logger.debug(f"Updated {field_update_count} fields in the PDF")

            # Save PDF
            writer = PdfWriter()
            writer.write(filepath, template)
            logger.debug(f"Saved PDF to: {filepath}")

            return PDFInfo(
                filepath=filepath,
                liga_id=league_info['liga_id'],
                date=league_info['season_id'],
                team=league_info['name'],
                players=[],  # No players in archive PDFs
                distance=total_distance,
                has_unknown_birthdays=False
            )

        except Exception as e:
            logger.error(f"Error generating archive PDF: {e}")
            return None

    def _lookup_birthday(self, player: Dict, birthday_lookup: Dict[str, str]) -> Tuple[str, bool]:
        """
        Look up birthday for a player, handling middle names and case inconsistencies.

        Args:
            player: Player dictionary with name information.
            birthday_lookup: Birthday lookup dictionary mapping "lastname, firstname" to birthday.

        Returns:
            Tuple of (birthday string, success boolean).
        """
        # Normalize helper function
        def normalize(name: str) -> str:
            return " ".join(name.strip().split()).lower()

        # Normalize player's names
        lastname = normalize(player.get('Nachname', ''))
        full_firstname = normalize(player.get('Vorname', ''))
        normalized_full_key = f"{lastname}, {full_firstname}"

        # Pre-normalize all keys from birthday_lookup for consistent comparisons.
        normalized_lookup = {normalize(key): value for key, value in birthday_lookup.items()}

        # 1. Try exact match first
        if normalized_full_key in normalized_lookup:
            logger.debug(f"Found exact birthday match for {normalized_full_key}")
            return normalized_lookup[normalized_full_key], True

        # 2. Try with just the first part of the first name
        if full_firstname:
            first_part = full_firstname.split()[0]
            normalized_first_key = f"{lastname}, {first_part}"
            if normalized_first_key in normalized_lookup:
                logger.debug(f"Found birthday match using first name only: {normalized_first_key}")
                return normalized_lookup[normalized_first_key], True

        # 3. Fallback: try to match if all parts of the player's first name appear
        #    in any lookup key for this lastname.
        for key, birthday in normalized_lookup.items():
            # Check that the key starts with the lastname and a comma.
            if not key.startswith(f"{lastname},"):
                continue
            # Extract the first part of the key (after the comma)
            try:
                _, key_firstname = key.split(",", 1)
            except ValueError:
                continue
            key_firstname = key_firstname.strip()
            # If all parts of the provided full first name are present in the key's first name, consider it a match.
            player_name_parts = full_firstname.split()
            if all(part in key_firstname for part in player_name_parts):
                logger.debug(f"Found birthday match with composite name: {key}")
                return birthday, True

        logger.warning(f"No birthday found for player: {lastname}, {full_firstname}")
        logger.debug(f"Available names in lookup: {list(birthday_lookup.keys())}")
        return "", False
