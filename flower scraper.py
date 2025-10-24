import requests
from bs4 import BeautifulSoup
import os
import time

# === CONFIG ===
SPECIES_FILE = "species_list.txt"
OUTPUT_FOLDER = "orchid_inflorescences"
HEADERS = {
    "User-Agent": "OrchidInflorescenceScraper/1.0 (contact: example@example.com)"
}
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
INAT_BASE = "https://api.inaturalist.org/v1/observations"

# === Helpers ===
def load_species_list(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

# --- IOSPE ---
def test_iospe_urls(species):
    base = "http://www.orchidspecies.com/"
    genus, *rest = species.split()
    if not rest:
        return []
    species_epithet = rest[0].lower()
    candidates = [
        f"{base}{genus.lower()}{species_epithet}.htm",
        f"{base}{genus.lower()}_{species_epithet}.htm",
        f"{base}{genus.lower()}{species_epithet}.html",
        f"{base}{genus.lower()}.htm",
        f"{base}{genus.lower()}.html",
    ]
    valid = []
    for url in candidates:
        try:
            resp = requests.head(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                valid.append(url)
        except requests.RequestException:
            continue
    return valid

def scrape_iospe_image(url):
    """Get first likely flower/inflorescence image from an IOSPE page, ignoring maps/logos."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None, 0

    soup = BeautifulSoup(resp.text, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        if not src.startswith("http"):
            src = "http://www.orchidspecies.com/" + src.lstrip("/")

        fname = src.lower()
        if any(x in fname for x in ["map", "logo", "icon"]):
            continue  # skip maps/logos

        alt = img.get("alt", "").lower()
        if "flower" in alt or "inflorescence" in alt or not alt:
            try:
                h = requests.head(src, headers=HEADERS, timeout=10)
                size = int(h.headers.get("Content-Length", 0))
            except:
                size = 0
            return src, size

    return None, 0

# --- iNaturalist ---
def get_inat_image(species):
    params = {
        "taxon_name": species,
        "quality_grade": "research",
        "per_page": 1,
        "order_by": "created_at",
    }
    try:
        resp = requests.get(INAT_BASE, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results and "photos" in results[0]:
            photo = results[0]["photos"][0]
            url = photo.get("url")
            if url:
                url = url.replace("square", "original")
                size = requests.head(url, headers=HEADERS).headers.get("Content-Length", 0)
                return url, int(size)
    except Exception:
        return None, 0
    return None, 0

# --- Wikimedia ---
def get_wikimedia_image(species):
    category = species.replace(" ", "_")
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": category + " inflorescence",
        "gsrlimit": 1,
        "prop": "imageinfo",
        "iiprop": "url|size"
    }
    try:
        resp = requests.get(WIKIMEDIA_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                return info[0]["url"], info[0]["size"]
    except Exception:
        return None, 0
    return None, 0

# --- Download ---
def download_image(url, save_path):
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=20) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        print(f"  ⚠️ Error downloading {url}: {e}")

# === Main ===
def main():
    species_list = load_species_list(SPECIES_FILE)
    print(f"Loaded {len(species_list)} species.")

    total_estimate = 0
    found_images = []

    for sp in species_list:
        print(f"\n🔎 Processing: {sp}")
        found = False

        # 1️⃣ IOSPE
        urls = test_iospe_urls(sp)
        for url in urls:
            img_url, size = scrape_iospe_image(url)
            if img_url:
                print(f"  ✅ Found IOSPE image: {img_url}")
                found_images.append((sp, img_url, size))
                total_estimate += size
                found = True
                break

        # 2️⃣ iNaturalist
        if not found:
            img_url, size = get_inat_image(sp)
            if img_url:
                print(f"  🌿 Found iNaturalist image: {img_url}")
                found_images.append((sp, img_url, size))
                total_estimate += size
                found = True

        # 3️⃣ Wikimedia fallback
        if not found:
            img_url, size = get_wikimedia_image(sp)
            if img_url:
                print(f"  🌐 Found Wikimedia image: {img_url}")
                found_images.append((sp, img_url, size))
                total_estimate += size
            else:
                print(f"  ❌ No image found anywhere.")

        time.sleep(1)  # polite delay

    # Summary
    print("\n=== Summary ===")
    print(f"Total images: {len(found_images)}")
    print(f"Estimated total size: {total_estimate/1024/1024:.2f} MB")

    # Download
    for sp, url, size in found_images:
        fname = sp.replace(" ", "_") + "_" + os.path.basename(url.split("?")[0])
        path = os.path.join(OUTPUT_FOLDER, fname)
        print(f"⬇️  Downloading {fname} ({size/1024:.1f} KB)...")
        download_image(url, path)
        time.sleep(0.5)

    print("\n✅ Done. All images saved in:", OUTPUT_FOLDER)

if __name__ == "__main__":
    main()
