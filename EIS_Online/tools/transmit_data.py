import sqlite3
import requests
import os
import sys
import json
from datetime import datetime
import time  # 确保导入 time 模块

# 获取项目根目录
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 将项目根目录添加到 Python 模块搜索路径
sys.path.insert(0, BASE_DIR)

from database.config import DB_PATH  # 从 database.config 导入 DB_PATH

class DataTransmitter:
    def __init__(self, batch_size=100, max_retries=3, server_url="http://192.168.98.6:8080/api/v1/transmit-data"):
        self.batch_size = batch_size  # 每批次发送的记录数
        self.max_retries = max_retries  # 最大重试次数
        self.server_url = server_url  # 服务器URL

    def get_eis_data_from_db(self):
        """获取所有未发送的数据，按 real_time_id 降序排序"""
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()

            # 查询所有 sent_time 为 NULL 的数据，按 real_time_id 降序排序
            query = """
            SELECT measurement_id, cell_id, real_time_id, frequency, real_impedance, imag_impedance, voltage,
                   container_number, cluster_number, pack_number
            FROM eis_measurement
            WHERE sent_time IS NULL
            ORDER BY real_time_id DESC LIMIT ?
            """

            cursor.execute(query, (self.batch_size,))
            rows = cursor.fetchall()

            print(f"Fetched {len(rows)} rows from the database.")
            return rows
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return []
        finally:
            if connection:
                connection.close()

    def update_sent_time(self, measurement_ids):
        """批量更新 sent_time 标记"""
        if not measurement_ids:
            return
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()

            current_time = datetime.utcnow().isoformat() + 'Z'  # 使用 UTC 时间

            placeholders = ",".join("?" for _ in measurement_ids)
            query = f"UPDATE eis_measurement SET sent_time = ? WHERE measurement_id IN ({placeholders})"
            cursor.execute(query, [current_time] + measurement_ids)
            connection.commit()
            print(f"Updated sent_time for {len(measurement_ids)} records.")
        except sqlite3.Error as e:
            print(f"Database error while updating sent_time: {e}")
        finally:
            if connection:
                connection.close()

    def format_data(self, rows):
        """将数据库行数据格式化为 JSON 格式"""
        measurements = []
        for row in rows:
            (measurement_id, cell_id, real_time_id, frequency, real_imp, imag_imp, voltage,
             container_number, cluster_number, pack_number) = row

            # 将 real_time_id 转换为 ISO8601 格式，确保包含 'T'
            try:
                creation_time = datetime.strptime(real_time_id, "%Y-%m-%d %H:%M:%S").isoformat() + 'Z'
            except ValueError as e:
                print(f"Time format error for measurement_id {measurement_id}: {e}")
                # 设置为当前时间
                creation_time = datetime.utcnow().isoformat() + 'Z'

            # 处理无效值
            voltage = voltage if voltage > 0 else 0.01  # 电压不能为零或负数

            # 保留阻抗的原始值（允许负数）
            real_imp = real_imp
            imag_imp = imag_imp

            measurement = {
                "containerId": str(container_number),
                "clusterId": str(cluster_number),
                "packId": str(pack_number),
                "cellId": str(cell_id),
                "temperature": 25.0,  # 示例温度，可以根据实际情况修改
                "voltage": voltage,
                "frequency": frequency,
                "realImpedance": real_imp,
                "imaginaryImpedance": imag_imp,
                "creationTime": creation_time  # 保留并上传 creationTime
            }

            measurements.append(measurement)

        if not measurements:
            print("No valid measurements to send.")
            return None

        return {
            "eisMeasurements": measurements
        }

    def send_data_to_docker(self, data):
        """发送 JSON 数据到 Docker 服务器，带重试机制"""
        headers = {"Content-Type": "application/json"}

        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"Attempt {attempt}: Sending {len(data['eisMeasurements'])} records to server...")

                response = requests.post(self.server_url, json=data, headers=headers)

                if response.status_code in [200, 201]:
                    print(f"Data sent successfully. Status code: {response.status_code}")
                    return True
                else:
                    print(f"Failed to send data. Status code: {response.status_code}")
                    print(f"Response content: {response.content.decode('utf-8')}")
            except requests.exceptions.RequestException as e:
                print(f"Request error on attempt {attempt}: {e}")

            # 等待一段时间后重试
            wait_time = 5 * attempt  # 指数等待
            print(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)

        return False

    def upload_data(self):
        """获取数据并上传到服务器"""
        rows = self.get_eis_data_from_db()
        if not rows:
            print("No more unsent data.")
            return

        # 格式化数据
        request_data = self.format_data(rows)
        if request_data is None:
            print("No valid data to send.")
            return

        # 上传数据到服务器
        if self.send_data_to_docker(request_data):
            measurement_ids = [row[0] for row in rows]
            self.update_sent_time(measurement_ids)
            print(f"Uploaded {len(measurement_ids)} records.")
        else:
            print("Failed to upload data.")
