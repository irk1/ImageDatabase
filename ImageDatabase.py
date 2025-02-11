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
    query = query.lower()
    query = query.replace("*", ".*")  # Convert * to regex equivalent
    return query

# Function to parse query into logical components
def parse_query(query):
    """
    Extracts phrases in quotes and individual words while keeping logical operators.
    Example:
    'Exposure Value' AND ISO 100  -> ['"Exposure Value"', 'AND', 'ISO', '100']
    """
    pattern = r'"([^"]+)"|\S+'  # Matches quoted phrases OR single words
    return re.findall(pattern, query)

# Function to evaluate complex search queries with phrases and wildcards
def match_search_terms(metadata_text, query):
    metadata_text = metadata_text.lower()
    terms = parse_query(query)

    if " and " in query.lower():
        subqueries = [wildcard_to_regex(term) for term in terms if term.lower() != "and"]
        return all(re.search(term, metadata_text) for term in subqueries)

    elif " or " in query.lower():
        subqueries = [wildcard_to_regex(term) for term in terms if term.lower() != "or"]
        return any(re.search(term, metadata_text) for term in subqueries)

    elif " not " in query.lower():
        parts = query.lower().split(" not ")
        include_pattern = wildcard_to_regex(parts[0].strip())
        exclude_pattern = wildcard_to_regex(parts[1].strip())
        return re.search(include_pattern, metadata_text) and not re.search(exclude_pattern, metadata_text)

    else:
        # If no operators, check for any match
        subqueries = [wildcard_to_regex(term) for term in terms]
        return any(re.search(term, metadata_text) for term in subqueries)

# Function to scan images in folder and search metadata
def search_metadata():
    if not selected_folder:
        folder_label.config(text="Please choose a folder first!", foreground="red")
        return

    search_query = search_entry.get().strip()
    results_list.delete(0, tk.END)  # Clear previous results
    global image_matches
    image_matches = []  # Store image paths for reference

    for filename in os.listdir(selected_folder):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
            image_path = os.path.join(selected_folder, filename)
            metadata = extract_metadata(image_path)

            metadata_text = " ".join(metadata.values()).lower()

            if match_search_terms(metadata_text, search_query):
                display_text = f"{filename} - {search_query} found"
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
root.geometry("650x450")

frame = ttk.Frame(root, padding=10)
frame.pack(fill=tk.BOTH, expand=True)

# Folder Selection
folder_button = ttk.Button(frame, text="Choose Folder", command=choose_folder)
folder_button.pack(pady=5)

folder_label = ttk.Label(frame, text="No folder selected", foreground="blue")
folder_label.pack(pady=5)

# Search Input
ttk.Label(frame, text="Search Term: (Use AND, OR, NOT, *, or quotes for phrases)").pack(pady=5)
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

results_list = Listbox(list_frame, width=90, height=15)
results_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = Scrollbar(list_frame, orient="vertical", command=results_list.yview)
scrollbar.pack(side=tk.RIGHT, fill="y")
results_list.config(yscrollcommand=scrollbar.set)

results_list.bind("<Double-Button-1>", open_selected_image)  # Double-click to open

root.mainloop()
