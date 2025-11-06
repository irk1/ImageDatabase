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
from tkinter import ttk, filedialog, simpledialog, messagebox
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
    """Initialize all required database tables with correct schema."""
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

    # ✅ Correct Feature Mappings (with feature_name)
    c.execute('''
        CREATE TABLE IF NOT EXISTS feature_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_name TEXT NOT NULL,
            parent_id INTEGER,
            general TEXT,
            FOREIGN KEY (parent_id) REFERENCES feature_mappings(id)
        )
    ''')

    # Location Mappings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS location_mappings (
            location_name TEXT PRIMARY KEY,
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

    # Photos table (unchanged)
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

    # Feature mappings table with hierarchy
    c.execute('''
        CREATE TABLE IF NOT EXISTS feature_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_name TEXT NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY (parent_id) REFERENCES feature_mappings(id)
        )
    ''')

    # Location mappings table (unchanged)
    c.execute('''
        CREATE TABLE IF NOT EXISTS location_mappings (
            location_name TEXT PRIMARY KEY,
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
    """Load hierarchical feature mappings into dictionaries for use elsewhere."""
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    # Always ensure the table exists before querying
    c.execute("""
        CREATE TABLE IF NOT EXISTS feature_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_name TEXT NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY (parent_id) REFERENCES feature_mappings(id)
        )
    """)
    conn.commit()

    # Now it is safe to query
    c.execute("SELECT id, feature_name, parent_id FROM feature_mappings")
    rows = c.fetchall()
    conn.close()

    # Build in-memory maps
    FEATURE_MAP = {}
    LOCATION_MAP = {}

    for row_id, feature_name, parent_id in rows:
        FEATURE_MAP[row_id] = parent_id
        if parent_id is not None:
            LOCATION_MAP.setdefault(parent_id, []).append(row_id)

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
        feature_name TEXT NOT NULL,
        parent_id INTEGER,
        general TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS location_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_name TEXT NOT NULL,
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
        init_db_if_missing(self.db_file)

        self.conn = sqlite3.connect(self.db_file)
        self.conn.row_factory = sqlite3.Row  # optional: access rows by column name

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
        """Create the main Mappings tab with sub-tabs for Features and Locations."""
        # Main frame for Mappings
        mappings_frame = ttk.Frame(self.notebook)
        self.notebook.add(mappings_frame, text="Mappings")

        # Sub-notebook for Features and Locations
        self.mappings_sub_notebook = ttk.Notebook(mappings_frame)
        self.mappings_sub_notebook.pack(fill="both", expand=True)

        # Build feature and location sub-tabs
        self.build_feature_tab()
        self.build_location_tab()

    def build_feature_tab(self):
        self.ensure_feature_table()
        """Create the hierarchical feature tree tab with unrestricted depth."""
        feature_frame = ttk.Frame(self.mappings_sub_notebook)
        self.mappings_sub_notebook.add(feature_frame, text="Features")

        # Treeview for hierarchical features
        self.feature_tree = ttk.Treeview(feature_frame)
        self.feature_tree.pack(fill="both", expand=True)

        # Recursive function to populate tree from database
        def populate_tree(parent_id=None, parent_row=None):
            cursor = self.conn.cursor()
            if parent_row is None:
                cursor.execute("SELECT id, feature_name FROM feature_mappings WHERE parent_id IS NULL")
            else:
                cursor.execute("SELECT id, feature_name FROM feature_mappings WHERE parent_id = ?", (parent_row,))

            for row_id, name in cursor.fetchall():
                # Convert parent_id to string for Tkinter, or use "" for top-level
                tree_parent = str(parent_id) if parent_id else ""
                item_id = self.feature_tree.insert(tree_parent, "end", text=name, values=(row_id,))
                populate_tree(item_id, row_id)


        # Fill tree
        populate_tree()

        # Button frame
        btn_frame = ttk.Frame(feature_frame)
        btn_frame.pack(fill="x", pady=6)

        # Control buttons
        ttk.Button(btn_frame, text="Add Feature", command=self.add_feature).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Edit Feature", command=self.edit_feature).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Insert Between", command=self.insert_between_feature).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remove Feature", command=self.remove_feature).pack(side="left", padx=4)

    def populate_tree(self):
        """Populate the feature hierarchy Treeview."""
        self.feature_tree.delete(*self.feature_tree.get_children())
        c = self.conn.cursor()

        # Ensure table exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS feature_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY(parent_id) REFERENCES feature_mappings(id)
            )
        ''')

        # Load features
        c.execute("SELECT id, feature_name, parent_id FROM feature_mappings")
        rows = c.fetchall()

        # Build lookup for hierarchy
        children = {}
        for row_id, name, parent_id in rows:
            children.setdefault(parent_id, []).append((row_id, name))

        def insert_children(parent_id, tree_parent=""):
            for row_id, name in children.get(parent_id, []):
                item_id = self.feature_tree.insert(tree_parent, "end", text=name, values=(row_id,))
                insert_children(row_id, item_id)

        insert_children(None)

    def ensure_feature_table(self):
        """Ensure the feature_mappings table exists and has proper columns."""
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS feature_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY(parent_id) REFERENCES feature_mappings(id)
            )
        """)
        self.conn.commit()


    def build_location_tab(self):
        """Create the hierarchical location tree tab."""
        location_frame = ttk.Frame(self.mappings_sub_notebook)
        self.mappings_sub_notebook.add(location_frame, text="Locations")

        self.location_treeview = ttk.Treeview(location_frame)
        self.location_treeview.pack(fill="both", expand=True)

        # Load all locations from DB
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("SELECT id, location_name, parent_id FROM location_mappings")
        rows = c.fetchall()
        conn.close()

        # Build a parent-child mapping
        children = {}
        for loc_id, name, parent_id in rows:
            children.setdefault(parent_id, []).append((loc_id, name))

        # Recursive function to insert into Treeview
        def insert_children(parent_id, tree_parent=""):
            for loc_id, name in children.get(parent_id, []):
                item_id = self.location_treeview.insert(tree_parent, "end", text=name, values=(loc_id,))
                insert_children(loc_id, item_id)

        insert_children(None)  # Start from top-level (parent_id is NULL)

        # Buttons
        btn_frame = ttk.Frame(location_frame)
        btn_frame.pack(fill="x", pady=6)
        ttk.Button(btn_frame, text="Add Location", command=self.add_location).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Edit Location", command=self.edit_location).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remove Location", command=self.remove_location).pack(side="left", padx=4)


    def load_feature_tree(self):
        """Load features into a dictionary for building the tree."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("SELECT id, feature_name FROM feature_mappings")
        rows = c.fetchall()
        conn.close()

        feature_dict = {}
        for row_id, feature_name, parent_id in rows:
            feature_dict.setdefault(parent_id, []).append((row_id, feature_name))
        return feature_dict


    def add_feature(self):
        """Add a new feature with optional parent and child relationships."""
        add_win = tk.Toplevel(self)
        add_win.title("Add Feature")
        add_win.geometry("350x220")

        # Feature name input
        tk.Label(add_win, text="New Feature Name:").pack(pady=5)
        name_entry = ttk.Entry(add_win, width=30)
        name_entry.pack()

        # Fetch existing features
        c = self.conn.cursor()
        c.execute("SELECT id, feature_name FROM feature_mappings ORDER BY feature_name")
        features = c.fetchall()
        feature_names = ["(None)"] + [f[1] for f in features]
        feature_ids = [None] + [f[0] for f in features]

        # Parent feature dropdown
        tk.Label(add_win, text="Parent Feature:").pack(pady=5)
        parent_var = tk.StringVar(value="(None)")
        parent_combo = ttk.Combobox(add_win, textvariable=parent_var, values=feature_names, state="readonly")
        parent_combo.pack()

        # Optional child feature dropdown
        tk.Label(add_win, text="Child Feature:").pack(pady=5)
        child_var = tk.StringVar(value="(None)")
        child_combo = ttk.Combobox(add_win, textvariable=child_var, values=feature_names, state="readonly")
        child_combo.pack()

        def save_new_feature():
            feature_name = name_entry.get().strip()
            if not feature_name:
                messagebox.showerror("Error", "Feature name cannot be empty.")
                return

            # Determine parent_id
            parent_idx = feature_names.index(parent_var.get())
            parent_id = feature_ids[parent_idx]

            # Insert new feature
            c = self.conn.cursor()
            c.execute(
                "INSERT INTO feature_mappings (feature_name, parent_id) VALUES (?, ?)",
                (feature_name, parent_id)
            )
            new_id = c.lastrowid

            # Update child feature if specified
            child_idx = feature_names.index(child_var.get())
            child_id = feature_ids[child_idx]
            if child_id:
                c.execute(
                    "UPDATE feature_mappings SET parent_id=? WHERE id=?",
                    (new_id, child_id)
                )

            self.conn.commit()
            self.populate_tree()
            add_win.destroy()

        ttk.Button(add_win, text="Save", command=save_new_feature).pack(pady=15)

    def edit_feature(self):
        """Edit a selected feature in the hierarchical tree."""
        selection = self.feature_tree.selection()
        if not selection:
            messagebox.showwarning("Select Feature", "Please select a feature to edit.")
            return

        selected_item = selection[0]
        feature_name = self.feature_tree.item(selected_item, "text")
        feature_id = int(self.feature_tree.item(selected_item, "values")[0])

        # Get current parent
        parent_item = self.feature_tree.parent(selected_item)
        current_parent_id = None
        if parent_item:
            current_parent_id = int(self.feature_tree.item(parent_item, "values")[0])

        # Build list of possible parents
        c = self.conn.cursor()
        c.execute("SELECT id, feature_name FROM feature_mappings WHERE id != ?", (feature_id,))
        rows = c.fetchall()
        parent_options = ["(None)"] + [row[1] for row in rows]
        parent_ids = [None] + [int(row[0]) for row in rows]

        # Build edit window
        edit_win = tk.Toplevel(self)
        edit_win.title("Edit Feature")
        edit_win.geometry("350x150")

        ttk.Label(edit_win, text="Feature Name:").pack(pady=5)
        name_var = tk.StringVar(value=feature_name)
        ttk.Entry(edit_win, textvariable=name_var).pack()

        ttk.Label(edit_win, text="Parent Feature:").pack(pady=5)
        parent_var = tk.StringVar()
        parent_combo = ttk.Combobox(edit_win, textvariable=parent_var, values=parent_options, state="readonly")
        parent_combo.pack()

        # Preselect current parent safely
        if current_parent_id and current_parent_id in parent_ids:
            parent_combo.current(parent_ids.index(current_parent_id))
        else:
            parent_combo.current(0)

        def save_edit():
            new_name = name_var.get().strip()
            parent_idx = parent_combo.current()
            new_parent_id = parent_ids[parent_idx]

            if not new_name:
                messagebox.showerror("Error", "Feature name cannot be empty.")
                return

            try:
                c = self.conn.cursor()
                c.execute(
                    "UPDATE feature_mappings SET feature_name=?, parent_id=? WHERE id=?",
                    (new_name, new_parent_id, feature_id)
                )
                self.conn.commit()
                self.refresh_feature_tree()
                edit_win.destroy()
            except Exception as e:
                messagebox.showerror("Database Error", f"Error updating feature:\n{e}")

        ttk.Button(edit_win, text="Save", command=save_edit).pack(pady=10)

    def insert_between_feature(self):
        """Insert a new feature between two existing ones in the hierarchy."""
        selected = self.feature_tree.selection()
        if not selected:
            messagebox.showwarning("No selection", "Select a feature to insert after.")
            return

        # Get the parent and index position
        selected_item = selected[0]
        parent_item = self.feature_tree.parent(selected_item)
        index = self.feature_tree.index(selected_item)

        # Ask for the new feature name
        new_name = simpledialog.askstring("Insert Feature", "Enter new feature name:")
        if not new_name:
            return

        # Insert it visually in the Treeview
        new_item = self.feature_tree.insert(parent_item, index + 1, text=new_name)

        # Insert into the database
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        try:
            # Get parent_id from Treeview item values
            parent_id = None
            if parent_item:
                parent_id = self.feature_tree.item(parent_item, "values")
                if parent_id:
                    parent_id = parent_id[0]  # Treeview stores values as a tuple

            c.execute(
                "INSERT INTO feature_mappings (feature_name, parent_id) VALUES (?, ?)",
                (new_name, parent_id)
            )
            conn.commit()

            # Update Treeview item with DB id
            new_id = c.lastrowid
            self.feature_tree.item(new_item, values=(new_id,))
        except Exception as e:
            messagebox.showerror("Database Error", f"Error inserting feature:\n{e}")
        finally:
            conn.close()


    def remove_feature(self):
        """Remove a selected feature and its children."""
        selection = self.feature_tree.selection()
        if not selection:
            messagebox.showwarning("Select Feature", "Please select a feature to remove.")
            return

        selected_item = selection[0]
        feature_id = self.feature_tree.item(selected_item, "values")[0]

        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this feature and all its sub-features?")
        if not confirm:
            return

        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # Recursive delete function to remove children first
        def delete_feature_recursive(fid):
            # Find children
            c.execute("SELECT id FROM feature_mappings WHERE parent_id=?", (fid,))
            child_ids = [row[0] for row in c.fetchall()]
            for child_id in child_ids:
                delete_feature_recursive(child_id)
            # Delete this feature
            c.execute("DELETE FROM feature_mappings WHERE id=?", (fid,))

        try:
            delete_feature_recursive(feature_id)
            conn.commit()
            self.refresh_feature_tree()
        except Exception as e:
            messagebox.showerror("Database Error", f"Error deleting feature:\n{e}")
        finally:
            conn.close()


    def refresh_feature_tree(self):
        """Rebuild the hierarchical feature tree from existing table."""
        self.feature_tree.delete(*self.feature_tree.get_children())
        c = self.conn.cursor()

        try:
            # Fetch all features
            c.execute("SELECT id, feature_name, parent_id FROM feature_mappings")
            rows = c.fetchall()
        except sqlite3.OperationalError as e:
            print("Database error:", e)
            return

        # Build a parent -> children mapping
        children = {}
        feature_names = {}
        for fid, name, parent_id in rows:
            children.setdefault(parent_id, []).append(fid)
            feature_names[fid] = name

        # Recursive function to insert tree nodes
        def insert_children(parent_id, tree_parent=""):
            for fid in children.get(parent_id, []):
                name = feature_names[fid]
                item_id = self.feature_tree.insert(tree_parent, "end", text=name, values=(fid,))
                insert_children(fid, item_id)

        # Start inserting from top-level (parent_id is None)
        insert_children(None)

    # --- Location Mappings Sub-tab ---
   
    def load_location_tree(self):
        """
        Load the location hierarchy from the database using the new schema.
        Returns a dict: {parent_id: [child_id, ...]} and a mapping of id -> name.
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute("SELECT id, location_name, parent_id FROM location_mappings")
            rows = c.fetchall()
        except sqlite3.OperationalError as e:
            print("Database error:", e)
            conn.close()
            return {}

        conn.close()

        # Build parent -> children mapping
        children = {}
        location_names = {}
        for loc_id, name, parent_id in rows:
            children.setdefault(parent_id, []).append(loc_id)
            location_names[loc_id] = name

        # Recursive function to build tree dict
        tree = {}

        def insert_children(parent_id, parent_name=None):
            for loc_id in children.get(parent_id, []):
                name = location_names[loc_id]
                if parent_name is None:
                    tree[name] = []
                    insert_children(loc_id, name)
                else:
                    tree[parent_name].append(name)
                    insert_children(loc_id, name)

        insert_children(None)  # Start from top-level locations
        return tree


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
    init_db_at(DB_FILE)
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