import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


def select_directory():
    path = filedialog.askdirectory()
    if path:
        dir_entry.delete(0, tk.END)
        dir_entry.insert(0, path)


def check_files():
    file_list_text = file_list_box.get("1.0", tk.END).strip()
    if not file_list_text:
        messagebox.showerror("Error", "Please paste a list of file names.")
        return

    directory = dir_entry.get().strip()
    if not directory or not os.path.isdir(directory):
        messagebox.showerror("Error", "Please select a valid directory.")
        return

    file_names = [name.strip() for name in file_list_text.splitlines() if name.strip()]

    found_files = {}
    missing_files = []
    duplicates = {}

    # Search for files
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f in file_names:
                full_path = os.path.join(root, f)
                if f in found_files:
                    # Duplicate found
                    duplicates.setdefault(f, []).append(full_path)
                else:
                    found_files[f] = full_path

    # Check which files are missing
    for name in file_names:
        if name not in found_files:
            missing_files.append(name)

    # Show results
    result = []
    result.append(f"Total requested: {len(file_names)}")
    result.append(f"Found: {len(found_files)}")
    result.append(f"Missing: {len(missing_files)}")
    result.append(f"Duplicates: {sum(len(v) for v in duplicates.values())}")

    result.append("\n--- Found Files ---")
    for name, path in found_files.items():
        result.append(f"{name} -> {path}")

    result.append("\n--- Missing Files ---")
    for name in missing_files:
        result.append(name)

    result.append("\n--- Duplicates ---")
    for name, paths in duplicates.items():
        result.append(f"{name}:")
        for p in paths:
            result.append(f"    {p}")

    result_text.delete("1.0", tk.END)
    result_text.insert(tk.END, "\n".join(result))


# GUI setup
root = tk.Tk()
root.title("File Checker with Duplicate Detection")
root.geometry("800x600")

# File list input
tk.Label(root, text="Paste file names here (one per line):").pack(anchor="w", padx=5, pady=2)
file_list_box = scrolledtext.ScrolledText(root, height=10)
file_list_box.pack(fill="x", padx=5, pady=5)

# Directory selector
dir_frame = tk.Frame(root)
dir_frame.pack(fill="x", padx=5, pady=2)
tk.Label(dir_frame, text="Directory to search:").pack(side="left", padx=5)
dir_entry = tk.Entry(dir_frame)
dir_entry.pack(side="left", fill="x", expand=True, padx=5)
tk.Button(dir_frame, text="Browse", command=select_directory).pack(side="left", padx=5)

# Check button
tk.Button(root, text="Check Files", command=check_files).pack(pady=5)

# Results box
tk.Label(root, text="Results:").pack(anchor="w", padx=5)
result_text = scrolledtext.ScrolledText(root, height=20)
result_text.pack(fill="both", expand=True, padx=5, pady=5)

root.mainloop()
