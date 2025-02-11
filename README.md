
# Basketball Game Management System

A Python-based system for managing basketball game information and to generating travel expense reports for teams.

![image](https://github.com/user-attachments/assets/415d3fc3-7797-4303-a6a6-bb8d59ee6b3a)

## Features

### Game Management
- Scrape current game data from basketball-bund.net
- Generate travel expense PDFs for individual games
- Calculate distances to game venues using Google Maps API
- Handle player information and birthdays
- Support test mode for development

### Archive Features
- Access historical game data from basketball-bund.net
- Search for teams across multiple leagues and seasons
- Generate league-specific travel expense reports
- Export game schedules to Excel
- Calculate total travel distances for past seasons

### Technical Features
- Authentication handling for basketball-bund.net
- Google Maps API integration for location and distance calculations
- PDF generation from templates
- Excel data export and processing
- Comprehensive error handling and logging
- Streamlit-based user interface

## Installation

1. Clone the repository:
```bash
git clone [https://github.com/rangulvers/py_huddle](https://github.com/rangulvers/py_huddle)
cd [https://github.com/rangulvers/py_huddle](https://github.com/rangulvers/py_huddle)
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up configuration:
- Add your Google Maps API key
- Configure PDF template paths
- Set up logging preferences

## Usage

### Starting the Application
```bash
streamlit run main.py
```

### Current Game Mode
1. Enter game details
2. Select players
3. Generate travel expense PDF
4. Download generated document

### Archive Mode
1. Select season
2. Enter team name
3. View leagues and games
4. Generate travel expense reports for entire leagues

## Configuration

### Google Maps API
- Set your API key in config.yml
- Configure region and language preferences
- Set retry parameters for API calls

### PDF Generation
- Customize template paths
- Configure output directory
- Set maximum players per document

### Logging
- Configure log levels
- Set log file rotation
- Define log format and retention

## Error Handling

The system includes comprehensive error handling for:
- Network connectivity issues
- API rate limits
- Invalid location data
- PDF generation errors
- Data validation
- Authentication failures

## Development

### Test Mode
Enable test mode to:
- Limit API calls
- Use test data
- Generate sample PDFs
- Debug logging

### Debug Mode
- Detailed logging
- Performance metrics
- API call tracking
- Error tracing

## Dependencies

- Python 3.8+
- Streamlit
- Pandas
- Google Maps Python Client
- PDFrw
- Loguru
- BeautifulSoup4
- Requests

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
