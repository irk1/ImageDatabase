import sqlite3
import os

DB_FILE = r"C:\Users\izzyk\Downloads\Flower Image DB\plant pic db.db"

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Get table info
c.execute("PRAGMA table_info(feature_mappings)")
columns = c.fetchall()

print("Columns in 'feature_mappings':")
for col in columns:
    # col[1] is the column name
    print(col[1])

conn.close()
