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
        """
        Generate PDF for a game.
        
        Args:
            game_details: Dictionary with game details
            liga_info: Liga information
            club_name: Name of the club
            event_type: Type of event
            birthday_lookup: Dictionary mapping player names to birthdays
            
        Returns:
            PDFInfo object if successful, None otherwise
        """
        try:
            # Prepare data for PDF
            date = game_details.get('date', 'Unknown')
            liga_id = game_details.get('liga_id', 'Unknown')
            
            # Create filename
            filename = f"{liga_id}_{date}.pdf"
            filepath = os.path.join(self.output_dir, filename)

            # Read template
            template = PdfReader(self.template_path)
            
            # Prepare form fields
            data = {
                PDF_FIELD_MAPPINGS["club_name"]: club_name,
                PDF_FIELD_MAPPINGS["event_type"]: event_type,
                PDF_FIELD_MAPPINGS["department"]: "Basketball",
                PDF_FIELD_MAPPINGS["team"]: f"{liga_info.liganame}",
                PDF_FIELD_MAPPINGS["date"]: date,
                PDF_FIELD_MAPPINGS["location"]: (
                    game_details.get('hall_address') or 
                    game_details.get('hall_name', 'Unknown')
                )
            }

            # Add distance if available
            if game_details.get('distance'):
                data[PDF_FIELD_MAPPINGS["distance"]] = f"{game_details['distance']:.1f}"

            # Process players
            players = game_details.get('players', [])
            has_unknown_birthdays = False
            
            # Ensure exactly 5 players
            player_count = 0
            for idx in range(self.max_players):
                field_key = f"player{idx + 1}"
                
                if player_count < len(players):
                    player = players[player_count]
                    if player.get('is_masked', False):
                        player_text = "Geblocked durch DSGVO"
                    else:
                        name = f"{player['lastname']}, {player['firstname']}"
                        birthday = birthday_lookup.get(name, "")
                        if not birthday:
                            has_unknown_birthdays = True
                        player_text = f"{name} {birthday}"
                    
                    data[PDF_FIELD_MAPPINGS[field_key]] = player_text
                    player_count += 1
                else:
                    data[PDF_FIELD_MAPPINGS[field_key]] = ""

            # Fill form fields
            for page in template.pages:
                if page.Annots:
                    for annotation in page.Annots:
                        if annotation.T and annotation.T in data:
                            annotation.update(PdfDict(V=data[annotation.T]))

            # Save PDF
            PdfWriter().write(filepath, template)

            return PDFInfo(
                filepath=filepath,
                liga_id=liga_id,
                date=date,
                team=liga_info.liganame,
                players=players[:self.max_players],
                distance=game_details.get('distance'),
                has_unknown_birthdays=has_unknown_birthdays
            )

        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            return None