from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class Player:
    """Player information."""
    lastname: str
    firstname: str
    is_masked: bool = False
    birthday: Optional[str] = None

@dataclass
class Liga:
    """League information."""
    liga_id: str
    liganame: str
    klasse: str
    alter: str
    gender: str
    bezirk: str
    kreis: str
    display_name: Optional[str] = None

    def __post_init__(self):
        """Set display name after initialization."""
        self.display_name = f"{self.liganame} ({self.klasse} {self.alter} {self.gender})"

@dataclass
class GameDetails:
    """Game details including players."""
    spielplan_id: str
    liga_id: str
    date: str
    home_team: str
    away_team: str
    home_score: str
    away_score: str
    players: List[Player]
    hall_name: Optional[str] = None
    hall_address: Optional[str] = None
    distance: Optional[float] = None

@dataclass
class PDFInfo:
    """Information about generated PDF."""
    filepath: str
    liga_id: str
    date: str
    team: str
    players: List[Player]
    distance: Optional[float] = None
    has_unknown_birthdays: bool = False
