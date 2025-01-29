# src/api/archive.py
from datetime import datetime
import os
import tempfile
from typing import Dict, List, Optional
from loguru import logger
from bs4 import BeautifulSoup
from dataclasses import dataclass
import time
import re

import pandas as pd

@dataclass
class ArchiveFilter:
    season_id: str
    team_name: str

class BasketballArchive:
    """Client for fetching archive data from basketball-bund.net."""
    
    BASE_URL = "https://www.basketball-bund.net"
    ARCHIVE_URL = f"{BASE_URL}/index.jsp"

    def __init__(self, authenticator):
        """Initialize with authenticated session."""
        if not authenticator.is_logged_in():
            raise ValueError("Authenticator must be logged in")
        self.session = authenticator.session
        logger.debug("Initialized archive client with authenticated session")

    def find_team_leagues(self, filter_params: ArchiveFilter) -> List[Dict]:
        """Find all leagues where the specified team plays and get their away games."""
        try:
            logger.info(f"Searching for team '{filter_params.team_name}' in season {filter_params.season_id}")
            
            # Get all leagues (across all pages)
            all_leagues = self._get_all_leagues(filter_params.season_id)
            logger.info(f"Found {len(all_leagues)} total leagues to search")

            # Search for team in each league and get away games
            matching_leagues = []
            for league in all_leagues:
                logger.debug(f"Checking league: {league['name']}")
                
                # Get teams for this league
                teams = self._get_league_teams(league['liga_id'], filter_params.season_id)
                
                # Check if our team is in this league
                team_found = False
                for team in teams:
                    if filter_params.team_name.lower() in team['name'].lower():
                        team_found = True
                        logger.info(f"Found team in league: {league['name']}")
                        
                        # Get away games for this league
                        away_games = self.get_away_games(league, filter_params.team_name)
                        
                        matching_leagues.append({
                            **league,
                            'teams': teams,
                            'found_team': team,
                            'away_games': away_games
                        })
                        break
                
                if not team_found:
                    logger.debug(f"Team not found in league: {league['name']}")
                
                time.sleep(0.5)  # Prevent rate limiting

            logger.info(f"Found team in {len(matching_leagues)} leagues")
            return matching_leagues

        except Exception as e:
            logger.error(f"Error searching for team: {e}")
            raise

    def _get_all_leagues(self, season_id: str) -> List[Dict]:
        """Get all leagues from all pages."""
        all_leagues = []
        page = 1
        start_row = 0
        
        while True:
            logger.debug(f"Fetching league page {page} (startrow={start_row}) for season {season_id}")
            
            # Get leagues from current page
            leagues, next_start_row = self._get_leagues_page(season_id, start_row)
            all_leagues.extend(leagues)
            
            if next_start_row is None:
                logger.debug("No more pages to fetch")
                break
                
            start_row = next_start_row
            page += 1
            
            # Small delay between pages
            time.sleep(0.5)

        logger.info(f"Found total of {len(all_leagues)} leagues across {page} pages")
        return all_leagues

    def _get_leagues_page(self, season_id: str, start_row: int) -> tuple[List[Dict], Optional[int]]:
        """Get leagues from a specific page."""
        try:
            # Prepare request data
            data = {
                "saison_id": season_id,
                "cbBezirkFilter": "28",  # Darmstadt
                "cbSpielklasseFilter": "0",
                "cbAltersklasseFilter": "-2",
                "cbGeschlechtFilter": "0",
                "cbKreisFilter": "0",
                "startrow": str(start_row)
            }

            # Make request
            response = self.session.post(
                f"{self.ARCHIVE_URL}?Action=106",
                data=data,
                headers=self._get_headers()
            )
            response.raise_for_status()

            # Parse the response
            soup = BeautifulSoup(response.text, 'html.parser')
            leagues = []

            # Find the main league table (the one with class="sportView" that contains the league data)
            league_tables = soup.find_all('table', class_='sportView')
            main_table = None
            for table in league_tables:
                if table.find('td', string=lambda x: x and 'Spielkl.' in str(x)):
                    main_table = table
                    break

            if not main_table:
                logger.error("Could not find main league table")
                return [], None

            # Find rows that contain cells with sportItemEven or sportItemOdd classes
            for row in main_table.find_all('tr'):
                cells = row.find_all('td', class_=['sportItemEven', 'sportItemOdd'])
                if cells and len(cells) >= 7:  # We need at least 7 columns
                    # Get links from action column
                    action_cell = cells[6]
                    links = action_cell.find_all('a')
                    liga_id = None
                    table_link = None
                    schedule_link = None
                    
                    for link in links:
                        href = link.get('href', '')
                        if 'Action=107' in href:  # Table link
                            liga_id_match = re.search(r'liga_id=(\d+)', href)
                            if liga_id_match:
                                liga_id = liga_id_match.group(1)
                                table_link = href
                        elif 'Action=108' in href:  # Schedule link
                            schedule_link = href

                    if liga_id:
                        league_info = {
                            'liga_id': liga_id,
                            'season_id': season_id,  # Add this line
                            'spielklasse': cells[0].text.strip(),
                            'altersklasse': cells[1].text.strip(),
                            'bereich': cells[2].text.strip(),
                            'bezirk': cells[3].text.strip(),
                            'kreis': cells[4].text.strip(),
                            'name': cells[5].text.strip(),
                            'table_link': f"{self.BASE_URL}/{table_link}" if table_link else None,
                            'schedule_link': f"{self.BASE_URL}/{schedule_link}" if schedule_link else None
                        }
                        leagues.append(league_info)
                        logger.debug(f"Added league: {league_info['name']} (ID: {liga_id})")

            logger.debug(f"Found {len(leagues)} leagues on current page")

            # Check for next page in pagination
            pagination = soup.find('td', class_='sportViewNavigationLinkPageNumber')
            if pagination:
                next_links = pagination.find_all('a', class_='sportViewNavigationLink')
                for link in next_links:
                    href = link.get('href', '')
                    if 'startrow=' in href:
                        row_match = re.search(r'startrow=(\d+)', href)
                        if row_match:
                            row_num = int(row_match.group(1))
                            if row_num > start_row:
                                return leagues, row_num

            return leagues, None

        except Exception as e:
            logger.error(f"Error getting leagues page: {e}")
            return [], None
    def _get_league_teams(self, liga_id: str, season_id: str) -> List[Dict]:
        """Get all teams from a league's table page."""
        try:
            url = f"{self.ARCHIVE_URL}?Action=107&liga_id={liga_id}&saison_id={season_id}"
            
            response = self.session.get(
                url,
                headers=self._get_headers()
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            teams = []

            # Find the main table (class="sportView" with "Rang" and "Name" headers)
            tables = soup.find_all('table', class_='sportView')
            main_table = None
            for table in tables:
                if table.find('td', class_='sportViewHeader', string=lambda x: x and 'Rang' in x):
                    main_table = table
                    break

            if not main_table:
                logger.error(f"Could not find team table for league {liga_id}")
                return []

            # Find team rows (both even and odd)
            rows = main_table.find_all('tr')
            for row in rows:
                cells = row.find_all('td', class_=['sportItemEven', 'sportItemOdd'])
                if cells and len(cells) >= 2:  # Need at least rank and name
                    # Check if the team is not struck through (removed from league)
                    strike_tag = cells[1].find('strike')
                    if not strike_tag:
                        team_info = {
                            'rank': cells[0].text.strip(),
                            'name': cells[1].text.strip(),
                            'games': cells[3].text.strip() if len(cells) > 3 else '',
                            'points': cells[4].text.strip() if len(cells) > 4 else ''
                        }
                        logger.debug(f"Found team: {team_info['name']} (Rank: {team_info['rank']})")
                        teams.append(team_info)

            logger.debug(f"Found {len(teams)} teams in league {liga_id}")
            return teams

        except Exception as e:
            logger.error(f"Error getting teams for league {liga_id}: {e}")
            return []
        
    def get_away_games(self, league_info: Dict, team_name: str) -> List[Dict]:
        """Get all away games for a team from a league's schedule using Excel export."""
        try:
            logger.debug(f"Getting away games for {team_name} in league {league_info['name']}")
            
            export_url = f"{self.BASE_URL}/servlet/sport.dbb.export.ExcelExportErgebnissePublic"
            params = {
                'liga_id': league_info['liga_id'],
                'saison_id': league_info['season_id'],
                'sessionkey': 'sport.dbb.liga.archiv.ArchivErgebnisseView/index.jsp_'
            }

            logger.debug(f"Downloading Excel from: {export_url}")

            response = self.session.get(
                export_url,
                params=params,
                headers=self._get_headers()
            )
            response.raise_for_status()

            # Save to temporary file and read with pandas
            with tempfile.NamedTemporaryFile(suffix='.xls', delete=False) as temp_file:
                temp_file.write(response.content)
                temp_file.flush()
                
                # Read Excel file with the exact column names from the format
                df = pd.read_excel(
                    temp_file.name,
                    names=[
                        'Spieltag',
                        'Spielnummer',
                        'Datum',
                        'Heimmannschaft',
                        'Gastmannschaft',
                        'Endstand'
                    ]
                )
                logger.debug(f"Loaded Excel with {len(df)} rows")
                
            # Clean up temp file
            os.unlink(temp_file.name)

            # Process the DataFrame to find away games
            games = []
            for _, row in df.iterrows():
                try:
                    # Skip rows that don't have proper data or are marked with *
                    if (pd.isna(row['Spieltag']) or 
                        pd.isna(row['Spielnummer']) or 
                        str(row['Spieltag']).endswith('*')):
                        continue
                    
                    # Clean up the team names (remove asterisks and whitespace)
                    home_team = str(row['Heimmannschaft']).strip().rstrip('*')
                    away_team = str(row['Gastmannschaft']).strip().rstrip('*')
                    
                    # Check if this is an away game for our team
                    if team_name.lower() in away_team.lower():
                        # Parse the date and time (format: DD.MM.YYYY HH:MM)
                        date_str = str(row['Datum']).strip()
                        
                        # Clean up the score (remove any whitespace)
                        score = str(row['Endstand']).strip() if pd.notna(row['Endstand']) else ''
                        
                        game_info = {
                            'spieltag': str(int(float(str(row['Spieltag']).split('*')[0]))),  # Handle potential decimals and asterisks
                            'nummer': str(int(float(str(row['Spielnummer']).split('*')[0]))),  # Handle potential decimals and asterisks
                            'datum': date_str,
                            'home_team': home_team,
                            'away_team': away_team,
                            'score': score
                        }
                        games.append(game_info)
                        logger.debug(f"Found away game: {game_info}")
                except Exception as e:
                    logger.error(f"Error processing row: {e}")
                    logger.error(f"Row content: {row.to_dict()}")
                    continue

            # Sort games by date
            games.sort(key=lambda x: datetime.strptime(x['datum'], '%d.%m.%Y %H:%M'))
            
            logger.info(f"Found {len(games)} away games for {team_name}")
            return games

        except Exception as e:
            logger.error(f"Error getting away games from Excel: {e}")
            if 'response' in locals():
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response content: {response.content[:200]}")
            return []
    def _get_schedule_page(
        self, 
        liga_id: str, 
        season_id: str, 
        start_row: int,
        team_name: str
    ) -> tuple[List[Dict], Optional[int]]:
        """Get games from a specific page of the schedule."""
        try:
            url = f"{self.ARCHIVE_URL}?Action=108&liga_id={liga_id}&saison_id={season_id}&defaultview=1"
            if start_row > 0:
                url += f"&startrow={start_row}"

            logger.debug(f"Fetching schedule page: {url}")
            response = self.session.get(
                url,
                headers=self._get_headers()
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            games = []

            # Find the main game table (the one with the actual games)
            tables = soup.find_all('table', class_='sportView')
            main_table = None
            for table in tables:
                # Look for table with game data (has columns for SpTag, Nr., Datum, etc.)
                if table.find('td', string=lambda x: x and 'Datum' in str(x)):
                    main_table = table
                    break

            if not main_table:
                logger.error("Could not find game table")
                return [], None

            # Track game numbers to prevent duplicates
            seen_game_numbers = set()

            # Process game rows
            rows = main_table.find_all('tr')
            for row in rows:
                cells = row.find_all('td', class_=['sportItemEven', 'sportItemOdd'])
                if cells and len(cells) >= 6:  # Need SpTag, Nr, Datum, Heim, Gast, Endstand
                    # Skip rows that are struck through (cancelled games)
                    if not cells[0].find('strike'):
                        # Get game number for deduplication
                        game_number = cells[1].text.strip()
                        
                        # Skip if we've already seen this game
                        if game_number in seen_game_numbers:
                            continue
                            
                        home_team = cells[3].text.strip()
                        away_team = cells[4].text.strip()
                        
                        # Check if this is an away game for our team
                        if team_name.lower() in away_team.lower():
                            game_info = {
                                'spieltag': cells[0].text.strip(),
                                'nummer': game_number,
                                'datum': cells[2].text.strip(),
                                'home_team': home_team,
                                'away_team': away_team,
                                'score': cells[5].text.strip() if len(cells) > 5 else ''
                            }
                            games.append(game_info)
                            seen_game_numbers.add(game_number)
                            logger.debug(f"Found away game: {game_info}")

            logger.debug(f"Found {len(games)} away games on this page")

            # Check for pagination
            next_start_row = None
            pagination = soup.find('td', class_='sportViewNavigationLinkPageNumber')
            if pagination:
                next_links = pagination.find_all('a', class_='sportViewNavigationLink')
                current_row = start_row
                for link in next_links:
                    href = link.get('href', '')
                    if 'startrow=' in href:
                        row_match = re.search(r'startrow=(\d+)', href)
                        if row_match:
                            row_num = int(row_match.group(1))
                            if row_num > current_row:
                                next_start_row = row_num
                                break

            return games, next_start_row

        except Exception as e:
            logger.error(f"Error getting schedule page: {e}")
            return [], None
    
    def _get_headers(self) -> Dict:
            """Get common headers for requests."""
            return {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9,de;q=0.8",
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