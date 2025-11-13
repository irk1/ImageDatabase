import sqlite3
import os

DB_FILE = r"C:\Users\izzyk\Downloads\Flower Image DB\test.db"
db_path = DB_FILE

# Connect properly — don't assign the filename directly to db
conn = sqlite3.connect(db_path)
c = conn.cursor()

# View the table schema
c.execute("PRAGMA table_info(location_mappings);")
print(c.fetchall())

conn.close()