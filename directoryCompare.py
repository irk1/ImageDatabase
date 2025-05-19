import os
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import py7zr
import shutil
import tempfile
import threading

def compute_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def extract_7z_flattened(archive_path, base_temp_dir, progress_callback=None):
    temp_dir = tempfile.mkdtemp(dir=base_temp_dir)
    with py7zr.SevenZipFile(archive_path, mode='r') as archive:
        archive.extractall(path=temp_dir)

    all_files = []
    for root, _, files in os.walk(temp_dir):
        for file in files:
            all_files.append(os.path.join(root, file))

    total = len(all_files)
    file_dict = {}
    for idx, full_path in enumerate(all_files, 1):
        rel = os.path.relpath(full_path, temp_dir)
        file_dict[rel] = full_path
        if progress_callback:
            progress_callback(idx, total)
    return file_dict, temp_dir

def list_files(source, base_temp_dir=None, progress_callback=None):
    if source.lower().endswith(".7z"):
        return extract_7z_flattened(source, base_temp_dir, progress_callback)
    else:
        all_files = []
        for root, _, files in os.walk(source):
            for file in files:
                all_files.append(os.path.join(root, file))
        total = len(all_files)
        file_dict = {}
        for idx, full_path in enumerate(all_files, 1):
            rel = os.path.relpath(full_path, source)
            file_dict[rel] = full_path
            if progress_callback:
                progress_callback(idx, total)
        return file_dict, None

class CompareApp:
    def __init__(self, root):
        self.root = root
        root.title("Compare by Filename or Hash")

        self.src1 = None
        self.src2 = None
        self.temp_dirs = []

        # UI Elements
        tk.Button(root, text="Select Source 1 (Folder or .7z)", command=self.select_src1).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.src1_label = tk.Label(root, text="No source 1 selected", anchor="w", width=70)
        self.src1_label.grid(row=0, column=1, padx=5, pady=5)

        tk.Button(root, text="Select Source 2 (Folder or .7z)", command=self.select_src2).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.src2_label = tk.Label(root, text="No source 2 selected", anchor="w", width=70)
        self.src2_label.grid(row=1, column=1, padx=5, pady=5)

        btn_frame = tk.Frame(root)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="Compare by Filename", command=lambda: self.start_thread(self.compare_by_name)).grid(row=0, column=0, padx=10)
        tk.Button(btn_frame, text="Compare by Hash", command=lambda: self.start_thread(self.compare_by_hash)).grid(row=0, column=1, padx=10)

        self.progress = ttk.Progressbar(root, orient="horizontal", length=450, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=2, pady=5)

        self.status = tk.Label(root, text="", anchor="w")
        self.status.grid(row=4, column=0, columnspan=2)

    def select_src1(self):
        path = filedialog.askopenfilename(title="Select Source 1: Folder or .7z archive",
                                          filetypes=[("7z archives", "*.7z")])
        if not path:
            path = filedialog.askdirectory(title="Or select Source 1 folder")
        if path:
            self.src1 = path
            self.src1_label.config(text=path)

    def select_src2(self):
        path = filedialog.askopenfilename(title="Select Source 2: Folder or .7z archive",
                                          filetypes=[("7z archives", "*.7z")])
        if not path:
            path = filedialog.askdirectory(title="Or select Source 2 folder")
        if path:
            self.src2 = path
            self.src2_label.config(text=path)

    def update_progress(self, current, total, label="Processing"):
        def _update():
            self.progress["maximum"] = total
            self.progress["value"] = current
            self.status.config(text=f"{label}: {current}/{total}")
        self.root.after(0, _update)

    def start_thread(self, func):
        if not self.src1 or not self.src2:
            messagebox.showwarning("Warning", "Please select both sources before comparing.")
            return
        self.progress["value"] = 0
        self.status.config(text="Starting comparison...")
        threading.Thread(target=func, daemon=True).start()

    def compare_by_name(self):
        self.status.config(text="Listing files in Source 1...")
        files1, tmp1 = list_files(self.src1, tempfile.gettempdir(), lambda i,t: self.update_progress(i, t, "Listing Src1"))
        self.status.config(text="Listing files in Source 2...")
        files2, tmp2 = list_files(self.src2, tempfile.gettempdir(), lambda i,t: self.update_progress(i, t, "Listing Src2"))
        if tmp1: self.temp_dirs.append(tmp1)
        if tmp2: self.temp_dirs.append(tmp2)

        set1, set2 = set(files1.keys()), set(files2.keys())
        only1 = sorted(set1 - set2)
        only2 = sorted(set2 - set1)

        self.show_results(only1, only2, files1, files2, "Filename Comparison")
        self.update_progress(0, 0, "Comparison done.")

    def compare_by_hash(self):
        self.status.config(text="Listing files in Source 1...")
        files1, tmp1 = list_files(self.src1, tempfile.gettempdir())
        self.status.config(text="Listing files in Source 2...")
        files2, tmp2 = list_files(self.src2, tempfile.gettempdir())
        if tmp1: self.temp_dirs.append(tmp1)
        if tmp2: self.temp_dirs.append(tmp2)

        self.status.config(text="Hashing files in Source 2...")
        hashes2 = {}
        all2 = list(files2.items())
        total2 = len(all2)
        for idx, (rel, full) in enumerate(all2, 1):
            h = compute_hash(full)
            hashes2[h] = rel
            self.update_progress(idx, total2, "Hashing Src2")

        self.status.config(text="Hashing files in Source 1...")
        only1 = []
        only2 = set(hashes2.values())
        all1 = list(files1.items())
        total1 = len(all1)
        for idx, (rel, full) in enumerate(all1, 1):
            h = compute_hash(full)
            if h in hashes2:
                only2.discard(hashes2[h])
            else:
                only1.append(rel)
            self.update_progress(idx, total1, "Hashing Src1")

        only2 = sorted(only2)
        self.show_results(only1, only2, files1, files2, "Hash Comparison")
        self.update_progress(0, 0, "Comparison done.")

    def show_results(self, only1, only2, map1, map2, title):
        def copy_files(selected, source_map, dest_path):
            count = 0
            for rel_path in selected:
                src_file = source_map[rel_path]
                dst_file = os.path.join(dest_path, rel_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
                count += 1
            messagebox.showinfo("Copy Complete", f"Copied {count} files.")

        def do_copy_left():
            selected = listbox_left.curselection()
            if not selected:
                messagebox.showwarning("No selection", "Select files to copy to Source 1")
                return
            files = [listbox_left.get(i) for i in selected]
            copy_files(files, map2, self.src1)

        def do_copy_right():
            selected = listbox_right.curselection()
            if not selected:
                messagebox.showwarning("No selection", "Select files to copy to Source 2")
                return
            files = [listbox_right.get(i) for i in selected]
            copy_files(files, map1, self.src2)

        win = tk.Toplevel(self.root)
        win.title(f"Results - {title}")

        tk.Label(win, text=f"Only in Source 1:\n{self.src1}").grid(row=0, column=0)
        tk.Label(win, text=f"Only in Source 2:\n{self.src2}").grid(row=0, column=2)

        listbox_left = tk.Listbox(win, selectmode=tk.EXTENDED, width=50, height=20)
        listbox_left.grid(row=1, column=0, padx=5, pady=5)
        for f in only1:
            listbox_left.insert(tk.END, f)

        listbox_right = tk.Listbox(win, selectmode=tk.EXTENDED, width=50, height=20)
        listbox_right.grid(row=1, column=2, padx=5, pady=5)
        for f in only2:
            listbox_right.insert(tk.END, f)

        btn_frame = tk.Frame(win)
        btn_frame.grid(row=1, column=1, padx=5, pady=5)

        tk.Button(btn_frame, text="Copy →", command=do_copy_right, width=10).pack(pady=10)
        tk.Button(btn_frame, text="← Copy", command=do_copy_left, width=10).pack(pady=10)

    def __del__(self):
        for d in self.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("700x250")
    app = CompareApp(root)
    root.mainloop()
