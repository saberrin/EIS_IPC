import random
import sqlite3
from typing import List
from datetime import datetime, timedelta
from entity import EisMeasurement
from repository import insert_measurements
from db_init import init_database
from repository import get_cluster_latest_measurements

DB_PATH = "eis_xjj.db"

# def generate_random_measurements(num_samples: int) -> List[EisMeasurement]:
#     measurements = []
#     for _ in range(num_samples):
#         cell_id = random.randint(1, 100)  # 随机生成单元 ID
#         creation_time = datetime.now() - timedelta(days=random.randint(0, 10))  # 随机生成创建时间（过去 10 天内）
#         frequency = random.uniform(1e3, 1e6)  # 随机生成频率 (1 kHz 到 1 MHz)
#         real_impedance = random.uniform(0, 100)  # 随机生成实部阻抗
#         imag_impedance = random.uniform(-50, 50)  # 随机生成虚部阻抗
#         voltage = random.uniform(0, 5)  # 随机生成电压
#         measurements.append(EisMeasurement(cell_id, creation_time, frequency, real_impedance, imag_impedance, voltage))
#     return measurements

def fetch_latest_ids():
    """Fetch the latest container, cabinet, and cluster IDs for testing."""
    try:
        # Connect to the database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        # Fetch the latest container ID
        cursor.execute("SELECT container_id FROM container ORDER BY container_id DESC LIMIT 1")
        container_id = cursor.fetchone()
        if container_id:
            print("Latest container_id:", container_id[0])
            
            # Fetch the latest cabinet ID related to the container
            cursor.execute("SELECT cabinet_id FROM battery_cabinet WHERE container_id = ? ORDER BY cabinet_id DESC LIMIT 1", (container_id[0],))
            cabinet_id = cursor.fetchone()
            if cabinet_id:
                print("Latest cabinet_id:", cabinet_id[0])
                
                # Fetch the latest cluster ID related to the cabinet
                cursor.execute("SELECT cluster_id FROM battery_cluster WHERE cabinet_id = ? ORDER BY cluster_id DESC LIMIT 1", (cabinet_id[0],))
                cluster_id = cursor.fetchone()
                if cluster_id:
                    print("Latest cluster_id:", cluster_id[0])
                else:
                    print("No cluster_id found for the latest cabinet.")
            else:
                print("No cabinet_id found for the latest container.")
        else:
            print("No container_id found in the container table.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if connection:
            connection.close()

# def fetch_measurements():
#     """Fetch all rows from eis_measurement table for testing."""
#     try:
#         # Connect to the database
#         connection = sqlite3.connect(DB_PATH)
#         cursor = connection.cursor()
        
#         # Execute the query
#         cursor.execute("SELECT * FROM eis_measurement;")
#         rows = cursor.fetchall()  # Fetch all results
        
#         # Print results
#         for row in rows:
#             print(row)  # Or format output as needed

#     except sqlite3.Error as e:
#         print(f"Database error: {e}")
#     finally:
#         if connection:
#             connection.close()  # Ensure the connection is closed

if __name__ == "__main__":
    # Initialize the database
    init_database()
    
    # Generate and insert random measurements
    # random_measurements = generate_random_measurements(10)
    # insert_measurements(random_measurements)  # Insert data into the database
    
    # Fetch and print latest IDs from container, cabinet, and cluster tables
    fetch_latest_ids()
    
    # Fetch and print all measurements from the eis_measurement table
    # fetch_measurements()
