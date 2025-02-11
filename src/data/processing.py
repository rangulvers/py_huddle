from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from datetime import datetime
from loguru import logger
from .models import Liga, Player, GameDetails

class DataProcessor:
    """Process and validate data for the application."""

    @staticmethod
    def validate_dataframe(df: pd.DataFrame, context: str) -> bool:
        """
        Validate DataFrame has required columns.

        Args:
            df: DataFrame to validate
            context: Context for validation ('spielerliste' or 'spieldaten')

        Returns:
            bool: True if valid
        """
        from src.config import REQUIRED_COLUMNS

        required_cols = REQUIRED_COLUMNS.get(context, [])
        return all(col in df.columns for col in required_cols)

    @staticmethod
    def create_liga(row: pd.Series) -> Liga:
        """Create Liga object from DataFrame row."""
        return Liga(
            liga_id=str(row.get('Liga_ID', '')),
            liganame=str(row.get('Liganame', '')),
            klasse=str(row.get('Klasse', '')),
            alter=str(row.get('Alter', '')),
            gender=str(row.get('m/w', '')),
            bezirk=str(row.get('Bezirk', '')),
            kreis=str(row.get('Kreis', ''))
        )

    @staticmethod
    def filter_relevant_games(
        df: pd.DataFrame,
        selected_liga_ids: List[str],
        club_name: str
    ) -> pd.DataFrame:
        """Filter games based on selected leagues and club name."""
        logger.debug(f"Filtering games with parameters:")
        logger.debug(f"Selected Liga IDs: {selected_liga_ids}")
        logger.debug(f"Club name: {club_name}")
        logger.debug(f"Input DataFrame shape: {df.shape}")

        # First filter: Liga_ID
        liga_filter = df["Liga_ID"].isin(selected_liga_ids)
        logger.debug(f"Games matching Liga_ID filter: {liga_filter.sum()}")

        # Second filter: Club name in Gast
        club_filter = df["Gast"].str.contains(club_name, na=False, case=False)
        logger.debug(f"Games matching club name filter: {club_filter.sum()}")

        # Combined filter
        filtered_df = df[liga_filter & club_filter]
        logger.debug(f"Final filtered DataFrame shape: {filtered_df.shape}")

        return filtered_df

    @staticmethod
    def build_birthday_lookup(df: pd.DataFrame) -> Dict[str, str]:
        """
        Build lookup dictionary for player birthdays with handling for middle names.

        Args:
            df: DataFrame with player information from Excel

        Returns:
            Dict mapping various name formats to birthday
        """
        birthday_lookup = {}

        for _, row in df.iterrows():
            try:
                lastname = str(row['Nachname']).strip()
                firstname = str(row['Vorname']).strip()

                if pd.notna(row.get('Geburtsdatum')):
                    try:
                        # Handle different date formats
                        date_str = str(row['Geburtsdatum'])
                        if isinstance(row['Geburtsdatum'], pd.Timestamp):
                            birthday = row['Geburtsdatum'].strftime('%d.%m.%Y')
                        else:
                            date_obj = pd.to_datetime(date_str)
                            birthday = date_obj.strftime('%d.%m.%Y')

                        # Store the basic version (as in Excel)
                        birthday_lookup[f"{lastname}, {firstname}"] = birthday

                        # Also store first name only version for matching against full names
                        firstname_parts = firstname.split()
                        if len(firstname_parts) > 0:
                            # Store version with just first part of first name
                            birthday_lookup[f"{lastname}, {firstname_parts[0]}"] = birthday

                        logger.debug(f"Added birthday for {lastname}, {firstname}")

                    except Exception as e:
                        logger.warning(f"Could not parse birthday for {lastname}, {firstname}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error processing row: {e}")
                continue

        return birthday_lookup



    @staticmethod
    def process_game_details(
        game_data: Dict[str, Any],
        hall_name: str,
        hall_address: Optional[str],
        distance: Optional[float]
    ) -> GameDetails:
        """Process raw game data into GameDetails object."""
        return GameDetails(
            spielplan_id=str(game_data.get('Spielplan_ID', '')),
            liga_id=str(game_data.get('Liga_ID', '')),
            date=str(game_data.get('Date', '')),
            home_team=str(game_data.get('Home Team', '')),
            away_team=str(game_data.get('Away Team', '')),
            home_score=str(game_data.get('Home Score', '')),
            away_score=str(game_data.get('Away Score', '')),
            players=[
                Player(
                    lastname=p['Nachname'],
                    firstname=p['Vorname'],
                    is_masked=p.get('is_masked', False)
                )
                for p in game_data.get('Players', [])
            ],
            hall_name=hall_name,
            hall_address=hall_address,
            distance=distance
        )

    @staticmethod
    def parse_date_only(date_str: str) -> str:
        """Extract date part from datetime string."""
        try:
            if isinstance(date_str, pd.Timestamp):
                return date_str.strftime('%d.%m.%Y')

            # Try different date formats
            for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).strftime('%d.%m.%Y')
                except ValueError:
                    continue

            # If all formats fail, try pandas
            return pd.to_datetime(date_str).strftime('%d.%m.%Y')
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return date_str
