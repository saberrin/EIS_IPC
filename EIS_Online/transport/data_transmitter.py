#!/usr/bin/env python3
"""
下位机 EIS SQLite -> 网页服务器 API 上传脚本。

用法示例：
  python3 -m transport.data_transmitter
  python3 -m transport.data_transmitter --server-url http://192.168.98.2:8080/api/v1/transmit-data
  python3 -m transport.data_transmitter --loop --interval-seconds 10

注意：
- 默认每次只上传同一个 container/cluster/pack/cell/real_time_id 的完整频率扫描。
- 只有 API 返回 2xx 成功后，才会把这些 measurement_id 标记 sent_time。
- 默认服务器地址按当前网页服务器 USB/RJ45 网卡 IP 设置为 192.168.98.2。
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

# 获取项目根目录，并兼容原下位机项目里的 database.config.DB_PATH
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

from database.config import DB_PATH


DEFAULT_SERVER_URL = "http://192.168.98.2:8080/api/v1/transmit-data"
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_LOOP_INTERVAL_SECONDS = 10


class DataTransmitter:
    def __init__(
        self,
        server_url=DEFAULT_SERVER_URL,
        max_retries=DEFAULT_MAX_RETRIES,
        request_timeout_seconds=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ):
        self.server_url = server_url
        self.max_retries = max_retries
        self.request_timeout_seconds = request_timeout_seconds

    def get_next_unsent_eis_scan(self):
        """获取一个 cell 在一个 real_time_id 下的完整 EIS 频率扫描。"""
        connection = None
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()

            # 先锁定一个未发送的扫描批次，避免把不同 cell/不同测量时间混在一次上传里。
            batch_query = """
            SELECT container_number, cluster_number, pack_number, cell_id, real_time_id
            FROM eis_measurement
            WHERE sent_time IS NULL
            ORDER BY real_time_id ASC
            LIMIT 1
            """
            cursor.execute(batch_query)
            batch = cursor.fetchone()

            if not batch:
                print("No unsent EIS scan found.")
                return []

            container_number, cluster_number, pack_number, cell_id, real_time_id = batch

            data_query = """
            SELECT measurement_id,
                   cell_id,
                   real_time_id,
                   frequency,
                   real_impedance,
                   imag_impedance,
                   voltage,
                   container_number,
                   cluster_number,
                   pack_number
            FROM eis_measurement
            WHERE sent_time IS NULL
              AND container_number = ?
              AND cluster_number = ?
              AND pack_number = ?
              AND cell_id = ?
              AND real_time_id = ?
            ORDER BY frequency DESC
            """
            cursor.execute(
                data_query,
                (container_number, cluster_number, pack_number, cell_id, real_time_id),
            )
            rows = cursor.fetchall()

            print(
                "Fetched "
                f"{len(rows)} points for "
                f"container={container_number}, "
                f"cluster={cluster_number}, "
                f"pack={pack_number}, "
                f"cell={cell_id}, "
                f"real_time_id={real_time_id}."
            )
            return rows
        except sqlite3.Error as error:
            print(f"Database error while reading EIS data: {error}")
            return []
        finally:
            if connection:
                connection.close()

    def update_sent_time(self, measurement_ids):
        """只有上传成功后才批量更新 sent_time。"""
        if not measurement_ids:
            return

        connection = None
        try:
            connection = sqlite3.connect(DB_PATH)
            cursor = connection.cursor()
            current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            placeholders = ",".join("?" for _ in measurement_ids)
            query = f"UPDATE eis_measurement SET sent_time = ? WHERE measurement_id IN ({placeholders})"
            cursor.execute(query, [current_time] + measurement_ids)
            connection.commit()
            print(f"Updated sent_time for {len(measurement_ids)} records.")
        except sqlite3.Error as error:
            print(f"Database error while updating sent_time: {error}")
        finally:
            if connection:
                connection.close()

    def format_creation_time(self, real_time_id):
        """把 SQLite 里的 real_time_id 转成 API 接收的 ISO8601 字符串。"""
        if real_time_id is None:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        raw_value = str(real_time_id).strip()
        if not raw_value:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 已经是 ISO 格式时，尽量少改动。
        if "T" in raw_value:
            if raw_value.endswith("Z") or "+" in raw_value or raw_value.rfind("-") > raw_value.find("T"):
                return raw_value
            return f"{raw_value}Z"

        # 原旧脚本格式：2026-06-17 10:30:00
        try:
            parsed_time = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
            return parsed_time.isoformat() + "Z"
        except ValueError as error:
            print(f"Time format error for real_time_id={real_time_id}: {error}")
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def format_data(self, rows):
        """将 SQLite 行转换为后端 /api/v1/transmit-data 接收的 JSON。"""
        measurements = []

        for row in rows:
            (
                measurement_id,
                cell_id,
                real_time_id,
                frequency,
                real_impedance,
                imag_impedance,
                voltage,
                container_number,
                cluster_number,
                pack_number,
            ) = row

            if frequency is None or real_impedance is None or imag_impedance is None:
                print(f"Skip invalid point measurement_id={measurement_id}: missing frequency/impedance.")
                continue

            safe_voltage = voltage if voltage is not None and voltage > 0 else 0.01

            measurements.append(
                {
                    "containerId": str(container_number),
                    "clusterId": str(cluster_number),
                    "packId": str(pack_number),
                    "cellId": str(cell_id),
                    "temperature": 25.0,
                    "voltage": float(safe_voltage),
                    "frequency": float(frequency),
                    "realImpedance": float(real_impedance),
                    "imaginaryImpedance": float(imag_impedance),
                    "creationTime": self.format_creation_time(real_time_id),
                }
            )

        if not measurements:
            print("No valid measurements to send.")
            return None

        return {"eisMeasurements": measurements}

    def send_data_to_server(self, data):
        headers = {"Content-Type": "application/json"}

        for attempt in range(1, self.max_retries + 1):
            try:
                print(
                    f"Attempt {attempt}: sending "
                    f"{len(data['eisMeasurements'])} points to {self.server_url} ..."
                )
                response = requests.post(
                    self.server_url,
                    json=data,
                    headers=headers,
                    timeout=self.request_timeout_seconds,
                )

                if 200 <= response.status_code < 300:
                    print(f"Data sent successfully. Status code: {response.status_code}")
                    print(f"Response: {response.text}")
                    return True

                print(f"Failed to send data. Status code: {response.status_code}")
                print(f"Response content: {response.text}")
            except requests.exceptions.RequestException as error:
                print(f"Request error on attempt {attempt}: {error}")

            wait_time = 5 * attempt
            print(f"Waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)

        return False

    def upload_once(self):
        rows = self.get_next_unsent_eis_scan()
        if not rows:
            return False

        request_data = self.format_data(rows)
        if request_data is None:
            return False

        if self.send_data_to_server(request_data):
            measurement_ids = [row[0] for row in rows]
            self.update_sent_time(measurement_ids)
            print(f"Uploaded {len(measurement_ids)} records.")
            return True

        print("Failed to upload data. sent_time was not updated, so this scan can retry later.")
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="Upload raw EIS points from SQLite to web server API.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="Target API URL.")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Max retry attempts.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument("--loop", action="store_true", help="Keep uploading scans forever.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_LOOP_INTERVAL_SECONDS,
        help="Sleep seconds between loop uploads.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    transmitter = DataTransmitter(
        server_url=args.server_url,
        max_retries=args.max_retries,
        request_timeout_seconds=args.timeout_seconds,
    )

    print(f"DB_PATH: {DB_PATH}")
    print(f"Server URL: {args.server_url}")

    if not args.loop:
        transmitter.upload_once()
        return

    while True:
        transmitter.upload_once()
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
