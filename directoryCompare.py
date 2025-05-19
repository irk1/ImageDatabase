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
        root.title("Compare Images in Folder or .7z Archive")
        self.src1 = self.src2 = ""
        self.temp_dirs = []

        tk.Button(root, text="Select Source 1", command=self.load_src1).grid(row=0, column=0, padx=5, pady=5)
        self.src1_label = tk.Label(root, text="Not selected", anchor="w", width=60)
        self.src1_label.grid(row=0, column=1)

        tk.Button(root, text="Select Source 2", command=self.load_src2).grid(row=1, column=0, padx=5, pady=5)
        self.src2_label = tk.Label(root, text="Not selected", anchor="w", width=60)
        self.src2_label.grid(row=1, column=1)

        btn_frame = tk.Frame(root)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="Compare by Filename", command=lambda: self.run_thread(self.compare_by_name)).grid(row=0, column=0, padx=10)
        tk.Button(btn_frame, text="Compare by Hash", command=lambda: self.run_thread(self.compare_by_hash)).grid(row=0, column=1, padx=10)

        self.progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=2, pady=5)
        self.status = tk.Label(root, text="", anchor="w")
        self.status.grid(row=4, column=0, columnspan=2)

    def load_src1(self):
        path = filedialog.askopenfilename(title="Select Folder or .7z File") or filedialog.askdirectory()
        if path:
            self.src1 = path
            self.src1_label.config(text=path)

    def load_src2(self):
        path = filedialog.askopenfilename(title="Select Folder or .7z File") or filedialog.askdirectory()
        if path:
            self.src2 = path
            self.src2_label.config(text=path)

    def update_progress(self, current, total, label="Processing"):
        self.root.after(0, lambda: self._update_progress(current, total, label))

    def _update_progress(self, current, total, label):
        self.progress["maximum"] = total
        self.progress["value"] = current
        self.status.config(text=f"{label}: {current}/{total}")

    def run_thread(self, comparison_func):
        if not self.src1 or not self.src2:
            messagebox.showwarning("Error", "Please select both sources.")
            return
        self.status.config(text="Starting...")
        self.progress["value"] = 0
        threading.Thread(target=lambda: self.threaded_compare(comparison_func), daemon=True).start()

    def threaded_compare(self, comparison_func):
        try:
            comparison_func()
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("Error", str(e)))

    def compare_by_name(self):
        self.update_progress(0, 1, "Listing Src1")
        files1, tmp1 = list_files(self.src1, tempfile.gettempdir(), lambda i, t: self.update_progress(i, t, "Listing Src1"))
        self.update_progress(0, 1, "Listing Src2")
        files2, tmp2 = list_files(self.src2, tempfile.gettempdir(), lambda i, t: self.update_progress(i, t, "Listing Src2"))
        if tmp1: self.temp_dirs.append(tmp1)
        if tmp2: self.temp_dirs.append(tmp2)

        set1, set2 = set(files1), set(files2)
        only1 = sorted(set1 - set2)
        only2 = sorted(set2 - set1)
        self.show_results(only1, only2, files1, files2, "Filename comparison")

    def compare_by_hash(self):
        self.update_progress(0, 1, "Listing Src1")
        f1, tmp1 = list_files(self.src1, tempfile.gettempdir(), lambda i, t: self.update_progress(i, t, "Listing Src1"))
        self.update_progress(0, 1, "Listing Src2")
        f2, tmp2 = list_files(self.src2, tempfile.gettempdir(), lambda i, t: self.update_progress(i, t, "Listing Src2"))
        if tmp1: self.temp_dirs.append(tmp1)
        if tmp2: self.temp_dirs.append(tmp2)

        self.status.config(text="Hashing Source 2...")
        hashes2 = {}
        all2 = list(f2.items())
        for idx, (rel, full) in enumerate(all2, 1):
            h = compute_hash(full)
            hashes2[h] = rel
            self.update_progress(idx, len(all2), "Hashing Src2")

        self.status.config(text="Hashing Source 1...")
        only1 = []
        only2 = set(hashes2.values())
        all1 = list(f1.items())
        for idx, (rel, full) in enumerate(all1, 1):
            h = compute_hash(full)
            if h in hashes2:
                only2.discard(hashes2[h])
            else:
                only1.append(rel)
            self.update_progress(idx, len(all1), "Hashing Src1")

        only2 = sorted(only2)
        self.show_results(only1, only2, f1, f2, "Hash comparison")

    def show_results(self, only1, only2, map1, map2, title):
        self.root.after(0, lambda: self._show_results(only1, only2, map1, map2, title))

    def _show_results(self, only1, only2, map1, map2, title):
        self.progress["value"] = 0
        self.status.config(text=title + " done.")
        win = tk.Toplevel(self.root)
        win.title(f"Results: {title}")

        frame = tk.Frame(win)
        frame.pack(padx=10, pady=10)

        tk.Label(frame, text=f"Only in Source 1\n({self.src1})", anchor="center").grid(row=0, column=0)
        tk.Label(frame, text=f"Only in Source 2\n({self.src2})", anchor="center").grid(row=0, column=1)

        lb1 = tk.Listbox(frame, selectmode=tk.MULTIPLE, width=60, height=20)
        lb1.grid(row=1, column=0, padx=5)
        for item in only1:
            lb1.insert(tk.END, item)

        lb2 = tk.Listbox(frame, selectmode=tk.MULTIPLE, width=60, height=20)
        lb2.grid(row=1, column=1, padx=5)
        for item in only2:
            lb2.insert(tk.END, item)

        def do_copy(lb, src_map, dst):
            sel = [lb.get(i) for i in lb.curselection()]
            for rel in sel:
                srcp = src_map[rel]
                dstp = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(dstp), exist_ok=True)
                shutil.copy2(srcp, dstp)
            messagebox.showinfo("Copied", f"Copied {len(sel)} files.")

        tk.Button(frame, text="Copy →", command=lambda: do_copy(lb1, map1, self.src2)).grid(row=2, column=0, pady=10)
        tk.Button(frame, text="← Copy", command=lambda: do_copy(lb2, map2, self.src1)).grid(row=2, column=1, pady=10)

    def __del__(self):
        for d in self.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    root = tk.Tk()
    CompareApp(root)
    root.mainloop()
