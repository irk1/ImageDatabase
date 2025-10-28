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
from PIL.ExifTags import TAGS
import sys
import platform
import subprocess
from tkinterdnd2 import DND_FILES, TkinterDnD
# -------------------------
# Configuration / Folders
# -------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(APP_DIR, "processed")
RAW_DIR = os.path.join(APP_DIR, "raw")
THUMB_SIZE = (320, 240)

# -------------------------
# Database file selection
# -------------------------
DEFAULT_DB_FILE = os.path.join(APP_DIR, "plant_photos.db")

def select_db_file():
    """
    Prompt user to select a database file on startup.
    Falls back to DEFAULT_DB_FILE if canceled.
    """
    try:
        from tkinter import filedialog, Tk
        # hide root window
        root = Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Select Plant Photo Database",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
        )
        root.destroy()
        if path:
            return path
    except Exception:
        pass
    return DEFAULT_DB_FILE

DB_FILE = select_db_file()

# Ensure processed/raw directories exist
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)


# -------------------------
# Database
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Main photos table
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
    # Feature mappings
    c.execute('''
        CREATE TABLE IF NOT EXISTS feature_mappings (
            specific_feature TEXT PRIMARY KEY,
            broad_category TEXT NOT NULL
        )
    ''')
    # Location mappings
    c.execute('''
        CREATE TABLE IF NOT EXISTS location_mappings (
            specific_location TEXT PRIMARY KEY,
            broad_category TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# -------------------------
# Compact Code Generators
# -------------------------
VOWELS = set("AEIOUaeiou")

def safe_code(s, length=4):
    """Make a short code from a species or location string."""
    if not s:
        return ("X" * length)[:length]
    s = re.sub(r'[^A-Za-z]', '', s)
    if not s:
        return ("X" * length)[:length]
    # Prefer consonants first
    consonants = "".join([c for c in s if c not in VOWELS])
    if len(consonants) >= length:
        return consonants[:length].upper()
    combined = consonants + "".join([c for c in s if c in VOWELS])
    return (combined[:length].upper()).ljust(length, "X")

# -------------------------
# Feature and Location Code Helpers with DB
# -------------------------

def feature_code(feat, db_conn=None):
    """Return 3-letter code using broad category mapping from DB or default mapping."""
    if not feat:
        return "UNK"
    m = feat.strip().lower()

    # Default broad categories
    default_mapping = {
        "flower": "FLW",
        "leaf": "LEF",
        "root": "ROT",
        "inflorescence": "INF",
        "habit": "HBT",
        "fruit": "FRT",
        "seed": "SED",
        "spike": "SPK",
        "bulb": "BLB",
        "pseudobulb": "PSB",
        "rhizome": "RHZ",
        "stem": "STM",
        "petiole": "PTL"
    }

    # Try default mapping first
    for k, v in default_mapping.items():
        if k in m:
            broad = k
            code = v
            break
    else:
        broad = None
        code = None

    # Use DB mapping if available
    if db_conn:
        cur = db_conn.cursor()
        cur.execute("SELECT broad_category FROM feature_mappings WHERE specific_feature=?", (m,))
        row = cur.fetchone()
        if row:
            broad = row[0]
            code = default_mapping.get(broad, "UNK")

    # If no mapping found, fallback
    if not code:
        code = "UNK"

    return code


def loc_code(loc, db_conn=None):
    """Return 2-3 letter code using broad category mapping from DB or default mapping."""
    if not loc:
        return "XX"
    m = loc.strip().lower()

    # Default mappings
    default_mapping = {
        "greenhouse": "GH",
        "lab": "LB",
        "garden": "GD",
        "wild": "WL",
        "mountain": "MT",
        "forest": "FR",
        "indoor": "IN",
        "nursery": "NY",
        "field": "FD"
    }

    code = None
    for k, v in default_mapping.items():
        if k in m:
            code = v
            break

    # Check DB mappings
    if db_conn:
        cur = db_conn.cursor()
        cur.execute("SELECT broad_category FROM location_mappings WHERE specific_location=?", (m,))
        row = cur.fetchone()
        if row:
            broad = row[0]
            code = default_mapping.get(broad, safe_code(loc, 3))

    # Fallback
    if not code:
        code = safe_code(loc, 3)

    return code.upper()

def short_hash(seed: str, chars=4):
    """Return a short hex from sha1 for collision-resistance."""
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return h[:chars].upper()

def gen_compact_filename(species, date_taken, main_feature, location, used_topaz, original_name, db_conn=None):
    spec_code = safe_code(species, 4)
    try:
        dt = datetime.datetime.strptime(date_taken, "%Y-%m-%d")
        date_str = dt.strftime("%d%m%y")
    except Exception:
        try:
            date_str = datetime.datetime.strptime(date_taken, "%d%m%y").strftime("%d%m%y")
        except Exception:
            date_str = datetime.date.today().strftime("%d%m%y")

    feat = feature_code(main_feature, db_conn=db_conn)
    loc = loc_code(location, db_conn=db_conn)
    ai_flag = "T" if used_topaz else "F"
    seed = f"{species}|{date_taken}|{main_feature}|{location}|{original_name}"
    hx = short_hash(seed, chars=4)
    fname = f"{spec_code}-{date_str}-{feat}-{loc}-{ai_flag}-{hx}.jpg"
    fname = re.sub(r'[^A-Za-z0-9._-]', '', fname)
    return fname, spec_code, feat, loc

# -------------------------
# Utils: open file in OS
# -------------------------
def open_path(path):
    if not path or not os.path.exists(path):
        messagebox.showerror("File not found", f"Path does not exist:\n{path}")
        return
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Open failed", str(e))

# -------------------------
# GUI Application
# -------------------------
class PlantPhotoManager(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Plant Photo Manager")
        self.geometry("900x600")

        # --- Initialize notebook ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Create tabs ---
        self.create_main_tab()   # Your main tab function
        self.create_raw_tab()    # The raw files tab with drag-and-drop

        # --- Initialize other components ---
        self.setup_database()    # Example: database setup
        self.load_initial_data() # Example: load initial data if needed

        # --- Any other initialization ---
        # self.some_other_setup()

    def create_raw_tab(self):
        """
        Create the Raw Files tab in the notebook and prepare it for drag-and-drop.
        """
        if not hasattr(self, 'notebook'):
            print("Error: Notebook widget does not exist.")
            return

        # Create the tab frame
        self.raw_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.raw_tab, text="Raw Files")

        # Example content: listbox to show dropped files
        self.raw_listbox = tk.Listbox(self.raw_tab, width=80, height=20)
        self.raw_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Enable drag-and-drop now that the tab exists
        self.enable_drag_and_drop()

    def enable_drag_and_drop(self):
        """
        Enable drag-and-drop support for the raw_tab to accept files.
        Requires the tkinterdnd2 module.
        """
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            print("tkinterdnd2 module not installed; drag-and-drop disabled.")
            return

        if hasattr(self, 'raw_tab') and self.raw_tab is not None:
            self.raw_tab.drop_target_register(DND_FILES)
            self.raw_tab.dnd_bind('<<Drop>>', self.handle_drop)
        else:
            print("Warning: raw_tab does not exist. Drag-and-drop not enabled.")

    def bulk_add_raw_selection(self, filepaths=None):
        """Add multiple raw files either via filedialog or drag-and-drop."""
        if filepaths is None:
            files = filedialog.askopenfilenames(
                title="Select raw image files",
                filetypes=[("Raw Images", "*.CR2 *.NEF *.ARW *.DNG"), ("All Files", "*.*")]
            )
        else:
            files = filepaths

        if not files:
            return

        for filepath in files:
            try:
                filename = os.path.basename(filepath)
                species = self.get_species_from_filename(filename)
                prefix = safe_filename_prefix(species)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                new_filename = f"{prefix}_{timestamp}_{filename}"
                dest_path = os.path.join(self.raw_dir, new_filename)
                shutil.copy2(filepath, dest_path)
                self.db_insert_raw_file(species, new_filename)
            except Exception as e:
                print(f"Error adding file {filepath}: {e}")

        # Prompt user for location and subject (applies to all selected files)
        def ask_user_inputs():
            dlg = tk.Toplevel(self)
            dlg.title("Bulk Raw Import Info")
            dlg.geometry("400x150")
            tk.Label(dlg, text="Location (greenhouse, wild, etc.)").pack(pady=5)
            loc_var = tk.StringVar()
            tk.Entry(dlg, textvariable=loc_var).pack(pady=5)
            tk.Label(dlg, text="Subject (flower, stamen, leaf, etc.)").pack(pady=5)
            subj_var = tk.StringVar()
            tk.Entry(dlg, textvariable=subj_var).pack(pady=5)

            submitted = tk.BooleanVar(value=False)
            def submit():
                if loc_var.get().strip() and subj_var.get().strip():
                    submitted.set(True)
                    dlg.destroy()
                else:
                    messagebox.showwarning("Missing info", "Please fill both fields.")

            tk.Button(dlg, text="Submit", command=submit).pack(pady=10)
            self.wait_window(dlg)
            if submitted.get():
                return loc_var.get().strip(), subj_var.get().strip()
            return None, None

        location, subject = ask_user_inputs()
        if not location or not subject:
            return

        # Process each selected file
        for f in files:
            # Extract date from EXIF if available
            date_taken = None
            try:
                img = Image.open(f)
                info = img._getexif() or {}
                for tag, value in info.items():
                    decoded = TAGS.get(tag, tag)
                    if decoded == "DateTimeOriginal":
                        date_taken = datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S").date().isoformat()
                        break
            except Exception:
                pass
            if not date_taken:
                date_taken = datetime.date.today().isoformat()

            # Pre-fill standard values for raw-only import
            species = "UNKNOWN"
            main_feat = "RAW"
            used_topaz = 0

            # Copy raw into managed RAW_DIR
            try:
                bn = os.path.basename(f)
                dest_name = f"{safe_filename_prefix(species)}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{bn}"
                dest_path = os.path.join(RAW_DIR, dest_name)
                shutil.copy2(f, dest_path)
                raw_attached = 1
                raw_mode = "copied"
            except Exception as e:
                messagebox.showwarning("Copy failed", f"Failed to copy {f}:\n{e}")
                continue

            # Insert into database
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO photos (
                    species, species_code, gfib_link, main_feature, feature_code, date_taken,
                    used_topaz, subject_size, other_features, location, location_code,
                    processed_filename, processed_path, raw_attached, raw_paths, raw_mode, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                species,
                safe_code(species, 4),
                "",
                main_feat,
                feature_code(main_feat),
                date_taken,
                used_topaz,
                subject,
                "",
                location,
                loc_code(location),
                "",
                "",  # no processed file
                raw_attached,
                dest_path,
                raw_mode,
                datetime.datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()

        messagebox.showinfo("Bulk Import Done", f"Added {len(files)} raw images with auto-filled metadata.")
   
        # -------------------------
    # Fetch previous values for autocomplete
    # -------------------------
    
        # -------------------------
    # Fetch previous values / autocomplete
    # -------------------------
    def get_previous_values(self, field):
        """Return a sorted list of distinct previous entries for a given metadata field,
        including specifics from the mapping tables if they exist."""
        if field not in ("species_var", "feature_var", "size_var", "other_var", "loc_var"):
            return []

        field_map = {
            "species_var": "species",
            "feature_var": "main_feature",
            "size_var": "subject_size",
            "other_var": "other_features",
            "loc_var": "location"
        }
        col = field_map.get(field)
        values = set()

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # Add values from photos table
            if col:
                c.execute(f"SELECT DISTINCT {col} FROM photos WHERE {col} IS NOT NULL AND {col} != ''")
                values.update(r[0] for r in c.fetchall() if r[0])

            # Add specifics from mappings tables
            if field == "feature_var":
                c.execute("SELECT specific_feature FROM feature_mappings")
                values.update(r[0] for r in c.fetchall() if r[0])
            elif field == "loc_var":
                c.execute("SELECT specific_location FROM location_mappings")
                values.update(r[0] for r in c.fetchall() if r[0])

            conn.close()
        except Exception:
            pass

        return sorted(values)


    # -------------------------
    # Autocomplete Entry Setup
    # -------------------------
    def setup_autocomplete(self, entry_widget, field_name):
        """Attach a basic autocomplete to a Tk Entry widget based on previous values."""
        values = self.get_previous_values(field_name)
        if not values:
            return

        def on_key_release(event):
            typed = entry_widget.get()
            entry_widget.tk.call("autocomplete::complete", entry_widget._w, typed)

        # create a Tcl autocomplete for simplicity
        self.tk.call("package", "require", "autocomplete")
        entry_widget.bind("<KeyRelease>", on_key_release)
        entry_widget.tk.call("autocomplete::setList", entry_widget._w, " ".join(values))

    
        

    def setup_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.add_frame = ttk.Frame(notebook)
        self.search_frame = ttk.Frame(notebook)
        self.db_frame = ttk.Frame(notebook)

        notebook.add(self.add_frame, text="Add New Entry")
        notebook.add(self.search_frame, text="Search / Filter")
        notebook.add(self.db_frame, text="Database View / Export")

        self.build_add_tab()
        self.build_search_tab()
        self.build_db_tab()

    # ---------------------
    # Add Tab
    # ---------------------
        # ---------------------
    # Add Tab
    # ---------------------
    def build_add_tab(self):
        frm = self.add_frame
        topfrm = ttk.Frame(frm, padding=8)
        midfrm = ttk.Frame(frm, padding=8)
        bottomfrm = ttk.Frame(frm, padding=8)
        topfrm.pack(fill="x")
        midfrm.pack(fill="both", expand=True)
        bottomfrm.pack(fill="x")

        # Variables
        self.proc_path_var = tk.StringVar()
        self.species_var = tk.StringVar()
        self.gfib_var = tk.StringVar()
        self.feature_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.size_var = tk.StringVar()
        self.other_var = tk.StringVar()
        self.loc_var = tk.StringVar()
        self.topaz_var = tk.IntVar(value=0)
        self.copy_raw_var = tk.IntVar(value=1)
        self.preview_var = tk.StringVar()

        # Top frame: main metadata
        ttk.Label(topfrm, text="Processed Image:").grid(row=0, column=0, sticky="w")
        ttk.Entry(topfrm, textvariable=self.proc_path_var, width=40).grid(row=0, column=1, sticky="w")
        ttk.Button(topfrm, text="Browse", command=self.browse_processed).grid(row=0, column=2, padx=4)

        ttk.Label(topfrm, text="Species:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.species_var, width=20).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(topfrm, text="GFIB link:").grid(row=1, column=2, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.gfib_var, width=25).grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(topfrm, text="Feature:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.feature_var, width=20).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(topfrm, text="Date taken (YYYY-MM-DD):").grid(row=2, column=2, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.date_var, width=15).grid(row=2, column=3, sticky="w", pady=4)

        ttk.Label(topfrm, text="Subject size:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.size_var, width=20).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(topfrm, text="Other features:").grid(row=3, column=2, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.other_var, width=25).grid(row=3, column=3, sticky="w", pady=4)

        ttk.Label(topfrm, text="Location:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(topfrm, textvariable=self.loc_var, width=20).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Checkbutton(topfrm, text="Topaz used", variable=self.topaz_var).grid(row=4, column=2, sticky="w", padx=4)
        ttk.Checkbutton(topfrm, text="Copy raw files", variable=self.copy_raw_var).grid(row=4, column=3, sticky="w", padx=4)

        # Mid frame: raw file selection
        raw_frame = ttk.LabelFrame(midfrm, text="Raw files")
        raw_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.raw_listbox = tk.Listbox(raw_frame, height=6)
        self.raw_listbox.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        self.raw_files_text = tk.Text(raw_frame, height=6, width=50)
        self.raw_files_text.pack(side="left", fill="both", expand=True, padx=2, pady=2)

        btn_frame = ttk.Frame(raw_frame)
        btn_frame.pack(side="left", fill="y", padx=2)
        ttk.Button(btn_frame, text="Add raw...", command=self.browse_raw).pack(pady=2)
        ttk.Button(btn_frame, text="Remove selected", command=self.remove_selected_raw).pack(pady=2)
        ttk.Button(btn_frame, text="Bulk import raw...", command=self.bulk_add_raw_selection).pack(pady=2)

        # Bottom frame: thumbnail, preview, save
        thumb_frame = ttk.LabelFrame(bottomfrm, text="Processed image preview")
        thumb_frame.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.thumb_label = ttk.Label(thumb_frame, text="No image selected")
        self.thumb_label.pack(fill="both", expand=True, padx=4, pady=4)

        preview_frame = ttk.Frame(bottomfrm)
        preview_frame.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        ttk.Label(preview_frame, text="Filename preview:").pack(anchor="w")
        ttk.Entry(preview_frame, textvariable=self.preview_var, width=40, state="readonly").pack(anchor="w", pady=2)
        ttk.Label(preview_frame, text="Notes preview:").pack(anchor="w", pady=(8,0))
        self.note_preview = tk.Text(preview_frame, height=5, width=50)
        self.note_preview.pack(fill="both", expand=True, pady=2)

        ttk.Button(bottomfrm, text="Save Entry", command=self.save_entry).pack(side="right", padx=4, pady=4)

    
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
                                         filetypes=[("Raw/Images", "*.CR2 *.NEF *.ARW *.dng *.raf *.rw2 *.tif *.tiff *.jpg *.jpeg *.png"), ("All files", "*.*")])
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
        species = self.species_var.get()
        date_taken = self.date_var.get() or datetime.date.today().isoformat()
        feat = self.feature_var.get()
        loc = self.loc_var.get()
        used_topaz = bool(self.topaz_var.get())
        original_name = os.path.basename(self.proc_path_var.get()) or "UNDEF"
        fname, spec_code, feat_code, locc = gen_compact_filename(species, date_taken, feat, loc, used_topaz, original_name)
        self.preview_var.set(fname)
        # simple quick note preview
        note_lines = [
            f"Species code: {spec_code}",
            f"Feature code: {feat_code}",
            f"Location code: {locc}",
            f"Topaz: {'Yes' if used_topaz else 'No'}",
        ]
        self.note_preview.delete("1.0", "end")
        self.note_preview.insert("end", "\n".join(note_lines))

    def save_entry(self):
        proc = self.proc_path_var.get()
        if not proc or not os.path.exists(proc):
            messagebox.showerror("Missing processed image", "Please select a processed image to save.")
            return

        species = self.species_var.get().strip()
        gfib = self.gfib_var.get().strip()
        main_feat = self.feature_var.get().strip()
        date_taken = self.date_var.get().strip() or datetime.date.today().isoformat()
        used_topaz = int(self.topaz_var.get())
        subject_size = self.size_var.get().strip()
        other = self.other_var.get().strip()
        location = self.loc_var.get().strip()
        raw_paths = [self.raw_listbox.get(i) for i in range(self.raw_listbox.size())]
        raw_attached = 1 if raw_paths else 0
        raw_mode = "copied" if self.copy_raw_var.get() else "referenced"

        fname, spec_code, feat_code, locc = gen_compact_filename(species, date_taken, main_feat, location, bool(used_topaz), os.path.basename(proc))

        # copy processed file to PROCESSED_DIR with fname (avoid overwriting)
        dest_proc = os.path.join(PROCESSED_DIR, fname)
        if os.path.exists(dest_proc):
            base, ext = os.path.splitext(fname)
            suffix = 1
            while os.path.exists(os.path.join(PROCESSED_DIR, f"{base}-{suffix}{ext}")):
                suffix += 1
            fname = f"{base}-{suffix}{ext}"
            dest_proc = os.path.join(PROCESSED_DIR, fname)
        try:
            shutil.copy2(proc, dest_proc)
        except Exception as e:
            messagebox.showerror("Copy failed", f"Failed to copy processed image:\n{e}")
            return

        # handle raw files: either copy into RAW_DIR or keep references
        handled_raw_paths = []
        for rp in raw_paths:
            if not os.path.exists(rp):
                # skip missing but alert
                messagebox.showwarning("Raw missing", f"Raw file not found, skipping:\n{rp}")
                continue
            if raw_mode == "copied":
                try:
                    bn = os.path.basename(rp)
                    prefix = safe_filename_prefix(species)
                    dest_name = f"{prefix}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{bn}"
                    dest = os.path.join(RAW_DIR, dest_name)
                    # ensure uniqueness
                    if os.path.exists(dest):
                        base, ext = os.path.splitext(dest)
                        c = 1
                        while os.path.exists(f"{base}_{c}{ext}"):
                            c += 1
                        dest = f"{base}_{c}{ext}"
                    shutil.copy2(rp, dest)
                    handled_raw_paths.append(dest)
                except Exception as e:
                    messagebox.showwarning("Raw copy warning", f"Failed to copy raw file {rp}:\n{e}")
                    # fallback to storing reference
                    handled_raw_paths.append(rp)
            else:
                handled_raw_paths.append(rp)

        # write to DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO photos (
                species, species_code, gfib_link, main_feature, feature_code, date_taken,
                used_topaz, subject_size, other_features, location, location_code,
                processed_filename, processed_path, raw_attached, raw_paths, raw_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            species,
            spec_code,
            gfib,
            main_feat,
            feat_code,
            date_taken,
            used_topaz,
            subject_size,
            other,
            location,
            locc,
            fname,
            dest_proc,
            raw_attached,
            "|".join(handled_raw_paths),
            raw_mode,
            datetime.datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()

        messagebox.showinfo("Saved", f"Entry saved.\nProcessed file: {dest_proc}\nRaw files attached: {len(handled_raw_paths)} (mode: {raw_mode})")
        self.clear_add_form()
        self.populate_db_view()
        self.populate_search_results()

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
    init_db()
    app = PlantPhotoManager()
    app.mainloop()

if __name__ == "__main__":
    main()
