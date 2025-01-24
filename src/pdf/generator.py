import os
from typing import Dict, Optional, List
from datetime import datetime
from pdfrw import PdfReader, PdfWriter, PdfDict
from loguru import logger
from src.config import PDF_CONFIG, PDF_FIELD_MAPPINGS
from src.data.models import PDFInfo, Liga

class PDFGenerator:
    """Generate PDF documents from template."""

    def __init__(self):
        """Initialize PDF generator with template path."""
        self.template_path = PDF_CONFIG["template_path"]
        self.output_dir = PDF_CONFIG["output_dir"]
        self.max_players = PDF_CONFIG["max_players"]

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
            filename = f"{liga_id}_{date}.pdf"
            filepath = os.path.join(self.output_dir, filename)
            
            # Read template
            template = PdfReader(self.template_path)
            
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

            # Get the location information
            location = f"{home_team} - {home_hall}" if home_team and home_hall else "Unknown"
            data["(Name oder SpielortRow1)"] = location

            if game_details.get('distance'):
                data["(km  Hin und Rückfahrt Row1)"] = f"{game_details['distance']:.1f}"

            logger.debug("Added game information to row 1")
            logger.debug(f"Date: {date}")
            logger.debug(f"Away game location: {data['(Name oder SpielortRow1)']}")
            logger.debug(f"Travel distance: {data.get('(km  Hin und Rückfahrt Row1)', 'Not set')}")

            # Process players starting from row 2
            players = game_details.get('Players', [])
            logger.debug(f"Processing {len(players)} players")
            has_unknown_birthdays = False
            
            # Maximum 5 players, using rows 2-6
            for idx, player in enumerate(players[:5], start=2):  # Start from row 2
                try:
                    if player.get('is_masked', False):
                        name_text = "Geblocked durch DSGVO"
                        birthday_text = ""
                    else:
                        name = f"{player['Nachname']}, {player['Vorname']}"
                        birthday = birthday_lookup.get(name, "")
                        if not birthday:
                            has_unknown_birthdays = True
                            logger.warning(f"No birthday found for player: {name}")
                        
                        name_text = name
                        birthday_text = birthday
                    
                    # Add name to Name oder Spielort field
                    data[f"(Name oder SpielortRow{idx})"] = name_text
                    # Add birthday to Einzelteilngeb field
                    data[f"(EinzelteilngebRow{idx})"] = birthday_text
                    
                    logger.debug(f"Added to row {idx}:")
                    logger.debug(f"  Name: {name_text}")
                    logger.debug(f"  Birthday: {birthday_text}")
                    
                except Exception as e:
                    logger.error(f"Error processing player for row {idx}: {e}")
                    continue

            logger.debug("Prepared form data:")
            for key, value in data.items():
                logger.debug(f"Field: {key} = {value}")

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

            # Verify file was created and has content
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.debug(f"Successfully created PDF: {filepath} ({os.path.getsize(filepath)} bytes)")
            else:
                logger.error(f"PDF file is empty or not created: {filepath}")

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
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            return None