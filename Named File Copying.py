import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox


def choose_source():
    path = filedialog.askdirectory(title="Select Source Directory")
    if path:
        source_var.set(path)


def choose_destination():
    path = filedialog.askdirectory(title="Select Destination Directory")
    if path:
        dest_var.set(path)


def show_missing_popup(missing):
    popup = tk.Toplevel(root)
    popup.title("Missing Files")
    popup.geometry("400x300")

    tk.Label(popup, text="The following files were not found:").pack(anchor="w", padx=5, pady=5)

    text = tk.Text(popup, wrap="word")
    text.pack(expand=True, fill="both", padx=5, pady=5)
    text.insert("1.0", "\n".join(missing))
    text.configure(state="disabled")

    def copy_to_clipboard():
        root.clipboard_clear()
        root.clipboard_append("\n".join(missing))
        root.update()
        messagebox.showinfo("Copied", "Missing file list copied to clipboard.")

    tk.Button(popup, text="Copy to Clipboard", command=copy_to_clipboard).pack(pady=5)
    tk.Button(popup, text="Close", command=popup.destroy).pack(pady=5)


def copy_files():
    filenames = [f.strip() for f in text_box.get("1.0", tk.END).splitlines() if f.strip()]
    if not filenames:
        messagebox.showerror("Error", "Please paste a list of file names.")
        return

    source = source_var.get()
    dest = dest_var.get()

    if not os.path.isdir(source):
        messagebox.showerror("Error", "Please select a valid source directory.")
        return
    if not os.path.isdir(dest):
        messagebox.showerror("Error", "Please select a valid destination directory.")
        return

    copied = 0
    missing = []

    for name in filenames:
        found = False
        for root_dir, _, files in os.walk(source):
            for fname in files:
                if fname.lower() == name.lower():
                    src_path = os.path.join(root_dir, fname)
                    shutil.copy2(src_path, os.path.join(dest, fname))
                    copied += 1
                    found = True
                    break
            if found:
                break
        if not found:
            missing.append(name)

    if missing:
        show_missing_popup(missing)

    messagebox.showinfo("Done", f"Copied {copied} file(s).")


# GUI Setup
root = tk.Tk()
root.title("File Finder & Copier")

source_var = tk.StringVar()
dest_var = tk.StringVar()

tk.Label(root, text="Paste file names (one per line):").pack(anchor="w", padx=5, pady=2)
text_box = tk.Text(root, height=10, width=50)
text_box.pack(padx=5, pady=5)

tk.Label(root, text="Source Directory:").pack(anchor="w", padx=5)
tk.Entry(root, textvariable=source_var, width=40).pack(side="left", padx=5)
tk.Button(root, text="Browse", command=choose_source).pack(side="left", padx=5)

tk.Label(root, text="Destination Directory:").pack(anchor="w", padx=5, pady=(10, 0))
tk.Entry(root, textvariable=dest_var, width=40).pack(side="left", padx=5)
tk.Button(root, text="Browse", command=choose_destination).pack(side="left", padx=5)

tk.Button(root, text="Copy Files", command=copy_files, bg="lightgreen").pack(pady=10)

root.mainloop()
