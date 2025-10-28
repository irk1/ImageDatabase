# download_jxl_deb.py
# Downloads jpeg-xl-tools and dependencies for Debian 12 amd64

import subprocess
import os

# ===== CONFIG =====
DEB_VERSION = "bookworm"      # Debian version OMV is based on
ARCH = "amd64"                # OMV CPU architecture
DOWNLOAD_FOLDER = r"C:\Users\izzyk\OneDrive\Documents\GitHub\ImageDatabase\New folder" # Change to your flash drive if desired

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# List of main packages to download
packages = [
    "jpeg-xl-tools",
    "libjxl0",
    "libbrotli1",
    "libpng16-16",
    "libstdc++6"
]

# Command template
# Use a Debian VM or WSL for apt-get download
for pkg in packages:
    cmd = [
        "apt-get",
        "download",
        pkg
    ]
    print(f"Downloading {pkg}...")
    try:
        subprocess.run(cmd, cwd=DOWNLOAD_FOLDER, check=True)
    except subprocess.CalledProcessError:
        print(f"Failed to download {pkg}. You may need to install apt-rdepends or check package names.")
