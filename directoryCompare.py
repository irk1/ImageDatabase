import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import py7zr
import hashlib
from tkinterdnd2 import DND_FILES, TkinterDnD
from concurrent.futures import ThreadPoolExecutor


def list_all_files(path):
    if path.lower().endswith('.7z'):
        with py7zr.SevenZipFile(path, mode='r') as archive:
            return {
                file_info.filename
                for info in archive.list()
                for file_info in info.files
                if not file_info.is_directory
            }
    else:
        return {
            os.path.relpath(os.path.join(root, name), path).replace("\\", "/")
            for root, _, filenames in os.walk(path)
            for name in filenames
        }


def calculate_hashes(base, file_list, is_archive, progress_callback=None):
    hashes = {}
    total = len(file_list)

    def hash_file_from_disk(rel_path):
        full_path = os.path.join(base, rel_path)
        with open(full_path, 'rb') as f:
            return rel_path, hashlib.sha256(f.read()).hexdigest()

    def hash_file_from_archive(rel_path, filedata):
        return rel_path, hashlib.sha256(filedata.read()).hexdigest()

    if is_archive:
        with py7zr.SevenZipFile(base, mode='r') as archive:
            batch_data = archive.read(file_list)

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(hash_file_from_archive, rel, batch_data[rel]): rel
                for rel in file_list
            }
            for i, future in enumerate(futures, 1):
                rel, h = future.result()
                hashes[rel] = h
                if progress_callback:
                    progress_callback(i, total)
    else:
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(hash_file_from_disk, rel): rel
                for rel in file_list
            }
            for i, future in enumerate(futures, 1):
                rel, h = future.result()
                hashes[rel] = h
                if progress_callback:
                    progress_callback(i, total)

    return hashes


class CompareApp:
    def __init__(self, root):
        self.root = root
        root.title("File Compare Tool (.7z + Folder)")
        self.src1 = tk.StringVar()
        self.src2 = tk.StringVar()

        for idx, var in enumerate((self.src1, self.src2)):
            tk.Label(root, text=f"Source {idx+1}").grid(row=idx, column=0, padx=5, pady=5)
            ent = tk.Entry(root, textvariable=var, width=60)
            ent.grid(row=idx, column=1, padx=5, pady=5)
            ent.drop_target_register(DND_FILES)
            ent.dnd_bind('<<Drop>>', lambda e, v=var: v.set(e.data.strip('{}')))
            tk.Button(root, text="Browse", command=lambda v=var: v.set(filedialog.askopenfilename() or filedialog.askdirectory())).grid(row=idx, column=2)

        tk.Button(root, text="Compare by Filename", command=lambda: self.start(compare_hash=False)).grid(row=2, column=0, pady=10)
        tk.Button(root, text="Compare by Hash", command=lambda: self.start(compare_hash=True)).grid(row=2, column=1, pady=10)

        self.prog_text = tk.StringVar(value="Idle")
        tk.Label(root, textvariable=self.prog_text).grid(row=3, column=0, columnspan=3)
        self.pb = ttk.Progressbar(root, orient="horizontal", mode="determinate", length=600)
        self.pb.grid(row=4, column=0, columnspan=3, pady=5)

    def start(self, compare_hash):
        s1, s2 = self.src1.get(), self.src2.get()
        if not s1 or not s2:
            messagebox.showerror("Error", "Select both sources")
            return
        self.pb['value'] = 0
        threading.Thread(target=self.run_compare, args=(s1, s2, compare_hash), daemon=True).start()

    def update_progress(self, current, total, prefix):
        self.pb['maximum'] = total
        self.pb['value'] = current
        self.prog_text.set(f"{prefix}: {current} of {total}")
        self.root.update_idletasks()

    def run_compare(self, s1, s2, compare_hash):
        self.update_progress(0, 1, "Listing Src1")
        files1 = list_all_files(s1)
        self.update_progress(1, 1, "Listing Src1")

        self.update_progress(0, 1, "Listing Src2")
        files2 = list_all_files(s2)
        self.update_progress(1, 1, "Listing Src2")

        only1 = files1 - files2
        only2 = files2 - files1

        common = sorted(files1 & files2)

        if compare_hash:
            hashes1 = calculate_hashes(s1, common, s1.lower().endswith('.7z'),
                                       lambda i, t: self.update_progress(i, t, "Hashing Src1"))
            hashes2 = calculate_hashes(s2, common, s2.lower().endswith('.7z'),
                                       lambda i, t: self.update_progress(i, t, "Hashing Src2"))
            for f in common:
                if hashes1[f] != hashes2[f]:
                    only1.add(f)
                    only2.add(f)

        self.prog_text.set("Comparison complete")
        self.pb['value'] = self.pb['maximum']
        self.root.after(0, lambda: self.show_results(s1, s2, only1, only2, len(files1), len(files2)))

    def show_results(self, s1, s2, only1, only2, total1, total2):
        w = tk.Toplevel(self.root)
        w.title("Results")

        tk.Label(w, text=f"Source 1: {s1}   Total files: {total1}").grid(row=0, column=0, sticky="w", padx=5)
        tk.Label(w, text=f"Source 2: {s2}   Total files: {total2}").grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(w, text=f"Files present in Source 1 but missing in Source 2 ({len(only1)})").grid(row=1, column=0)
        tk.Label(w, text=f"Files present in Source 2 but missing in Source 1 ({len(only2)})").grid(row=1, column=1)

        lb1 = tk.Listbox(w, selectmode=tk.MULTIPLE, width=60, height=20)
        lb2 = tk.Listbox(w, selectmode=tk.MULTIPLE, width=60, height=20)
        lb1.grid(row=2, column=0, padx=5, pady=5)
        lb2.grid(row=2, column=1, padx=5, pady=5)
        for f in sorted(only1):
            lb1.insert(tk.END, f)
        for f in sorted(only2):
            lb2.insert(tk.END, f)

        tk.Button(w, text="Select All", command=lambda: lb1.select_set(0, tk.END)).grid(row=3, column=0)
        tk.Button(w, text="Select All", command=lambda: lb2.select_set(0, tk.END)).grid(row=3, column=1)

        tk.Button(w, text="Copy Selected from Source 1 → Source 2", command=lambda: self.copy_files(s1, s2, lb1)).grid(row=4, column=0, pady=5)
        tk.Button(w, text="Copy Selected from Source 2 → Source 1", command=lambda: self.copy_files(s2, s1, lb2)).grid(row=4, column=1, pady=5)

    def copy_files(self, src, dst, lb):
        is_arch = src.lower().endswith('.7z')
        sel = [lb.get(i) for i in lb.curselection()]
        if is_arch:
            with py7zr.SevenZipFile(src, 'r') as archive:
                files = archive.read(sel)
                for rel in sel:
                    data = files[rel].read()
                    out = os.path.join(dst, rel)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out, 'wb') as f:
                        f.write(data)
        else:
            for rel in sel:
                srcp = os.path.join(src, rel)
                dstp = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(dstp), exist_ok=True)
                shutil.copy2(srcp, dstp)
        messagebox.showinfo("Copied", f"Copied {len(sel)} files.")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    CompareApp(root)
    root.mainloop()
