import os
import tkinter as tk
from tkinter import filedialog, ttk, Listbox, Scrollbar
from PIL import Image, ExifTags
import webbrowser
import re

# Global variable to store selected folder
selected_folder = ""

# Function to extract metadata from an image
def extract_metadata(image_path):
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if exif_data:
                return {ExifTags.TAGS.get(tag, tag): str(value) for tag, value in exif_data.items()}
    except Exception as e:
        print(f"Error reading {image_path}: {e}")
    return {}

# Function to choose folder and update label
def choose_folder():
    global selected_folder
    folder_path = filedialog.askdirectory(title="Select Folder with Images")
    if folder_path:
        selected_folder = folder_path
        folder_label.config(text=f"Folder: {folder_path}", foreground="black")

# Function to convert wildcard queries to regex patterns
def wildcard_to_regex(query):
    return query.replace("*", ".*")  # Convert * to regex equivalent

# Function to parse logical search queries
def parse_query(query):
    """
    Extracts phrases in quotes, field-specific searches, and logical operators.
    Example:
    'Copyright: John Doe AND ISO: 1600' -> [('Copyright', 'John Doe'), 'AND', ('ISO', '1600')]
    """
    field_pattern = r'(\w+)\s*:\s*"([^"]+)"|(\w+)\s*:\s*([\S]+)'  # Matches field:value or field:"value"
    logical_pattern = r'\b(AND|OR|NOT)\b'  # Matches logical operators
    matches = re.findall(field_pattern, query, re.IGNORECASE)

    parsed_terms = []
    for match in matches:
        field = match[0] or match[2]
        value = match[1] or match[3]
        parsed_terms.append((field.lower(), wildcard_to_regex(value.lower())))

    # Find logical operators
    operators = re.findall(logical_pattern, query, re.IGNORECASE)

    return parsed_terms, operators

# Function to evaluate complex field-specific search queries
def match_search_terms(metadata, query):
    metadata = {k.lower(): v.lower() for k, v in metadata.items()}  # Normalize metadata keys/values
    parsed_terms, operators = parse_query(query)

    if not parsed_terms:
        return False  # No valid search terms found

    results = []
    
    for field, pattern in parsed_terms:
        if field in metadata:
            match_found = re.search(pattern, metadata[field]) is not None
        else:
            match_found = False  # Field not in metadata

        results.append(match_found)

    # Apply logical operations (AND, OR, NOT)
    if "AND" in operators:
        return all(results)
    elif "OR" in operators:
        return any(results)
    elif "NOT" in operators:
        return results[0] and not results[1]  # Assumes only one NOT condition for simplicity
    else:
        return any(results)  # Default behavior if no operators

# Function to recursively search for images in all subfolders
def search_images_in_folder(folder):
    image_files = []
    for root, _, files in os.walk(folder):  # Recursively walks through all subdirectories
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                image_files.append(os.path.join(root, file))
    return image_files

# Function to scan images in folder (and subfolders) and search metadata
def search_metadata():
    if not selected_folder:
        folder_label.config(text="Please choose a folder first!", foreground="red")
        return

    search_query = search_entry.get().strip()
    results_list.delete(0, tk.END)  # Clear previous results
    global image_matches
    image_matches = []  # Store image paths for reference

    image_files = search_images_in_folder(selected_folder)  # Get images from all subfolders

    for image_path in image_files:
        metadata = extract_metadata(image_path)

        if match_search_terms(metadata, search_query):
            display_text = f"{os.path.relpath(image_path, selected_folder)} - Match found"
            results_list.insert(tk.END, display_text)
            image_matches.append(image_path)

# Function to open image on click
def open_selected_image(event):
    selected_index = results_list.curselection()  # Get selected item index
    if selected_index:
        image_path = image_matches[selected_index[0]]
        webbrowser.open(image_path)  # Open with default image viewer

# GUI Setup
root = tk.Tk()
root.title("Advanced Image Metadata Search")
root.geometry("700x500")

frame = ttk.Frame(root, padding=10)
frame.pack(fill=tk.BOTH, expand=True)

# Folder Selection
folder_button = ttk.Button(frame, text="Choose Folder", command=choose_folder)
folder_button.pack(pady=5)

folder_label = ttk.Label(frame, text="No folder selected", foreground="blue")
folder_label.pack(pady=5)

# Search Input
ttk.Label(frame, text="Search Term: (Field:Value, AND, OR, NOT, *, quotes for phrases)").pack(pady=5)
search_entry = ttk.Entry(frame, width=50)
search_entry.pack(pady=5)

# Search Button
search_button = ttk.Button(frame, text="Search Metadata", command=search_metadata)
search_button.pack(pady=5)

# Results Label
ttk.Label(frame, text="Results (Double-click to Open Image):").pack(pady=5)

# Scrollable Listbox
list_frame = ttk.Frame(frame)
list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

results_list = Listbox(list_frame, width=100, height=20)
results_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = Scrollbar(list_frame, orient="vertical", command=results_list.yview)
scrollbar.pack(side=tk.RIGHT, fill="y")
results_list.config(yscrollcommand=scrollbar.set)

results_list.bind("<Double-Button-1>", open_selected_image)  # Double-click to open

root.mainloop()
