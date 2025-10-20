import requests
import os
import time

# === CONFIG ===
species_file = "species_list.txt"  # text file with one species per line
output_folder = "orchid_inflorescences"
os.makedirs(output_folder, exist_ok=True)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
FILTER_INFLORESCENCE = True  # set False to download all images

# --- Helper Functions ---

def load_species_list(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def get_category_members(category, cmtype="file"):
    """Get category members of type 'file' or 'subcat'"""
    members = []
    cmcontinue = ""
    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": cmtype,
            "cmlimit": "50",
            "cmcontinue": cmcontinue
        }
        resp = requests.get(WIKIMEDIA_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        members.extend(data.get("query", {}).get("categorymembers", []))
        if "continue" in data:
            cmcontinue = data["continue"]["cmcontinue"]
        else:
            break
    return members

def gather_images_recursive(category):
    """Recursively gather all images in a category and subcategories"""
    images = []

    # Get images directly in this category
    for file_member in get_category_members(category, cmtype="file"):
        title = file_member["title"]
        if FILTER_INFLORESCENCE:
            if "inflorescence" in title.lower():
                images.append(title)
        else:
            images.append(title)

    # Recurse into subcategories
    for subcat in get_category_members(category, cmtype="subcat"):
        subcat_name = subcat["title"].replace("Category:", "")
        images.extend(gather_images_recursive(subcat_name))

    return images

def get_image_info(file_title):
    """Return original image URL and file size in bytes"""
    params = {
        "action": "query",
        "format": "json",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|size"
    }
    resp = requests.get(WIKIMEDIA_API, params=params)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        imageinfo = page.get("imageinfo", [])
        if imageinfo:
            return imageinfo[0]["url"], imageinfo[0]["size"]
    return None, 0

def download_image(url, save_path):
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)

# --- Main Script ---

def main():
    species_list = load_species_list(species_file)
    print(f"Loaded {len(species_list)} species from {species_file}")

    total_estimate = 0
    all_files_info = []

    # First pass: gather image URLs and sizes
    for species in species_list:
        print(f"\nScanning species: {species}")
        category_name = species.replace(" ", "_")
        try:
            images = gather_images_recursive(category_name)
            if not images:
                print("  No images found.")
                continue
            print(f"  Found {len(images)} image(s) matching criteria.")
            for f in images:
                url, size = get_image_info(f)
                if url:
                    all_files_info.append((species, url, size))
                    total_estimate += size
        except Exception as e:
            print(f"  Error processing {species}: {e}")

    print("\n=== Storage Estimate ===")
    print(f"Total files: {len(all_files_info)}")
    print(f"Estimated total size: {total_estimate / 1024 / 1024:.2f} MB")

    # Second pass: download images
    for species, url, size in all_files_info:
        filename = os.path.basename(url.split("?")[0])
        safe_name = f"{species.replace(' ','_')}__{filename}"
        save_path = os.path.join(output_folder, safe_name)
        print(f"Downloading {safe_name} ({size/1024/1024:.2f} MB)...")
        download_image(url, save_path)
        time.sleep(1)  # polite delay

    print("\n✅ All images downloaded.")

if __name__ == "__main__":
    main()
