import sqlite3
from typing import List, Dict
from database.entity import EisMeasurement
from datetime import datetime
from database.config import DB_PATH
from collections import defaultdict
from typing import List, Dict
class Repository:
    def __init__(self):
        super().__init__()
        # self.connection = sqlite3.connect(DB_PATH)
        # self.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        # self.cursor = self.connection.cursor()



    def insert_measurements(self, measurements: List[EisMeasurement]):
        """
        Insert multiple measurements into the database.
        """
        connection = None
        try:
            # Confirm that the table exists
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='eis_measurement'")
            if not cursor.fetchone():
                print("Table 'eis_measurement' does not exist.")
                return
        
            cursor.executemany("""
            INSERT INTO eis_measurement (cell_id, real_time_id, frequency, real_impedance, imag_impedance, voltage, temperature,
                                         pack_current, container_number, cluster_number, pack_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (m.cell_id, m.real_time_id, m.frequency, m.real_impedance, m.imag_impedance, m.voltage,m.temperature,
             m.pack_current, m.container_number, m.cluster_number, m.pack_number)
            for m in measurements
        ])
            connection.commit()
            print("Measurements inserted successfully.")
        except Exception as e:
            print(f"Error inserting measurements: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()


    def insert_generated_info(self, generated_info_list: List[Dict]):
        """
        Inserts generated info data into the database.
        """
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            cursor.executemany("""
                INSERT INTO generated_info (measurement_id, dispersion_rate, temperature, real_time_id, cell_id,
                                            sei_rate, dendrites_rate, electrolyte_rate, polar_rate, conduct_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [
            (info['measurement_id'], info['dispersion_rate'], info['temperature'], info['real_time_id'], 
             info['cell_id'], info['sei_rate'], info['dendrites_rate'], info['electrolyte_rate'], 
             info['polar_rate'], info['conduct_rate'])
            for info in generated_info_list
            ])
            connection.commit()
        finally:
            if connection:
                connection.close()
    
    def insert_battery_pack(self, battery_pack_list: List[Dict]):
        """
        Inserts generated info data into the database.
        """
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            cursor.executemany("""
                INSERT INTO battery_pack (cluster_id, description, dispersion_rate, pack_saftety_rate,
                                            real_time_id)
                VALUES (?, ?, ?, ?, ?);
            """, [
            (pack['cluster_id'], pack['description'], pack['dispersion_rate'], 
             pack['pack_saftety_rate'], pack['real_time_id'])
            for pack in battery_pack_list
            ])
            connection.commit()
        finally:
            if connection:
                connection.close()

    def get_battery_pack_info(self, cluster_id: int, limit: int = 10) -> List[dict]:
        """
        Fetches the latest information for all battery packs within a given cluster.
        
        Returns a list of dictionaries containing information about each battery pack.
        """
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            # rows = cursor.execute("SELECT id from battery_cell WHERE cluster_id = ?;", (cluster_id,)).fetchall()
            # cursor = self.connection.cursor()
            # Fetch data from battery_pack table based on cluster_id
            cursor.execute("""
                SELECT pack_id, cluster_id, description, dispersion_rate, pack_saftety_rate, real_time_id
                FROM battery_pack
                WHERE cluster_id = ?
                ORDER BY real_time_id DESC
                LIMIT ?;
            """, (cluster_id, limit))
            
            rows = cursor.fetchall()

            # Convert the rows into a list of dictionaries for easier access
            result = [
                {
                    "pack_id": row[0],
                    "cluster_id": row[1],
                    "description": row[2],
                    "dispersion_rate": row[3],
                    "pack_saftety_rate": row[4],
                    "real_time_id": row[5]
                }
                for row in rows
            ]
            return result

        finally:
            if connection:
                connection.close()

    def get_latest_generated_info(self, cell_id: int) -> Dict:
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            cursor.execute("""
                SELECT measurement_id, dispersion_rate, temperature, real_time_id, cell_id,
                    sei_rate, dendrites_rate, electrolyte_rate, polar_rate, conduct_rate
                FROM generated_info
                WHERE cell_id = ?
                ORDER BY real_time_id DESC
                LIMIT 1;
            """, (cell_id,))
            
            row = cursor.fetchone()

            if row:
                result = {
                    "measurement_id": row[0],
                    "dispersion_rate": row[1],
                    "temperature": row[2],
                    "real_time_id": row[3],
                    "cell_id": row[4],
                    "sei_rate": row[5],
                    "dendrites_rate": row[6],
                    "electrolyte_rate": row[7],
                    "polar_rate": row[8],
                    "conduct_rate": row[9]
                }
                return result
            else:
                return {}
        except Exception as e:
            print(f"Error fetching latest generated info: {e}")
            return {}
        finally:
            if connection:
                connection.close()

    def get_cell_measurements(self, cell_id: int, limit: int = 50) -> List[EisMeasurement]:
        """
        Fetches the latest measurements for a specific cell.
        """
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            # cursor.execute("SELECT * FROM eis_measurement WHERE cell_id = ? ORDER BY creation_time DESC LIMIT ?;", (cell_id, limit))
            # cursor = self.connection.cursor()
            cursor.execute("""
                SELECT cell_id, real_time_id, frequency, real_impedance, imag_impedance,
                       voltage, temperature, pack_current,
                       container_number, cluster_number, pack_number
                FROM eis_measurement
                WHERE cell_id = ? 
                ORDER BY real_time_id DESC 
                LIMIT ?;
            """, (cell_id, limit))
            rows = cursor.fetchall()
            return [
                EisMeasurement(
                    cell_id=row[0],
                    real_time_id=row[1],
                    frequency=row[2],
                    real_impedance=row[3],
                    imag_impedance=row[4],
                    voltage=row[5],
                    temperature=row[6],
                    pack_current=row[7],
                    container_number=row[8],
                    cluster_number=row[9],
                    pack_number=row[10]
                ) for row in rows
            ]
        finally:
            if connection:
                connection.close()



    def get_cell_history(self, cell_id: int, index: int) -> Dict[str, List[EisMeasurement]]:
        """
        Fetches the historical measurements for a specific cell based on the provided index (number of distinct real_time_id records).

        Returns:
            A dictionary where the keys are `real_time_id` values, and the values are lists of `EisMeasurement` objects.
        """
        try:
            with sqlite3.connect(DB_PATH) as connection:
                cursor = connection.cursor()
                # Fetch data grouped by real_time_id, limited to the most recent 'index' real_time_ids
                cursor.execute("""
                    SELECT cell_id, real_time_id, frequency, real_impedance, imag_impedance,
                           voltage, temperature, pack_current,
                           container_number, cluster_number, pack_number
                    FROM eis_measurement 
                    WHERE cell_id = ? 
                    ORDER BY real_time_id DESC, frequency ASC;
                """, (cell_id,))
                rows = cursor.fetchall()

                # Group the rows by real_time_id
                grouped_data = defaultdict(list)
                for row in rows:
                    measurement = EisMeasurement(
                        cell_id=row[0],
                        real_time_id=row[1],
                        frequency=row[2],
                        real_impedance=row[3],
                        imag_impedance=row[4],
                        voltage=row[5],
                        temperature=row[6],
                        pack_current=row[7],
                        container_number=row[8],
                        cluster_number=row[9],
                        pack_number=row[10]
                    )
                    grouped_data[row[1]].append(measurement)

                # Limit to the most recent 'index' real_time_id groups
                sorted_keys = sorted(grouped_data.keys(), reverse=True)[:index]
                return {key: grouped_data[key] for key in sorted_keys}

        except Exception as e:
            print(f"Error fetching cell history: {e}")
            return {}


        finally:
            if connection:
                connection.close()

    def get_latest_temperature(self,cell_id:int) -> float:
        """
        获取最新的 real_time_id 对应的温度数据。
        """
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            cursor.execute("""
                SELECT temperature
                FROM eis_measurement 
                WHERE cell_id = ? 
                ORDER BY real_time_id DESC 
                LIMIT 1;
            """, (cell_id,))
            row = cursor.fetchone()
            
            if row:
                return float(row[0])
            else:
                return None
        except Exception as e:
            print(f"Error fetching latest temperature: {e}")
            return None
        finally:
            if connection:
                connection.close()

    def delete_all_data(self):
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()

            cursor.execute("DELETE FROM eis_measurement")
            cursor.execute("DELETE FROM generated_info")
            cursor.execute("DELETE FROM battery_pack")
            connection.commit()
            connection.close()

            print("所有数据已成功删除")
        except Exception as e:
            print(f"数据删除失败: {str(e)}")
            connection.rollback()  
            connection.close()
