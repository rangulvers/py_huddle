from typing import List, Dict, Any
from dataclasses import dataclass
from src.data.models import PDFInfo

@dataclass
class PDFAnalysis:
    """Analysis results for generated PDFs."""
    total_pdfs: int
    total_players: int
    unknown_birthdays: int
    long_distances: int
    files_with_issues: List[str]
    recommendations: List[str]
    details: Dict[str, Any]

class PDFAnalyzer:
    """Analyze generated PDFs for potential issues and statistics."""

    def analyze_pdfs(self, pdf_infos: List[PDFInfo]) -> PDFAnalysis:
        """
        Analyze generated PDFs and provide summary.

        Args:
            pdf_infos: List of PDFInfo objects

        Returns:
            PDFAnalysis object with results
        """
        total_pdfs = len(pdf_infos)
        total_players = sum(len(info.players) for info in pdf_infos)
        unknown_birthdays = sum(
            1 for info in pdf_infos
            if info.has_unknown_birthdays
        )

        long_distances = sum(
            1 for info in pdf_infos
            if info.distance and info.distance > 200
        )

        files_with_issues = []
        recommendations = []

        # Check for PDFs with issues
        for info in pdf_infos:
            issues = []

            if info.has_unknown_birthdays:
                issues.append("Fehlende Geburtstage")

            if info.distance and info.distance > 200:
                issues.append(f"Lange Fahrstrecke ({info.distance:.1f}km)")

            if issues:
                files_with_issues.append(
                    f"{info.filepath}: {', '.join(issues)}"
                )

        # Generate recommendations
        if unknown_birthdays > 0:
            recommendations.append(
                "🎂 Bitte überprüfen Sie die Spielerliste auf fehlende Geburtstage"
            )

        if long_distances > 0:
            recommendations.append(
                "🚗 Einige Fahrten sind über 200km - prüfen Sie die Routen"
            )

        # Collect detailed statistics
        details = {
            "pdfs_by_liga": self._group_by_liga(pdf_infos),
            "pdfs_by_month": self._group_by_month(pdf_infos),
            "distance_stats": self._calculate_distance_stats(pdf_infos)
        }

        return PDFAnalysis(
            total_pdfs=total_pdfs,
            total_players=total_players,
            unknown_birthdays=unknown_birthdays,
            long_distances=long_distances,
            files_with_issues=files_with_issues,
            recommendations=recommendations,
            details=details
        )

    def _group_by_liga(self, pdf_infos: List[PDFInfo]) -> Dict[str, int]:
        """Group PDFs by Liga ID."""
        liga_counts = {}
        for info in pdf_infos:
            liga_counts[info.liga_id] = liga_counts.get(info.liga_id, 0) + 1
        return liga_counts

    def _group_by_month(self, pdf_infos: List[PDFInfo]) -> Dict[str, int]:
        """Group PDFs by month."""
        from datetime import datetime

        month_counts = {}
        for info in pdf_infos:
            try:
                date = datetime.strptime(info.date, '%d.%m.%Y')
                month_key = date.strftime('%Y-%m')
                month_counts[month_key] = month_counts.get(month_key, 0) + 1
            except ValueError:
                continue
        return month_counts

    def _calculate_distance_stats(self, pdf_infos: List[PDFInfo]) -> Dict[str, float]:
        """Calculate statistics about travel distances."""
        distances = [
            info.distance
            for info in pdf_infos
            if info.distance is not None
        ]

        if not distances:
            return {}

        return {
            "total_km": sum(distances),
            "avg_km": sum(distances) / len(distances),
            "max_km": max(distances),
            "min_km": min(distances)
        }
