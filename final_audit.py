import sqlite3
import os

db = r"c:\Users\naras\OneDrive\Desktop\upi-fraud-detection\database\users.db"

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- USERS ---")
cursor.execute("SELECT id, name, email FROM user")
for r in cursor.fetchall():
    print(f"{r['id']}: {r['name']} ({r['email']})")

print("\n--- TX COUNTS BY SENDER ---")
cursor.execute("SELECT sender_id, COUNT(*) FROM \"transaction\" GROUP BY sender_id")
for r in cursor.fetchall():
    print(f"Sender {r[0]}: {r[1]} txns")

conn.close()
