"""
plant_photo_manager.py
A compact plant photo database manager with GUI, compact filename generation,
raw-file attachment (copy or reference), and search/filtering.

Dependencies:
    pip install pillow
"""

import os
import shutil
import sqlite3
import hashlib
import csv
import datetime
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import sys
import platform
import subprocess
import threading

# -------------------------
# Configuration / Folders
# -------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(APP_DIR, "processed")
RAW_DIR = os.path.join(APP_DIR, "raw")
THUMB_SIZE = (320, 240)


# -------------------------
# Utility functions
# -------------------------

def gen_compact_filename(species, date_taken, feat=None, loc=None, used_topaz=False, original_name=None):
    """
    Generate a compact filename for a plant image.
    
    Args:
        species (str): Species name.
        date_taken (str or datetime.date): Date the photo was taken.
        feat (str, optional): Feature code.
        loc (str, optional): Location code.
        used_topaz (bool, optional): Flag if Topaz enhancement was used.
        original_name (str, optional): Original filename.
    
    Returns:
        tuple: (fname, spec_code, feat_code, locc)
    """

    # Example logic to generate codes
    spec_code = species[:3].upper() if species else "UNK"
    feat_code = feat[:2].upper() if feat else "XX"
    locc = loc[:2].upper() if loc else "YY"

    # Construct filename
    date_str = date_taken.strftime("%Y%m%d") if hasattr(date_taken, "strftime") else str(date_taken)
    topaz_tag = "_T" if used_topaz else ""
    orig_tag = f"_{original_name}" if original_name else ""
    
    fname = f"{spec_code}{feat_code}{locc}_{date_str}{topaz_tag}{orig_tag}.jpg"

    return fname, spec_code, feat_code, locc


def open_path(path):
    """
    Open a file or folder using the OS default method.
    """
    if not os.path.exists(path):
        messagebox.showwarning("Missing", f"Path does not exist:\n{path}")
        return

    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", path])
        else:  # Linux and others
            subprocess.run(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open path:\n{e}")


# -------------------------
# Database file selection and initialization
# -------------------------

import threading

DEFAULT_DB_FILE = os.path.join(APP_DIR, "plant_photos.db")

def select_or_create_db():
    """Prompt once for a database file, or create default if none chosen."""
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select Plant Photo Database",
        filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
    )
    root.destroy()

    if not path:
        path = DEFAULT_DB_FILE
        print(f"No file selected — using default: {path}")

    if not os.path.exists(path):
        print(f"Creating new database at: {path}")
        init_db_at(path)
    return path


def init_db_at(db_path):
    """Initialize all required database tables."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Photos table
    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species TEXT,
            species_code TEXT,
            gfib_link TEXT,
            main_feature TEXT,
            feature_code TEXT,
            date_taken TEXT,
            used_topaz INTEGER,
            subject_size TEXT,
            other_features TEXT,
            location TEXT,
            location_code TEXT,
            processed_filename TEXT,
            processed_path TEXT,
            raw_attached INTEGER,
            raw_paths TEXT,
            raw_mode TEXT,
            created_at TEXT
        )
    ''')

    # Mapping tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS feature_mappings (
            specific TEXT PRIMARY KEY,
            general TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS location_mappings (
            specific TEXT PRIMARY KEY,
            general TEXT
        )
    ''')
    conn.commit()
    conn.close()


# -------------------------
# Database initialization and mapping
# -------------------------

def init_db_if_missing(db_path):
    """Ensure the database and its tables exist."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species TEXT,
            species_code TEXT,
            gfib_link TEXT,
            main_feature TEXT,
            feature_code TEXT,
            date_taken TEXT,
            used_topaz INTEGER,
            subject_size TEXT,
            other_features TEXT,
            location TEXT,
            location_code TEXT,
            processed_filename TEXT,
            processed_path TEXT,
            raw_attached INTEGER,
            raw_paths TEXT,
            raw_mode TEXT,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feature_mappings (
            specific TEXT PRIMARY KEY,
            general TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS location_mappings (
            specific TEXT PRIMARY KEY,
            general TEXT
        )
    ''')
    conn.commit()
    conn.close()


def select_or_create_db():
    """Prompt user to select an existing DB or create a new one."""
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()

    path = filedialog.askopenfilename(
        title="Select Existing Plant Photo Database",
        filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
    )

    if not path:
        path = filedialog.asksaveasfilename(
            title="Create New Plant Photo Database",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
        )

    root.destroy()
    return path or os.path.join(APP_DIR, "plant_photos.db")


def load_specific_mappings(db_file):
    """
    Safely loads feature and location mappings from the database.
    Returns: (FEATURE_MAP, LOCATION_MAP)
    """
    FEATURE_MAP = {}
    LOCATION_MAP = {}
    try:
        conn = sqlite3.connect(db_file)
        c = conn.cursor()

        # Ensure tables exist
        c.execute("""CREATE TABLE IF NOT EXISTS feature_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        parent_id INTEGER,
                        general TEXT
                     )""")
        c.execute("""CREATE TABLE IF NOT EXISTS location_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        parent_id INTEGER,
                        general TEXT
                     )""")
        conn.commit()

        # Load feature mappings
        c.execute("SELECT specific, general FROM feature_mappings")
        for name, general in c.fetchall():
            FEATURE_MAP[name] = general

        # Load location mappings
        c.execute("SELECT specific, general FROM location_mappings")
        for name, general in c.fetchall():
            LOCATION_MAP[name] = general

    except Exception as e:
        messagebox.showerror("Database Error", f"Error loading mappings:\n{e}")
    finally:
        conn.close()

    return FEATURE_MAP, LOCATION_MAP


def ensure_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        species TEXT,
        species_code TEXT,
        gfib_link TEXT,
        main_feature TEXT,
        feature_code TEXT,
        date_taken TEXT,
        used_topaz INTEGER,
        subject_size TEXT,
        other_features TEXT,
        location TEXT,
        location_code TEXT,
        processed_filename TEXT,
        processed_path TEXT,
        raw_attached INTEGER,
        raw_paths TEXT,
        raw_mode TEXT,
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS feature_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        parent_id INTEGER,
        general TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS location_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        parent_id INTEGER,
        general TEXT
    )""")
    conn.commit()
    conn.close()


# --- One-time setup before GUI ---
DB_FILE = select_or_create_db()
ensure_db()
db_file = DB_FILE
# Ensure database exists and has proper schema
init_db_if_missing(DB_FILE)

# Make sure working folders exist
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

# Prepare empty mappings (will load in GUI)
FEATURE_MAP, LOCATION_MAP = {}, {}



# -------------------------
# GUI Application
# -------------------------
class PlantPhotoManager(tk.Tk):
    def __init__(self, db_file):
        print("[DEBUG] Initializing PlantPhotoManager...")
        super().__init__()

        # Assign database file
        self.db_file = db_file

        # Set up main window
        self.title("Plant Photo Manager")
        self.geometry("1050x700")
        self.minsize(950, 620)

        # Setup empty maps; will load immediately
        global FEATURE_MAP, LOCATION_MAP
        FEATURE_MAP = {}
        LOCATION_MAP = {}

        print("[DEBUG] Loading mappings into memory...")
        try:
            FEATURE_MAP, LOCATION_MAP = load_specific_mappings(self.db_file)
            print(f"[DEBUG] Feature mappings loaded: {len(FEATURE_MAP)}")
            print(f"[DEBUG] Location mappings loaded: {len(LOCATION_MAP)}")
        except Exception as e:
            print("[DEBUG] Mapping load error:", e)

        print("[DEBUG] Starting GUI widget setup...")
        self.setup_widgets()  # Only call once
        print("[DEBUG] Finished setup_widgets()")
    # -------------------------
    # Fetch previous values for autocomplete
    # -------------------------
    def get_previous_values(self, field):
        """Return a list of distinct previous entries for a given metadata field."""
        if field not in ("species_var", "feature_var", "size_var", "other_var", "loc_var"):
            return []
        # Map Tk variable names to DB columns
        field_map = {
            "species_var": "species",
            "feature_var": "main_feature",
            "size_var": "subject_size",
            "other_var": "other_features",
            "loc_var": "location"
        }
        col = field_map.get(field)
        if not col:
            return []

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(f"SELECT DISTINCT {col} FROM photos WHERE {col} IS NOT NULL AND {col} != ''")
            rows = c.fetchall()
            conn.close()
            return [r[0] for r in rows if r[0]]
        except Exception:
            return []

    
    def load_mappings_async(self):
        """
        Loads FEATURE_MAP and LOCATION_MAP in a background thread safely.
        Updates GUI via self.after().
        """
        import threading

        def loader():
            global FEATURE_MAP, LOCATION_MAP
            FEATURE_MAP, LOCATION_MAP = load_specific_mappings(DB_FILE)
            self.after(0, self.refresh_autocomplete)

        threading.Thread(target=loader, daemon=True).start()

    def refresh_autocomplete(self):
        """Refresh all autocomplete comboboxes in Add tab after mappings are loaded."""
        for varname in ("species_var", "feature_var", "size_var", "other_var", "loc_var"):
            cb = getattr(self, varname + "_combobox", None)
            if cb:
                cb['values'] = self.get_previous_values(varname)

    def setup_widgets(self):
        # Use self.notebook instead of a local variable
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.add_frame = ttk.Frame(self.notebook)
        self.search_frame = ttk.Frame(self.notebook)
        self.db_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.add_frame, text="Add New Entry")
        self.notebook.add(self.search_frame, text="Search / Filter")
        self.notebook.add(self.db_frame, text="Database View / Export")

        self.build_add_tab()
        self.build_search_tab()
        self.build_db_tab()

        # --- Add Edit Entries Tab ---
        self.edit_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.edit_tab, text="Edit Entries")
        self.build_edit_tab()

            
        # --- Mappings tab ---
        self.build_mappings_tab()

    # ---------------------
    # Add Tab
    # ---------------------
    def build_add_tab(self):
        frm = self.add_frame

        # Scrollable canvas/frame to contain everything
        canvas = tk.Canvas(frm)
        vscroll = ttk.Scrollbar(frm, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        left = ttk.Frame(scrollable_frame, padding=10)
        right = ttk.Frame(scrollable_frame, padding=10)
        left.pack(side="left", fill="y", padx=(8, 4))
        right.pack(side="left", fill="both", expand=True, padx=(4, 8))

        # Processed image selector
        ttk.Label(left, text="Processed image (required)").grid(row=0, column=0, sticky="w")
        self.proc_path_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.proc_path_var, width=46).grid(row=1, column=0, sticky="w")
        ttk.Button(left, text="Browse...", command=self.browse_processed).grid(row=1, column=1, padx=6)

        # Raw file attach
        ttk.Label(left, text="Attach raw file(s) (optional)").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.raw_listbox = tk.Listbox(left, height=5, width=60)
        self.raw_listbox.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(left, text="Add Raw Files...", command=self.browse_raw).grid(row=4, column=0, pady=6, sticky="w")
        ttk.Button(left, text="Remove Selected Raw", command=self.remove_selected_raw).grid(row=4, column=1, pady=6, sticky="w")

        # Option: copy raw or reference (tk.Checkbutton supports wraplength)
        self.copy_raw_var = tk.IntVar(value=1)
        tk.Checkbutton(
            left,
            text="Copy raw files into managed raw/ folder\n(uncheck to only reference original paths)",
            variable=self.copy_raw_var,
            wraplength=320,
            justify="left",
            anchor="w",
            padx=4
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Metadata fields with autocomplete
        row = 6
        def mk_entry(label_text, varname, autocomplete=True):
            nonlocal row
            setattr(self, varname, tk.StringVar())
            ttk.Label(left, text=label_text).grid(row=row, column=0, sticky="w", pady=(6, 0))
            if autocomplete:
                cb = ttk.Combobox(
                    left,
                    textvariable=getattr(self, varname),
                    width=46,
                    values=self.get_previous_values(varname)
                )
                cb.grid(row=row+1, column=0, columnspan=2, sticky="w")
            else:
                ttk.Entry(left, textvariable=getattr(self, varname), width=46).grid(row=row+1, column=0, columnspan=2, sticky="w")
            row += 2

        mk_entry("Species (Genus species)", "species_var")
        mk_entry("Link to GFIB (optional)", "gfib_var", autocomplete=False)
        mk_entry("Main feature (flower, leaf...)", "feature_var")
        mk_entry("Date taken (YYYY-MM-DD)", "date_var", autocomplete=False)
        mk_entry("Subject size (macro/small/med/large)", "size_var")
        mk_entry("Other visible features (comma sep)", "other_var")
        mk_entry("Location (greenhouse, wild...)", "loc_var")

        self.topaz_var = tk.IntVar(value=0)
        ttk.Checkbutton(left, text="Processed with Topaz AI", variable=self.topaz_var).grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        # Filename preview + actions
        ttk.Label(left, text="Generated filename preview").grid(row=row, column=0, sticky="w")
        self.preview_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.preview_var, width=46, state="readonly").grid(row=row+1, column=0, columnspan=2, sticky="w")
        ttk.Button(left, text="Generate Preview", command=self.update_preview).grid(row=row+1, column=1, padx=6)
        row += 2

        ttk.Button(left, text="Save Entry (Copy files & write DB)", command=self.save_entry).grid(row=row, column=0, pady=12, sticky="w")
        ttk.Button(left, text="Clear", command=self.clear_add_form).grid(row=row, column=1, pady=12, sticky="e")

        # Right: thumbnail, attached raw list, and notes
        ttk.Label(right, text="Processed Image Preview").pack(anchor="w")
        self.thumb_label = ttk.Label(right)
        self.thumb_label.pack(pady=6)
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(right, text="Attached raw files").pack(anchor="w")
        self.raw_files_text = tk.Text(right, height=8, wrap="word")
        self.raw_files_text.pack(fill="both", expand=False)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(right, text="Notes / Quick view").pack(anchor="w")
        self.note_preview = tk.Text(right, height=8, wrap="word")
        self.note_preview.pack(fill="both", expand=True)

    def build_edit_tab(self):
        """Build the Edit Entries tab with search, editable fields, and image management."""

        # --- Search Section ---
        search_frame = ttk.LabelFrame(self.edit_tab, text="Search / Select Entry")
        search_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(search_frame, text="Species:").grid(row=0, column=0, sticky="w")
        self.edit_species_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.edit_species_var).grid(row=0, column=1, padx=5, sticky="ew")

        ttk.Label(search_frame, text="Date Taken:").grid(row=0, column=2, sticky="w")
        self.edit_date_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.edit_date_var).grid(row=0, column=3, padx=5, sticky="ew")

        ttk.Button(search_frame, text="Search", command=self.search_entries).grid(row=0, column=4, padx=5)

        search_frame.columnconfigure(1, weight=1)
        search_frame.columnconfigure(3, weight=1)

        # --- Results List ---
        results_frame = ttk.LabelFrame(self.edit_tab, text="Matching Entries")
        results_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.edit_results_list = tk.Listbox(results_frame, height=8)
        self.edit_results_list.pack(side="left", fill="both", expand=True)
        self.edit_results_list.bind("<<ListboxSelect>>", self.load_selected_entry)

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.edit_results_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.edit_results_list.config(yscrollcommand=scrollbar.set)

        # --- Editable Fields Section ---
        fields_frame = ttk.LabelFrame(self.edit_tab, text="Edit Metadata / Associated Images")
        fields_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Species
        ttk.Label(fields_frame, text="Species:").grid(row=0, column=0, sticky="w")
        self.edit_species_entry = ttk.Entry(fields_frame)
        self.edit_species_entry.grid(row=0, column=1, sticky="ew", padx=5)

        # Main Feature
        ttk.Label(fields_frame, text="Main Feature:").grid(row=1, column=0, sticky="w")
        self.edit_feature_entry = ttk.Entry(fields_frame)
        self.edit_feature_entry.grid(row=1, column=1, sticky="ew", padx=5)

        # Location
        ttk.Label(fields_frame, text="Location:").grid(row=2, column=0, sticky="w")
        self.edit_location_entry = ttk.Entry(fields_frame)
        self.edit_location_entry.grid(row=2, column=1, sticky="ew", padx=5)

        # Date Taken
        ttk.Label(fields_frame, text="Date Taken:").grid(row=3, column=0, sticky="w")
        self.edit_date_entry = ttk.Entry(fields_frame)
        self.edit_date_entry.grid(row=3, column=1, sticky="ew", padx=5)

        # Used Topaz
        ttk.Label(fields_frame, text="Used Topaz:").grid(row=4, column=0, sticky="w")
        self.edit_topaz_var = tk.BooleanVar()
        ttk.Checkbutton(fields_frame, variable=self.edit_topaz_var).grid(row=4, column=1, sticky="w", padx=5)

        # Raw Files
        ttk.Label(fields_frame, text="Raw Files:").grid(row=5, column=0, sticky="w")
        self.edit_raw_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.edit_raw_var, state="readonly").grid(row=5, column=1, sticky="ew", padx=5)
        ttk.Button(fields_frame, text="Add/Change Raw Files", command=self.browse_edit_raw).grid(row=5, column=2, padx=5)

        # Processed File
        ttk.Label(fields_frame, text="Processed File:").grid(row=6, column=0, sticky="w")
        self.edit_processed_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.edit_processed_var, state="readonly").grid(row=6, column=1, sticky="ew", padx=5)
        ttk.Button(fields_frame, text="Select Processed File", command=self.browse_edit_processed).grid(row=6, column=2, padx=5)

        # Save Changes Button
        ttk.Button(fields_frame, text="Save Changes", command=self.save_edited_entry).grid(row=7, column=0, columnspan=3, pady=10)

        # Make the fields expand nicely
        fields_frame.columnconfigure(1, weight=1)

    # --- Major Mappings Tab ---
    def build_mappings_tab(self):
        # Clear previous tab if needed
        if hasattr(self, 'mappings_tab'):
            self.mappings_tab.destroy()

        import tkinter as tk
        from tkinter import ttk

        self.mappings_tab = ttk.Notebook(self)
        self.mappings_tab.pack(fill="both", expand=True)

        # Build features and locations tabs
        self.build_feature_tab()
        self.build_location_tab()


    # --- Feature Mappings Sub-tab ---
    def build_feature_tab(self):
        import tkinter as tk
        from tkinter import ttk

        if hasattr(self, 'feature_frame'):
            self.feature_frame.destroy()

        self.feature_frame = ttk.Frame(self.mappings_tab)
        self.feature_frame.pack(fill="both", expand=True)

        feature_tree = self.load_feature_tree()

        self.feature_treeview = ttk.Treeview(self.feature_frame)
        self.feature_treeview.pack(fill="both", expand=True)

        for general, specifics in feature_tree.items():
            general_id = self.feature_treeview.insert("", "end", text=general)
            for specific in specifics:
                self.feature_treeview.insert(general_id, "end", text=specific)


    def load_feature_tree(self):
        """
        Load the feature hierarchy from the database.
        Returns a dict: {general_category: [specific_features]}
        """
        import sqlite3

        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute("SELECT specific, general FROM feature_mappings")
        rows = c.fetchall()
        conn.close()

        feature_tree = {}
        for specific, general in rows:
            if general not in feature_tree:
                feature_tree[general] = []
            feature_tree[general].append(specific)

        return feature_tree


    def add_feature(self):
        """Add a new feature under a selected parent."""
        selection = self.feature_tree.selection()
        parent_id = int(selection[0]) if selection else None

        def save_new():
            name = name_var.get().strip()
            general = general_var.get().strip() or name
            if not name:
                messagebox.showwarning("Invalid", "Feature name cannot be empty.")
                return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO feature_mappings (name, parent_id, general) VALUES (?, ?, ?)",
                    (name, parent_id, general))
            conn.commit()
            conn.close()
            self.load_feature_tree()
            add_win.destroy()

        add_win = tk.Toplevel(self)
        add_win.title("Add Feature")
        ttk.Label(add_win, text="Feature Name:").grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar()
        ttk.Entry(add_win, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(add_win, text="Top-Level Category (optional):").grid(row=1, column=0, padx=5, pady=5)
        general_var = tk.StringVar()
        ttk.Entry(add_win, textvariable=general_var).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(add_win, text="Save", command=save_new).grid(row=2, column=0, columnspan=2, pady=10)


    def edit_feature(self):
        """Edit the selected feature."""
        selection = self.feature_tree.selection()
        if not selection:
            messagebox.showwarning("Select Feature", "Please select a feature to edit.")
            return
        feature_id = int(selection[0])

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, general FROM feature_mappings WHERE id=?", (feature_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return

        def save_edit():
            new_name = name_var.get().strip()
            new_general = general_var.get().strip() or new_name
            if not new_name:
                messagebox.showwarning("Invalid", "Feature name cannot be empty.")
                return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE feature_mappings SET name=?, general=? WHERE id=?", (new_name, new_general, feature_id))
            conn.commit()
            conn.close()
            self.load_feature_tree()
            edit_win.destroy()

        edit_win = tk.Toplevel(self)
        edit_win.title("Edit Feature")
        ttk.Label(edit_win, text="Feature Name:").grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar(value=row[0])
        ttk.Entry(edit_win, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(edit_win, text="Top-Level Category (optional):").grid(row=1, column=0, padx=5, pady=5)
        general_var = tk.StringVar(value=row[1])
        ttk.Entry(edit_win, textvariable=general_var).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(edit_win, text="Save", command=save_edit).grid(row=2, column=0, columnspan=2, pady=10)


    def remove_feature(self):
        """Remove a feature and all its children recursively."""
        selection = self.feature_tree.selection()
        if not selection:
            messagebox.showwarning("Select Feature", "Please select a feature to remove.")
            return
        feature_id = int(selection[0])
        if not messagebox.askyesno("Confirm Delete", "Delete this feature and all sub-features?"):
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        def delete_recursive(fid):
            c.execute("SELECT id FROM feature_mappings WHERE parent_id=?", (fid,))
            for (child_id,) in c.fetchall():
                delete_recursive(child_id)
            c.execute("DELETE FROM feature_mappings WHERE id=?", (fid,))

        delete_recursive(feature_id)
        conn.commit()
        conn.close()
        self.load_feature_tree()


    # --- Location Mappings Sub-tab ---
    def build_location_tab(self):
        import tkinter as tk
        from tkinter import ttk

        if hasattr(self, 'location_frame'):
            self.location_frame.destroy()

        self.location_frame = ttk.Frame(self.mappings_tab)
        self.location_frame.pack(fill="both", expand=True)

        location_tree = self.load_location_tree()

        self.location_treeview = ttk.Treeview(self.location_frame)
        self.location_treeview.pack(fill="both", expand=True)

        for general, specifics in location_tree.items():
            general_id = self.location_treeview.insert("", "end", text=general)
            for specific in specifics:
                self.location_treeview.insert(general_id, "end", text=specific)


    def load_location_tree(self):
        """
        Load the location hierarchy from the database.
        Returns a dict: {general_location: [specific_locations]}
        """
        import sqlite3

        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute("SELECT specific, general FROM location_mappings")
        rows = c.fetchall()
        conn.close()

        location_tree = {}
        for specific, general in rows:
            if general not in location_tree:
                location_tree[general] = []
            location_tree[general].append(specific)

        return location_tree


    def add_location(self):
        """Add a new location under a selected parent."""
        selection = self.location_tree.selection()
        parent_id = int(selection[0]) if selection else None

        def save_new():
            name = name_var.get().strip()
            general = general_var.get().strip() or name
            if not name:
                messagebox.showwarning("Invalid", "Location name cannot be empty.")
                return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO location_mappings (name, parent_id, general) VALUES (?, ?, ?)",
                    (name, parent_id, general))
            conn.commit()
            conn.close()
            self.load_location_tree()
            add_win.destroy()

        add_win = tk.Toplevel(self)
        add_win.title("Add Location")
        ttk.Label(add_win, text="Location Name:").grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar()
        ttk.Entry(add_win, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(add_win, text="Top-Level Category (optional):").grid(row=1, column=0, padx=5, pady=5)
        general_var = tk.StringVar()
        ttk.Entry(add_win, textvariable=general_var).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(add_win, text="Save", command=save_new).grid(row=2, column=0, columnspan=2, pady=10)


    def edit_location(self):
        """Edit the selected location."""
        selection = self.location_tree.selection()
        if not selection:
            messagebox.showwarning("Select Location", "Please select a location to edit.")
            return
        loc_id = int(selection[0])

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, general FROM location_mappings WHERE id=?", (loc_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return

        def save_edit():
            new_name = name_var.get().strip()
            new_general = general_var.get().strip() or new_name
            if not new_name:
                messagebox.showwarning("Invalid", "Location name cannot be empty.")
                return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE location_mappings SET name=?, general=? WHERE id=?", (new_name, new_general, loc_id))
            conn.commit()
            conn.close()
            self.load_location_tree()
            edit_win.destroy()

        edit_win = tk.Toplevel(self)
        edit_win.title("Edit Location")
        ttk.Label(edit_win, text="Location Name:").grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar(value=row[0])
        ttk.Entry(edit_win, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(edit_win, text="Top-Level Category (optional):").grid(row=1, column=0, padx=5, pady=5)
        general_var = tk.StringVar(value=row[1])
        ttk.Entry(edit_win, textvariable=general_var).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(edit_win, text="Save", command=save_edit).grid(row=2, column=0, columnspan=2, pady=10)


    def remove_location(self):
        """Remove a location and all its children recursively."""
        selection = self.location_tree.selection()
        if not selection:
            messagebox.showwarning("Select Location", "Please select a location to remove.")
            return
        loc_id = int(selection[0])
        if not messagebox.askyesno("Confirm Delete", "Delete this location and all sub-locations?"):
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        def delete_recursive(lid):
            c.execute("SELECT id FROM location_mappings WHERE parent_id=?", (lid,))
            for (child_id,) in c.fetchall():
                delete_recursive(child_id)
            c.execute("DELETE FROM location_mappings WHERE id=?", (lid,))

        delete_recursive(loc_id)
        conn.commit()
        conn.close()
        self.load_location_tree()

    def search_entries(self):
        """Search the database for matching entries based on the search fields."""
        # Clear previous results
        self.edit_results_list.delete(0, tk.END)

        species = self.edit_species_var.get().strip()
        date_taken = self.edit_date_var.get().strip()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        query = "SELECT id, species, date_taken FROM photos WHERE 1=1"
        params = []

        if species:
            query += " AND species LIKE ?"
            params.append(f"%{species}%")
        if date_taken:
            query += " AND date_taken LIKE ?"
            params.append(f"%{date_taken}%")

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        for row in rows:
            self.edit_results_list.insert(tk.END, f"{row[0]} | {row[1]} | {row[2]}")

    def load_selected_entry(self, event):
        """Load the selected entry's metadata into the editable fields."""
        selection = self.edit_results_list.curselection()
        if not selection:
            return

        entry_text = self.edit_results_list.get(selection[0])
        entry_id = int(entry_text.split("|")[0].strip())

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM photos WHERE id=?", (entry_id,))
        row = c.fetchone()
        conn.close()

        if row:
            # Map columns to fields
            self.edit_species_entry.delete(0, tk.END)
            self.edit_species_entry.insert(0, row[1])
            self.edit_feature_entry.delete(0, tk.END)
            self.edit_feature_entry.insert(0, row[4])
            self.edit_location_entry.delete(0, tk.END)
            self.edit_location_entry.insert(0, row[10])
            self.edit_date_entry.delete(0, tk.END)
            self.edit_date_entry.insert(0, row[6])
            self.edit_topaz_var.set(bool(row[7]))
            self.edit_raw_var.set(row[15] or "")
            self.edit_processed_var.set(row[12] or "")

            self.current_edit_id = entry_id  # store which entry we are editing

    def browse_edit_raw(self):
        """Select new raw files for the entry."""
        files = filedialog.askopenfilenames(title="Select Raw Files", filetypes=[("Camera RAW", "*.CR2 *.NEF *.ARW *.DNG *.RAF")])
        if files:
            self.edit_raw_var.set(";".join(files))

    def browse_edit_processed(self):
        """Select a processed file for the entry."""
        file = filedialog.askopenfilename(title="Select Processed File", filetypes=[("Images", "*.jpg *.png *.jpeg *.tiff *.tif")])
        if file:
            self.edit_processed_var.set(file)

    def save_edited_entry(self):
        """Save the edited metadata and file paths back to the database."""
        if not hasattr(self, "current_edit_id"):
            messagebox.showwarning("No Selection", "Please select an entry to edit.")
            return

        species = self.edit_species_entry.get().strip()
        feature = self.edit_feature_entry.get().strip()
        location = self.edit_location_entry.get().strip()
        date_taken = self.edit_date_entry.get().strip()
        used_topaz = int(self.edit_topaz_var.get())
        raw_paths = self.edit_raw_var.get()
        processed_file = self.edit_processed_var.get()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            UPDATE photos
            SET species=?, main_feature=?, location=?, date_taken=?, used_topaz=?, raw_paths=?, processed_filename=?
            WHERE id=?
        """, (species, feature, location, date_taken, used_topaz, raw_paths, processed_file, self.current_edit_id))
        conn.commit()
        conn.close()

        messagebox.showinfo("Saved", "Entry updated successfully.")
        self.search_entries()  # refresh list after update


    def browse_file(self):
        """Open a file dialog to select an image, update the entry and preview."""
        file_path = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if file_path:
            self.proc_path_var.set(file_path)  # Update the entry field
            # Update the preview image
            try:
                img = Image.open(file_path)
                img.thumbnail((200, 200))
                self.preview_image = ImageTk.PhotoImage(img)
                self.preview_label.config(image=self.preview_image)
            except Exception as e:
                messagebox.showerror("Error", f"Could not open image:\n{e}")


    def browse_processed(self):
        p = filedialog.askopenfilename(title="Select processed image",
                                    filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("All files", "*.*")])
        if p:
            self.proc_path_var.set(p)
            self.show_thumbnail(p)
            self.update_preview()
            # try to auto-fill date from file mtime (fallback)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p)).date().isoformat()
                if not self.date_var.get():
                    self.date_var.set(mtime)
            except Exception:
                pass

    def browse_raw(self):
        ps = filedialog.askopenfilenames(title="Select raw files (can choose multiple)",
                                        filetypes=[("Raw/Images", "*.CR2 *.NEF *.ARW *.dng *.raf *.rw2 *.tif *.tiff *.DNG *.ORF"), ("All files", "*.*")])
        for p in ps:
            if p not in self.raw_listbox.get(0, 'end'):
                self.raw_listbox.insert("end", p)
                self.raw_files_text.insert("end", p + "\n")

    def remove_selected_raw(self):
        sel = self.raw_listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            self.raw_listbox.delete(i)
        self.raw_files_text.delete("1.0", "end")
        for i in range(self.raw_listbox.size()):
            self.raw_files_text.insert("end", self.raw_listbox.get(i) + "\n")

    def show_thumbnail(self, path):
        try:
            img = Image.open(path)
            img.thumbnail(THUMB_SIZE)
            self.current_thumb = ImageTk.PhotoImage(img)
            self.thumb_label.configure(image=self.current_thumb, text="")
        except Exception as e:
            self.thumb_label.configure(image="", text=f"Preview not available\n{e}")

    def update_preview(self):
        """
        Updates the image preview safely.
        """
        path = self.proc_path_var.get()
        if not path or not os.path.exists(path):
            # Clear the preview if file missing
            self.preview_label.config(image='')
            return

        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((250, 250))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Could not load image:\n{e}")

    def save_entry(self):
        """
        Safely saves the current entry to the database.
        """
        proc_path = self.proc_path_var.get()
        if not proc_path or not os.path.exists(proc_path):
            messagebox.showerror("Error", "Processed image path is invalid or missing.")
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO photos
                        (species, species_code, gfib_link, main_feature, feature_code,
                        date_taken, used_topaz, subject_size, other_features,
                        location, location_code, processed_filename, processed_path,
                        raw_attached, raw_paths, raw_mode, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.species_var.get(),
                    self.species_var.get().upper(),
                    self.gfib_var.get(),
                    self.feature_var.get(),
                    self.feature_var.get().upper(),
                    self.date_var.get(),
                    self.topaz_var.get(),
                    self.size_var.get(),
                    self.other_var.get(),
                    self.loc_var.get(),
                    self.loc_var.get().upper(),
                    os.path.basename(proc_path),
                    proc_path,
                    1 if self.raw_listbox.size() > 0 else 0,
                    ",".join(self.raw_listbox.get(0, tk.END)),
                    "copy" if self.copy_raw_var.get() else "link",
                    datetime.now().isoformat()
                    ))
            conn.commit()
            messagebox.showinfo("Success", "Entry saved successfully!")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to save entry:\n{e}")
        finally:
            conn.close()

    def clear_add_form(self):
        self.proc_path_var.set("")
        self.raw_listbox.delete(0, 'end')
        self.raw_files_text.delete("1.0", "end")
        for var in ("species_var", "gfib_var", "feature_var", "date_var", "size_var", "other_var", "loc_var"):
            getattr(self, var).set("")
        self.topaz_var.set(0)
        self.preview_var.set("")
        self.thumb_label.configure(image="", text="")
        self.note_preview.delete("1.0", "end")
        self.copy_raw_var.set(1)




    
# ---------------------
# Search Tab
# ---------------------
    def build_search_tab(self):
        frm = self.search_frame
        topfrm = ttk.Frame(frm, padding=8)
        midfrm = ttk.Frame(frm, padding=8)
        bottomfrm = ttk.Frame(frm, padding=8)
        topfrm.pack(fill="x")
        midfrm.pack(fill="both", expand=True)
        bottomfrm.pack(fill="x")

        # Filters
        ttk.Label(topfrm, text="Species:").grid(row=0, column=0, sticky="w")
        self.s_search = tk.StringVar()
        ttk.Entry(topfrm, textvariable=self.s_search, width=20).grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(topfrm, text="Feature:").grid(row=0, column=2, sticky="w")
        self.f_search = tk.StringVar()
        ttk.Entry(topfrm, textvariable=self.f_search, width=20).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(topfrm, text="Date from (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=6)
        self.date_from = tk.StringVar()
        ttk.Entry(topfrm, textvariable=self.date_from, width=12).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(topfrm, text="to:").grid(row=1, column=2, sticky="w")
        self.date_to = tk.StringVar()
        ttk.Entry(topfrm, textvariable=self.date_to, width=12).grid(row=1, column=3, sticky="w", padx=4)

        self.topaz_search_var = tk.IntVar(value=0)
        ttk.Checkbutton(topfrm, text="Topaz only", variable=self.topaz_search_var).grid(row=0, column=4, padx=12)

        ttk.Label(topfrm, text="Free text (other features):").grid(row=1, column=4, sticky="w")
        self.free_text = tk.StringVar()
        ttk.Entry(topfrm, textvariable=self.free_text, width=30).grid(row=1, column=5, sticky="w", padx=4)

        ttk.Button(topfrm, text="Search", command=self.populate_search_results).grid(row=0, column=6, padx=6)
        ttk.Button(topfrm, text="Reset", command=self.reset_search).grid(row=1, column=6, padx=6)

        # Results Treeview
        cols = ("id", "species", "date_taken", "main_feature", "used_topaz", "processed_filename", "raw_attached", "raw_mode")
        self.res_tree = ttk.Treeview(midfrm, columns=cols, show="headings", selectmode="browse")
        widths = {"id":60, "species":160, "date_taken":100, "main_feature":120, "used_topaz":80, "processed_filename":260, "raw_attached":100, "raw_mode":100}
        for c in cols:
            self.res_tree.heading(c, text=c.replace("_", " ").title())
            self.res_tree.column(c, width=widths.get(c, 120), anchor="w")
        self.res_tree.pack(fill="both", expand=True)
        self.res_tree.bind("<Double-1>", self.open_selected_processed)

        # Bottom: preview & actions
        self.search_preview = ttk.Label(bottomfrm, text="Double-click a result to open the processed image.")
        self.search_preview.pack(side="left", padx=6)

        ttk.Button(bottomfrm, text="Open Processed", command=self.open_selected_processed).pack(side="right", padx=6)
        ttk.Button(bottomfrm, text="Open Raw Folder / Files", command=self.open_selected_raw_folder).pack(side="right", padx=6)
        ttk.Button(bottomfrm, text="Export Results CSV", command=self.export_search_csv).pack(side="right", padx=6)

    def reset_search(self):
        self.s_search.set("")
        self.f_search.set("")
        self.date_from.set("")
        self.date_to.set("")
        self.topaz_search_var.set(0)
        self.free_text.set("")
        self.populate_search_results()

    def populate_search_results(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        query = "SELECT id, species, date_taken, main_feature, used_topaz, processed_filename, raw_attached, raw_mode FROM photos WHERE 1=1"
        params = []
        if self.s_search.get().strip():
            query += " AND species LIKE ?"
            params.append(f"%{self.s_search.get().strip()}%")
        if self.f_search.get().strip():
            query += " AND main_feature LIKE ?"
            params.append(f"%{self.f_search.get().strip()}%")
        if self.topaz_search_var.get():
            query += " AND used_topaz = 1"
        if self.free_text.get().strip():
            query += " AND other_features LIKE ?"
            params.append(f"%{self.free_text.get().strip()}%")
        df = self.date_from.get().strip()
        dt = self.date_to.get().strip()
        if df:
            try:
                datetime.datetime.strptime(df, "%Y-%m-%d")
                query += " AND date(date_taken) >= date(?)"
                params.append(df)
            except Exception:
                pass
        if dt:
            try:
                datetime.datetime.strptime(dt, "%Y-%m-%d")
                query += " AND date(date_taken) <= date(?)"
                params.append(dt)
            except Exception:
                pass

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        for i in self.res_tree.get_children():
            self.res_tree.delete(i)
        for r in rows:
            self.res_tree.insert("", "end", values=r)

    def open_selected_processed(self, event=None):
        sel = self.res_tree.selection()
        if not sel:
            return
        item = self.res_tree.item(sel[0])["values"]
        if not item:
            return
        pk = item[0]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT processed_path FROM photos WHERE id=?", (pk,))
        row = c.fetchone()
        conn.close()
        if row:
            open_path(row[0])

    def open_selected_raw_folder(self):
        sel = self.res_tree.selection()
        if not sel:
            return
        item = self.res_tree.item(sel[0])["values"]
        if not item:
            return
        pk = item[0]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT raw_paths, raw_mode FROM photos WHERE id=?", (pk,))
        row = c.fetchone()
        conn.close()
        if not row or not row[0]:
            messagebox.showinfo("No raw files", "No raw files attached for this entry.")
            return
        raw_paths = row[0].split("|")
        raw_mode = row[1] if row[1] else "referenced"
        if raw_mode == "copied":
            # open the folder containing the first raw copy
            folder = os.path.dirname(raw_paths[0])
            open_path(folder)
        else:
            # referenced: open the first raw file directly
            open_path(raw_paths[0])

    def export_search_csv(self):
        sel_rows = self.res_tree.get_children()
        if not sel_rows:
            messagebox.showinfo("No results", "No results to export.")
            return
        save_path = filedialog.asksaveasfilename(title="Export CSV", defaultextension=".csv",
                                                filetypes=[("CSV", "*.csv")])
        if not save_path:
            return
        # build export list from the search query constraints
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        query = "SELECT * FROM photos WHERE 1=1"
        params = []
        if self.s_search.get().strip():
            query += " AND species LIKE ?"
            params.append(f"%{self.s_search.get().strip()}%")
        if self.f_search.get().strip():
            query += " AND main_feature LIKE ?"
            params.append(f"%{self.f_search.get().strip()}%")
        if self.topaz_search_var.get():
            query += " AND used_topaz = 1"
        if self.free_text.get().strip():
            query += " AND other_features LIKE ?"
            params.append(f"%{self.free_text.get().strip()}%")
        df = self.date_from.get().strip()
        dt = self.date_to.get().strip()
        if df:
            try:
                datetime.datetime.strptime(df, "%Y-%m-%d")
                query += " AND date(date_taken) >= date(?)"
                params.append(df)
            except Exception:
                pass
        if dt:
            try:
                datetime.datetime.strptime(dt, "%Y-%m-%d")
                query += " AND date(date_taken) <= date(?)"
                params.append(dt)
            except Exception:
                pass
        c.execute(query, params)
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        conn.close()
        try:
            with open(save_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(cols)
                for r in rows:
                    writer.writerow(r)
            messagebox.showinfo("Exported", f"Exported {len(rows)} rows to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

# ---------------------
# DB View Tab
# ---------------------
    def build_db_tab(self):
        frm = self.db_frame
        top = ttk.Frame(frm, padding=6)
        bottom = ttk.Frame(frm, padding=6)
        top.pack(fill="x")
        bottom.pack(fill="both", expand=True)
        ttk.Button(top, text="Refresh", command=self.populate_db_view).pack(side="left")
        ttk.Button(top, text="Compact DB (VACUUM)", command=self.vacuum_db).pack(side="left", padx=6)
        ttk.Button(top, text="Open processed folder", command=lambda: open_path(PROCESSED_DIR)).pack(side="left", padx=6)
        ttk.Button(top, text="Open raw folder", command=lambda: open_path(RAW_DIR)).pack(side="left", padx=6)



        cols = ("id", "species", "date_taken", "main_feature", "used_topaz", "processed_filename", "raw_attached", "raw_mode")
        self.db_tree = ttk.Treeview(bottom, columns=cols, show="headings")
        widths = {"id":60, "species":160, "date_taken":100, "main_feature":120, "used_topaz":80, "processed_filename":260, "raw_attached":100, "raw_mode":100}
        for c in cols:
            self.db_tree.heading(c, text=c.replace("_", " ").title())
            self.db_tree.column(c, width=widths.get(c, 130), anchor="w")
        self.db_tree.pack(fill="both", expand=True)
        self.db_tree.bind("<Double-1>", self.db_open_processed)

    def populate_db_view(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, species, date_taken, main_feature, used_topaz, processed_filename, raw_attached, raw_mode FROM photos ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        for i in self.db_tree.get_children():
            self.db_tree.delete(i)
        for r in rows:
            self.db_tree.insert("", "end", values=r)
        # Also refresh search results
        self.populate_search_results()

    def db_open_processed(self, event=None):
        sel = self.db_tree.selection()
        if not sel:
            return
        item = self.db_tree.item(sel[0])["values"]
        if not item:
            return
        pk = item[0]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT processed_path FROM photos WHERE id=?", (pk,))
        row = c.fetchone()
        conn.close()
        if row:
            open_path(row[0])

    def vacuum_db(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("VACUUM")
        conn.commit()
        conn.close()
        messagebox.showinfo("Vacuum", "Database vacuumed.")

# -------------------------
# Misc helpers
# -------------------------
def safe_filename_prefix(s):
    s = s or "UNDEF"
    s = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')
    return s[:16]

# -------------------------
# Run
# -------------------------
def main():
    if not DB_FILE:
        print("No database selected or created. Exiting.")
        sys.exit(0)

    app = PlantPhotoManager(DB_FILE)
    app.mainloop()
    print("[DEBUG] Tk root created.")

    # Load mappings in a background thread
    def load_mappings_bg():
        global FEATURE_MAP, LOCATION_MAP
        print("[DEBUG] Loading mappings into memory...")
        FEATURE_MAP, LOCATION_MAP = load_specific_mappings(DB_FILE)
        print(f"[DEBUG] Feature mappings loaded: {len(FEATURE_MAP)}")
        print(f"[DEBUG] Location mappings loaded: {len(LOCATION_MAP)}")
        # If GUI needs updates, schedule safely:
        app.after(0, lambda: print("[DEBUG] Mappings loaded callback executed"))

    import threading
    threading.Thread(target=load_mappings_bg, daemon=True).start()

    app.mainloop()

if __name__ == "__main__":
    main()