import os
import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import init_db, get_connection
from data.fetch_real_delhi_data import fetch_real_delhi_road_dataset

def seed_database(num_segments=350):
    """
    Initializes SQLite tables and seeds them with authentic Delhi road network,
    condition surveys, live traffic & Open-Meteo weather, and repair records.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Drop existing tables to ensure latest schema with geometry_coords
    cursor.execute("DROP TABLE IF EXISTS predictions")
    cursor.execute("DROP TABLE IF EXISTS repair_history")
    cursor.execute("DROP TABLE IF EXISTS condition_surveys")
    cursor.execute("DROP TABLE IF EXISTS traffic_weather")
    cursor.execute("DROP TABLE IF EXISTS road_segments")
    conn.commit()
    conn.close()

    print("Initializing SQLite database schema...")
    init_db()
    
    print(f"Fetching authentic Delhi road network dataset ({num_segments} segments)...")
    df_seg, df_surv, df_tw, df_rep = fetch_real_delhi_road_dataset(target_count=num_segments)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Insert road segments
    print("Populating road_segments table with authentic Delhi corridors...")
    df_seg.to_sql("road_segments", conn, if_exists="append", index=False)
    
    # Insert condition surveys
    print("Populating condition_surveys table...")
    df_surv.to_sql("condition_surveys", conn, if_exists="append", index=False)
    
    # Insert traffic and weather
    print("Populating traffic_weather table...")
    df_tw.to_sql("traffic_weather", conn, if_exists="append", index=False)
    
    # Insert repair history
    print("Populating repair_history table...")
    df_rep.to_sql("repair_history", conn, if_exists="append", index=False)
    
    conn.commit()
    conn.close()
    print("Database seeding with authentic Delhi data completed successfully!")

if __name__ == "__main__":
    seed_database()
