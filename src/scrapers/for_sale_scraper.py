"""
imoti.info Sofia apartment-rental scraper
-------------------------------------------
Scrapes for sale listings for Sofia from imoti.info and
saves them into a CSV file with automatic pagination, optimized delay intervals,
and dual-layer extraction (SSR JSON state + CSS selector fallbacks).
Retains original Bulgarian description without translation.
"""

import csv
import json
import re
import time
import random
import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime

# ----------------------------------------------------------------------
# SETTINGS
# ----------------------------------------------------------------------

SEARCH_BASE = "https://imoti.info/en/for-sale/grad-sofiya"
OUTPUT_FILE = r"D:\Data Analysis\Projects\Sofia Housing\files\scraped\sofia_for_sale_scraped.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

LISTING_LINK_RE = re.compile(r'href="(/en/properties/\d+-[^"]+)"')

# Order of columns
COLUMNS = [
    "url",
    "ad_id",
    "listing_type",
    "location",
    "price_eur",
    "area_sqm",
    "price_per_sqm_eur",
    "floor",
    "central_heating",
    "gas",
    "construction_type",      
    "construction_year",
    "description_bulgarian",
    "features",
    "views",
    "saves",
    "ad_published_date",
    "agency",
    "date_scraped",
]


# ----------------------------------------------------------------------
# STEP 1: Collect listing links from search result pages
# ----------------------------------------------------------------------

def get_listing_links(page_url):
    """Fetch a search results page and return full listing URLs."""
    response = requests.get(page_url, headers=HEADERS, timeout=15)
    if response.status_code == 404:
        return []
    response.raise_for_status()

    links = set()
    for match in LISTING_LINK_RE.finditer(response.text):
        links.add("https://imoti.info" + match.group(1))

    return list(links)


# ----------------------------------------------------------------------
# STEP 2: Extract all requested listing details
# ----------------------------------------------------------------------

def extract_ssr_state(soup):
    """Extract embedded Angular SSR state dictionary if available."""
    state_tag = soup.find("script", id="serverApp-state")
    if not state_tag or not state_tag.string:
        return None

    try:
        data = json.loads(state_tag.string)
        # Scan keys for the advert data dictionary
        for val in data.values():
            if isinstance(val, dict):
                if "advert" in val and isinstance(val["advert"], dict):
                    return val["advert"]
                if "b" in val and isinstance(val["b"], dict) and "advert" in val["b"]:
                    return val["b"]["advert"]
    except Exception:
        pass
    return None


def get_listing_details(url):
    """Fetch an individual listing page and extract all target columns."""
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    state = extract_ssr_state(soup) or {}

    data = {col: "N/A" for col in COLUMNS}
    data["url"] = url
    data["features"] = []
    data["date_scraped"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. ad_id
    if state.get("seo_id"):
        data["ad_id"] = str(state["seo_id"])
    else:
        id_match = re.search(r"/properties/(\d+)-", url)
        if id_match:
            data["ad_id"] = id_match.group(1)

    # 2. listing_type
    if state.get("pubtypetxt"):
        data["listing_type"] = str(state["pubtypetxt"]).strip()
    else:
        title_el = soup.select_one("h1")
        if title_el:
            data["listing_type"] = title_el.get_text(strip=True).split(" в ")[0].strip()

    # 3. location
    if state.get("nraion"):
        nraion = state.get("nraion", "")
        craion = state.get("craion", "")
        data["location"] = f"{nraion}{craion}".strip(" ,")
    else:
        loc_el = soup.select_one(".location p")
        if loc_el:
            data["location"] = loc_el.get_text(strip=True)

    # 4. price_eur
    if state.get("price"):
        data["price_eur"] = str(state["price"]).strip()
    else:
        price_el = soup.select_one(".price")
        if price_el:
            data["price_eur"] = price_el.get_text(strip=True).replace("€", "").replace(" ", "").strip()

    # 5. area_sqm
    if state.get("area"):
        data["area_sqm"] = str(state["area"]).strip()
    else:
        area_m = re.search(r"Area:\s*([\d.,]+)\s*sq\.m", page_text, re.IGNORECASE)
        if area_m:
            data["area_sqm"] = area_m.group(1).strip()

    # 6. price_per_sqm_eur
    if state.get("price_kv"):
        data["price_per_sqm_eur"] = str(state["price_kv"]).strip()
    else:
        sqm_m = re.search(r"Price\s+(?:on|per)\s+sq\.m:\s*([\d.,]+)\s*€?", page_text, re.IGNORECASE)
        if sqm_m:
            data["price_per_sqm_eur"] = sqm_m.group(1).strip()

    # 7. floor
    if state.get("et"):
        data["floor"] = str(state["et"]).strip()
    else:
        floor_m = re.search(r"Floor\s+([A-Za-z0-9]+)", page_text)
        if floor_m:
            data["floor"] = floor_m.group(1).strip()

    # 7.5 construction_type & construction_year
    # Attempt to get precise year from JSON state
    if state.get("ybuild"):
        data["construction_year"] = str(state["ybuild"]).strip()
    
    # Extract type (and fallback year) from tbuild or HTML spans
    raw_build = ""
    if state.get("tbuild"):
        raw_build = str(state["tbuild"]).strip()
    else:
        for span in soup.select(".parameters span"):
            text = span.get_text(" ", strip=True)
            if "Construction type" in text:
                raw_build = text.split("Construction type")[-1].strip()
                break

    if raw_build:
        # Example raw_build: "Brick, 2026" or "Brick"
        build_parts = [p.strip() for p in raw_build.split(",")]
        data["construction_type"] = build_parts[0]
        
        # If year wasn't found in ybuild but exists in the comma-separated string
        if data["construction_year"] == "N/A" and len(build_parts) > 1:
            year_match = re.search(r"(\d{4})", build_parts[1])
            if year_match:
                data["construction_year"] = year_match.group(1)

    # 8. central_heating & 9. gas
    for span in soup.select(".parameters span"):
        text = span.get_text(" ", strip=True)
        if "Central Heating:" in text:
            data["central_heating"] = text.split("Central Heating:")[-1].strip().upper()
        elif "Gas:" in text:
            data["gas"] = text.split("Gas:")[-1].strip().upper()

    if data["central_heating"] == "N/A":
        if state.get("tec"):
            data["central_heating"] = str(state["tec"]).strip().upper()
        else:
            ch_m = re.search(r"Central\s+Heating:\s*([A-Za-z]+)", page_text, re.IGNORECASE)
            if ch_m:
                data["central_heating"] = ch_m.group(1).strip().upper()

    if data["gas"] == "N/A":
        gas_m = re.search(r"Gas:\s*([A-Za-z]+)", page_text, re.IGNORECASE)
        if gas_m:
            data["gas"] = gas_m.group(1).strip().upper()

    # 10. description_bulgarian
    desc_el = soup.select_one(".description .text")
    if desc_el:
        data["description_bulgarian"] = desc_el.get_text(separator="\n", strip=True)
    elif state.get("extinfo"):
        data["description_bulgarian"] = BeautifulSoup(state["extinfo"], "html.parser").get_text(separator="\n", strip=True)

    # 11. features
    if state.get("extriArr") and isinstance(state["extriArr"], list):
        data["features"] = [item.strip() for item in state["extriArr"] if item.strip()]
    else:
        feature_items = soup.select(".features ul li")
        if feature_items:
            data["features"] = [li.get_text(strip=True) for li in feature_items if li.get_text(strip=True)]
        elif state.get("extri"):
            data["features"] = [f.strip() for f in state["extri"].split(",") if f.strip()]

    # 12. views
    if state.get("views") is not None:
        data["views"] = str(state["views"]).strip()
    else:
        views_m = re.search(r"(\d+)\s+views?", page_text, re.IGNORECASE)
        if views_m:
            data["views"] = views_m.group(1).strip()

    # 13. saves
    if state.get("favs") is not None:
        data["saves"] = str(state["favs"]).strip()
    else:
        saves_m = re.search(r"(\d+)\s+Save(?:s)?\s+to\s+notebook", page_text, re.IGNORECASE)
        if saves_m:
            data["saves"] = saves_m.group(1).strip()

    # 14. ad_published_date
    if state.get("published"):
        date_clean = re.search(r"(?:published|updated)\s+on\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", state["published"], re.I)
        data["ad_published_date"] = date_clean.group(1).strip() if date_clean else state["published"].strip()
    else:
        date_el = soup.select_one(".statistics .date")
        if date_el:
            date_clean = re.search(r"(?:published|updated)\s+on\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", date_el.get_text(), re.I)
            if date_clean:
                data["ad_published_date"] = date_clean.group(1).strip()

    # 15. agency
    if state.get("agency") and isinstance(state["agency"], dict) and state["agency"].get("name"):
        data["agency"] = state["agency"]["name"].strip()
    else:
        agency_el = soup.select_one(".broker a.name") or soup.select_one(".advertiserBox .name")
        if agency_el:
            data["agency"] = agency_el.get_text(strip=True)

    return data


# ----------------------------------------------------------------------
# STEP 3: Execution Loop and CSV Storage (Nested by District & Type)
# ----------------------------------------------------------------------

DISTRICTS = [
    "Abdovitsa", "Banishora", "Belite brezi", "Benkovski", "Borovo", "Botunets", 
    "Botunets 2", "Boyana", "Bakston", "Vitosha", "Voenna rampa", "Vrazhdebna", 
    "Vrabnitsa 1", "Vrabnitsa 2", "Gevgeliyski", "Geo Milev", "Gorna banya", 
    "Gorublyane", "Gotse Delchev", "Gradina", "Dianabad", "Dimitar Milenkov", 
    "Doktorski pametnik", "Dragalevtsi", "Druzhba 1", "Druzhba 2", "Darvenitsa", 
    "Eksperimentalen", "Zapaden park", "Zaharna fabrika", "Zona B-18", "Zona B-19", 
    "Zona B-5", "Zona B-5-3", "Ivan Vazov", "Izgrev", "Iztok", "Ilinden", "Iliyantsi", 
    "Karpuzitsa", "Knyazhevo", "Krasna polyana 1", "Krasna polyana 2", "Krasna polyana 3", 
    "Krasno selo", "Kremikovtsi", "Krastova vada", "Lagera", "Levski", "Levski V", 
    "Levski G", "Letishte Sofia", "Lozenets", "Lyulin - tsentar", "Lyulin 1", "Lyulin 10", 
    "Lyulin 2", "Lyulin 3", "Lyulin 4", "Lyulin 5", "Lyulin 6", "Lyulin 7", "Lyulin 8", 
    "Lyulin 9", "Malashevtsi", "Malinova dolina", "Manastirski livadi", "Meditsinska akademiya", 
    "Mladost 1", "Mladost 1A", "Mladost 2", "Mladost 3", "Mladost 4", "Moderno predgradie", 
    "Musagenitsa", "Nadezhda 1", "Nadezhda 2", "Nadezhda 3", "Nadezhda 4", "NPZ Iztok", 
    "NPZ Iskar", "NPZ Sredets", "NPZ Hadzhi Dimitar", "Obelya", "Obelya 1", "Obelya 2", 
    "Oborishte", "Ovcha kupel", "Ovcha kupel 1", "Ovcha kupel 2", "Orlandovtsi", "Pavlovo", 
    "PZ Iliyantsi", "PZ Hladilnika", "Poduyane", "Poligona", "Razsadnika", "Reduta", 
    "Republika", "Republika 2", "Sveta Troitsa", "Svoboda", "Serdika", "Seslavtsi", 
    "Simeonovo", "Slaviya", "Slatina", "SPZ Moderno predgradie", "SPZ Slatina", "Strelbishte", 
    "Studentski grad", "Suhata reka", "Suhodol", "Tolstoy", "Trebich", "Triagalnika", 
    "Fakulteta", "Filipovtsi", "Fondovi zhilishta", "Hadzhi Dimitar", "Hipodruma", 
    "Hladilnika", "Hristo Botev", "Tsentar", "Chelopechene", "Yavorov", "7-mi 11-ti kilometar", 
    "v.z.Amerikanski kolezh", "v.z.Belovodski pat", "v.z.Boyana", "v.z.Bunkera", 
    "v.z.Vrana - German", "v.z.Vrana - Lozen", "v.z.Gorna banya", "v.z.Kiliite", 
    "v.z.Kinotsentara", "v.z.Kinotsentara 3 chast", "v.z.Lyulin", "v.z.Malinova dolina", 
    "v.z.Malinova dolina - Gerena", "v.z.Simeonovo - Dragalevtsi", "v.z.Cherniya kos", 
    "Bankya", "Buhovo", "Novi Iskar", "zh.gr.Zoopark", "zh.gr.Yuzhen park", "m-t Barite", 
    "m-t Batareyata", "m-t Gardova glava", "m-t Detski grad", "m-t Kambanite", 
    "m-t Kinotsentara", "m-t Mala koriya", "m-t Podlozishte", "m-t Shtarkelovo gnezdo", 
    "m-t Yubileyna gora", "m-t yaz. Iskar", "m-t Yaladzha", "Balsha", "Bistritsa", 
    "Busmantsi", "Vladaya", "Voynegovtsi", "Voluyak", "German", "Gorni Bogrov", 
    "Dobroslavtsi", "Dolni Bogrov", "Dolni Pasarel", "Zheleznitsa", "Zhelyava", "Zhiten", 
    "Ivanyane", "Kazichene", "Klisura", "Kokalyane", "Krivina", "Kubratovo", "Katina", 
    "Lozen", "Lokorsko", "Malo Buchino", "Mirovyane", "Mramor", "Marchaevo", "Negovan", 
    "Pancharevo", "Plana", "Podgumer", "Svetovrachene", "Chepintsi", "Yana"
]

PROPERTY_TYPES = ["apartments", "houses-villas"]


def format_url_slug(name):
    """Converts a district name into the exact URL slug required by imoti.info rules."""
    slug = name.lower()
    slug = slug.replace(" - ", "-")  # Handle "Lyulin - tsentar" -> "lyulin-tsentar"
    slug = slug.replace(".", "-")    # Handle "v.z." -> "v-z-"
    slug = slug.replace(" ", "-")    # Replace all remaining spaces
    slug = re.sub(r'-+', '-', slug)  # Remove any duplicate consecutive hyphens
    return slug


def append_page_to_csv(listings, filename):
    """Saves listings incrementally to avoid data loss if the scraper crashes."""
    if not listings:
        return
    
    file_exists = os.path.isfile(filename)
    
    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if not file_exists:
            writer.writeheader()
            
        for row in listings:
            row_to_write = dict(row)
            if isinstance(row_to_write["features"], list):
                row_to_write["features"] = json.dumps(row_to_write["features"], ensure_ascii=False)
            writer.writerow(row_to_write)


def scrape_sofia_apartments():
    # Ensure directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Initialize the file with headers if it doesn't exist
    if not os.path.isfile(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()

    seen_urls = set()
    total_saved = 0

    for district in DISTRICTS:
        district_slug = format_url_slug(district)
        
        for p_type in PROPERTY_TYPES:
            page_num = 1
            
            while True:
                # Construct the nested URL
                base_url = f"{SEARCH_BASE}/{district_slug}/{p_type}"
                page_url = base_url if page_num == 1 else f"{base_url}/page-{page_num}"
                
                print(f"Fetching: {page_url}")

                try:
                    links = get_listing_links(page_url)
                except requests.RequestException as e:
                    print(f"  Failed loading page {page_num}: {e}")
                    break

                # Filter out links already seen
                new_links = [l for l in links if l not in seen_urls]
                if not new_links:
                    print("  No new listing links found. Moving to next category.")
                    break

                print(f"  Found {len(new_links)} new links.")
                page_listings = []

                for link in new_links:
                    seen_urls.add(link)
                    try:
                        details = get_listing_details(link)
                        page_listings.append(details)
                        print(f"    Scraped: ID {details['ad_id']} | {details['location']} | {details['agency']}")
                    except requests.RequestException as e:
                        print(f"    Error scraping {link}: {e}")

                    time.sleep(random.uniform(0.1, 0.3))

                # Save immediately after finishing the page
                append_page_to_csv(page_listings, OUTPUT_FILE)
                total_saved += len(page_listings)
                print(f"  -> Saved {len(page_listings)} items. Running total: {total_saved}")

                time.sleep(random.uniform(0.2, 0.5))
                page_num += 1


if __name__ == "__main__":
    scrape_sofia_apartments()