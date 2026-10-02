import sqlite3
conn = sqlite3.connect('data/processed/risk_store.db')
conn.execute("DELETE FROM risk_history WHERE location_id LIKE 'test_%'")
conn.commit()
print("Cleaned!")
