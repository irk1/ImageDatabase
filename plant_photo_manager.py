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


def load_specific_mappings(db_path):
    """Load feature and location mappings safely."""
    feature_map, location_map = {}, {}
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        for row in c.execute("SELECT specific, general FROM feature_mappings"):
            feature_map[row[0]] = row[1]
    except sqlite3.OperationalError:
        print("Warning: feature_mappings table not found, skipping...")

    try:
        for row in c.execute("SELECT specific, general FROM location_mappings"):
            location_map[row[0]] = row[1]
    except sqlite3.OperationalError:
        print("Warning: location_mappings table not found, skipping...")

    conn.close()
    return feature_map, location_map


# --- One-time setup before GUI ---
DB_FILE = select_or_create_db()

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
    def __init__(self):
        print("[DEBUG] Initializing PlantPhotoManager...")
        super().__init__()
        print("[DEBUG] Tk root created.")
        self.title("Plant Photo Manager")
        self.geometry("1050x700")
        self.minsize(950, 620)

        # Setup empty maps; will load in background
        global FEATURE_MAP, LOCATION_MAP
        FEATURE_MAP = {}
        LOCATION_MAP = {}

        print("[DEBUG] Loading mappings into memory...")
        try:
            FEATURE_MAP, LOCATION_MAP = load_specific_mappings(DB_FILE)
            print(f"[DEBUG] Feature mappings loaded: {len(FEATURE_MAP)}")
            print(f"[DEBUG] Location mappings loaded: {len(LOCATION_MAP)}")
        except Exception as e:
            print("[DEBUG] Mapping load error:", e)

        print("[DEBUG] Starting GUI widget setup...")
        self.setup_widgets()
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
        import threading
        def loader():
            global FEATURE_MAP, LOCATION_MAP
            load_specific_mappings(DB_FILE)
            print("Feature/Location mappings loaded successfully.")
            # Refresh autocomplete entries after loading
            self.after(0, self.refresh_autocomplete)
        threading.Thread(target=loader, daemon=True).start()

    def refresh_autocomplete(self):
        """Refresh all autocomplete comboboxes in Add tab after mappings are loaded."""
        for varname in ("species_var", "feature_var", "size_var", "other_var", "loc_var"):
            cb = getattr(self, varname + "_combobox", None)
            if cb:
                cb['values'] = self.get_previous_values(varname)

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
    if not DB_FILE:
        print("No database selected or created. Exiting.")
        sys.exit(0)

    app = PlantPhotoManager()
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