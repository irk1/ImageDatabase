import os
import hashlib
import shutil
import tempfile
import threading
import concurrent.futures
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import py7zr

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}

def is_image_file(filename):
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS

def hash_file(fp):
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def list_files(path, temp_dirs, include_all=False):
    files = {}
    if os.path.isdir(path):
        for root, _, names in os.walk(path):
            for n in names:
                if include_all or is_image_file(n):
                    full = os.path.join(root, n)
                    rel = os.path.relpath(full, path).replace("\\", "/")
                    files[rel] = full
    elif path.lower().endswith(".7z"):
        tmp = tempfile.mkdtemp()
        temp_dirs.append(tmp)
        with py7zr.SevenZipFile(path, "r") as a:
            a.extractall(path=tmp)
        return list_files(tmp, temp_dirs, include_all)
    return files

def compare_by_filename(f1, f2):
    m1 = {p: f2[p] for p in f2 if p not in f1}
    m2 = {p: f1[p] for p in f1 if p not in f2}
    return m1, m2

def compare_by_hash(f1, f2, progress=None):
    # Hash all files in source1
    hashes1 = {}
    items1 = list(f1.items())
    total1 = len(items1)
    with concurrent.futures.ThreadPoolExecutor() as ex:
        futures = {ex.submit(hash_file, fp): rel for rel, fp in items1}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            rel = futures[fut]
            h = fut.result()
            hashes1.setdefault(h, []).append(rel)
            if progress: progress("Hashing Src1", i, total1)

    # Hash all files in source2
    hashes2 = {}
    items2 = list(f2.items())
    total2 = len(items2)
    with concurrent.futures.ThreadPoolExecutor() as ex:
        futures = {ex.submit(hash_file, fp): rel for rel, fp in items2}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            rel = futures[fut]
            h = fut.result()
            hashes2.setdefault(h, []).append(rel)
            if progress: progress("Hashing Src2", i, total2)

    # Find hashes only in one
    only_hash1 = set(hashes1) - set(hashes2)
    only_hash2 = set(hashes2) - set(hashes1)

    # Map back to rel paths
    m1 = {rel: f1[rel] for h in only_hash1 for rel in hashes1[h]}
    m2 = {rel: f2[rel] for h in only_hash2 for rel in hashes2[h]}
    return m1, m2

class CompareApp:
    def __init__(self, root):
        self.root = root
        root.title("Image Compare Tool (.7z + Folders)")
        self.src1 = self.src2 = ""
        self.temp_dirs = []

        tk.Button(root, text="Select Source 1", command=self.load1).grid(row=0,column=0,padx=5,pady=5)
        self.l1 = tk.Label(root, text="Drop here for Source 1", width=60, relief="sunken", anchor="w")
        self.l1.grid(row=0,column=1,padx=5)
        self.l1.drop_target_register(DND_FILES); self.l1.dnd_bind("<<Drop>>", self.drop1)

        tk.Button(root, text="Select Source 2", command=self.load2).grid(row=1,column=0,padx=5,pady=5)
        self.l2 = tk.Label(root, text="Drop here for Source 2", width=60, relief="sunken", anchor="w")
        self.l2.grid(row=1,column=1,padx=5)
        self.l2.drop_target_register(DND_FILES); self.l2.dnd_bind("<<Drop>>", self.drop2)

        f = tk.Frame(root); f.grid(row=2,column=0,columnspan=2,pady=10)
        tk.Button(f, text="Compare by Filename", command=lambda: self.run(self._cmp_name)).grid(row=0,column=0,padx=10)
        tk.Button(f, text="Compare by Hash",     command=lambda: self.run(self._cmp_hash)).grid(row=0,column=1,padx=10)

        self.pb = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
        self.pb.grid(row=3,column=0,columnspan=2,pady=5)
        self.st = tk.Label(root, text="", anchor="w")
        self.st.grid(row=4,column=0,columnspan=2)

    def load1(self):
        p = filedialog.askopenfilename(title="Src1") or filedialog.askdirectory(title="Src1")
        if p: self.src1, self.l1["text"] = p, p
    def load2(self):
        p = filedialog.askopenfilename(title="Src2") or filedialog.askdirectory(title="Src2")
        if p: self.src2, self.l2["text"] = p, p
    def drop1(self,e):
        p=e.data.strip("{}"); 
        if os.path.exists(p): self.src1, self.l1["text"]=p,p
    def drop2(self,e):
        p=e.data.strip("{}"); 
        if os.path.exists(p): self.src2, self.l2["text"]=p,p

    def update(self, tag, i, total):
        self.pb["maximum"], self.pb["value"] = total, i
        self.st["text"] = f"{tag}: {i}/{total}"
        self.root.update_idletasks()

    def run(self, func):
        if not self.src1 or not self.src2:
            messagebox.showwarning("Error","Select both sources."); return
        self.pb["value"] = 0
        self.st["text"] = "Starting..."
        threading.Thread(target=func, daemon=True).start()

    def _cmp_name(self):
        f1 = list_files(self.src1, self.temp_dirs, include_all=False)
        f2 = list_files(self.src2, self.temp_dirs, include_all=False)
        m1, m2 = compare_by_filename(f1, f2)
        self._show(f1, f2, m1, m2)

    def _cmp_hash(self):
        f1 = list_files(self.src1, self.temp_dirs, include_all=True)  # all files hashed
        f2 = list_files(self.src2, self.temp_dirs, include_all=True)
        m1, m2 = compare_by_hash(f1, f2, self.update)
        self._show(f1, f2, m1, m2)

    def _show(self, f1, f2, m1, m2):
        self.pb["value"]=0; self.st["text"]="Done"
        w=tk.Toplevel(self.root); w.title("Comparison Results")

        # Show full paths and total files for each source
        tk.Label(w, text=f"Source 1: {self.src1}", anchor="w", justify="left").grid(row=0,column=0, sticky="w", padx=5)
        tk.Label(w, text=f"Total files in Src1: {len(f1)}", anchor="w").grid(row=1,column=0, sticky="w", padx=5)

        tk.Label(w, text=f"Source 2: {self.src2}", anchor="w", justify="left").grid(row=0,column=1, sticky="w", padx=5)
        tk.Label(w, text=f"Total files in Src2: {len(f2)}", anchor="w").grid(row=1,column=1, sticky="w", padx=5)

        # Missing files labels
        tk.Label(w,text=f"Missing in Src1 ({len(m1)}):").grid(row=2,column=0)
        tk.Label(w,text=f"Missing in Src2 ({len(m2)}):").grid(row=2,column=1)

        lb1 = tk.Listbox(w, width=60, height=20)
        lb2 = tk.Listbox(w, width=60, height=20)
        lb1.grid(row=3,column=0,padx=5,pady=5)
        lb2.grid(row=3,column=1,padx=5,pady=5)

        for k in m1: lb1.insert("end", k)
        for k in m2: lb2.insert("end", k)

        def c1(): 
            for k,fp in m1.items():
                dst=os.path.join(self.src1,k); os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copy2(fp,dst)
            messagebox.showinfo("Copied",f"{len(m1)} files copied to Src1")
        def c2(): 
            for k,fp in m2.items():
                dst=os.path.join(self.src2,k); os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copy2(fp,dst)
            messagebox.showinfo("Copied",f"{len(m2)} files copied to Src2")

        tk.Button(w,text="Copy → Src1",command=c1).grid(row=4,column=0,pady=10)
        tk.Button(w,text="Copy → Src2",command=c2).grid(row=4,column=1,pady=10)

    def __del__(self):
        for d in self.temp_dirs: shutil.rmtree(d,ignore_errors=True)

if __name__ == "__main__":
    root=TkinterDnD.Tk()
    CompareApp(root)
    root.mainloop()
