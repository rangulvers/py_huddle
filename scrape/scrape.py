import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.basketball-bund.net/index.jsp?Action=100&Verband=6"

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,de;q=0.8",
    "content-type": "application/x-www-form-urlencoded",
    "upgrade-insecure-requests": "1"
}

payload = (
    "search=TV+Heppenheim&cbSpielklasseFilter=0&spieltyp_id=0&cbAltersklasseFilter=0"
    "&cbGeschlechtFilter=0&cbBezirkFilter=0&cbKreisFilter=0"
)

response = requests.post(url, headers=headers, data=payload)
soup = BeautifulSoup(response.text, "html.parser")

form = soup.find("form", {"name": "ligaliste"})
tables = form.find_all("table", class_="sportView")

# Identify the table containing the required data
target_table = None
for t in tables:
    headers_in_table = t.find_all("td", class_="sportViewHeader")
    if headers_in_table:
        header_texts = [h.get_text(strip=True) for h in headers_in_table]
        if "Klasse" in header_texts and "Alter" in header_texts and "Liganame" in header_texts:
            target_table = t
            break

data_list = []
if target_table:
    rows = target_table.find_all("tr")
    for row in rows[1:]:  # Skip header row
        cells = row.find_all("td")
        if len(cells) >= 7:  # Ensure enough columns exist
            klasse = cells[0].get_text(strip=True)
            alter = cells[1].get_text(strip=True)
            geschlecht = cells[2].get_text(strip=True)
            bezirk = cells[3].get_text(strip=True)
            kreis = cells[4].get_text(strip=True)
            liganame = cells[5].get_text(strip=True)
            liganr = cells[6].get_text(strip=True)

            # Extract liga_id from the hyperlink
            liga_id = None
            links = cells[7].find_all("a", href=True)
            for link in links:
                if "Action=102" in link["href"]:  # Look for the table (Tabelle) link
                    liga_id = link["href"].split("liga_id=")[-1]
                    break

            data_list.append({
                "Klasse": klasse,
                "Alter": alter,
                "m/w": geschlecht,
                "Bezirk": bezirk,
                "Kreis": kreis,
                "Liganame": liganame,
                "Liganr": liganr,
                "Liga_ID": liga_id
            })

df = pd.DataFrame(data_list)
print(df)
