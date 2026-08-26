from database.config import DB_PATH
import sqlite3
from datetime import datetime
import time
import threading
import re
from pathlib import Path

from typing import List
from database.db_init import init_database
from database.repository import Repository
from database.entity import EisMeasurement

import json
import can
import os


PROJECT_DIR = Path(__file__).resolve().parent.parent


class CANReader:
    
    def __init__(
        self,
        channel="can1",
        bitrate="500000",
        timeout_duration=1,
        message_id=0x10,
        on_eis_complete=None,
        address_mapping_path=None,
    ):
        super().__init__()
        os.system(f'sudo ip link set {channel} type can bitrate {bitrate}')
        os.system(f'sudo ifconfig {channel} up')

        self.bus = None
           
        # 尝试初始化bus，如果失败则保持为None
        try:
            self.bus = can.interface.Bus(channel=channel, bustype='socketcan', bitrate=bitrate)
        except Exception as e:
            print(f"初始化CAN总线失败: {e}")
            self.bus = None

        self.db_path = DB_PATH

        self.message_id = message_id

        self.chunk_size = 1
        self.line_ending = b'<'
        self.timeout_duration = timeout_duration
        self.running = True
        self.data = []
        self.temperature = None
        self.voltage = None
        self.repo = Repository()

        # 回调函数 - EIS扫频完成回调
        self.on_eis_complete = on_eis_complete

        self.real_time_id = None
        
        # 从配置文件加载地址映射
        self.address_mapping_path = Path(address_mapping_path) if address_mapping_path else PROJECT_DIR / "address_mapping.json"
        self.address_mapping = self.load_address_mapping()
        
        # 不再需要用户输入，从配置文件中获取
        self.container_number = None
        self.cluster_number = None
        self.pack_number = None

        self.database_init()
        # self.setup_can_interface(channel,bitrate)

    def setup_can_interface(self, channel, bitrate):
        """设置CAN接口"""
        try:
            # 先关闭可能存在的CAN接口
            os.system(f'sudo ifconfig {channel} down 2>/dev/null')
            
            # 设置CAN接口
            result = os.system(f'sudo ip link set {channel} type can bitrate {bitrate}')
            if result != 0:
                print(f"Warning: Failed to set CAN bitrate, may already be configured")
            
            # 启动CAN接口
            result = os.system(f'sudo ifconfig {channel} up')
            if result != 0:
                print(f"Error: Failed to bring up {channel}")
                return False
            
            time.sleep(0.5)  # 等待接口启动
            
            # 创建CAN总线对象
            self.bus = can.interface.Bus(
                channel=channel, 
                bustype='socketcan', 
                bitrate=bitrate
            )
            print(f"CAN interface {channel} initialized successfully")
            return True
            
        except Exception as e:
            print(f"Error setting up CAN interface: {e}")
            self.bus = None
            return False
        

    def database_init(self):
        """初始化 SQLite 结构并建立连接。"""
        try:
            init_database()
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
            print("SQLite database connection successful")
        except Exception as e:
            print(f"Error connecting to SQLite database: {e}")
            self.connection = None

    def load_address_mapping(self):
        """加载板卡级映射：板卡地址只决定 Container/Cluster/Pack。"""
        try:
            with open(self.address_mapping_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                mapping = {}
                for item in config.get("address_mapping", []):
                    # 处理16进制地址字符串
                    addr_str = str(item["addr_id"]).strip().upper()
                    if addr_str.startswith("0X"):
                        addr_id = int(addr_str, 16)
                    else:
                        addr_id = int(addr_str)

                    if addr_id in mapping:
                        raise ValueError(f"Duplicate board address: 0x{addr_id:02X}")

                    board_mapping = {
                        "container_number": int(item["container_number"]),
                        "cluster_number": int(item["cluster_number"]),
                        "pack_number": int(item["pack_number"]),
                    }
                    if any(value <= 0 for value in board_mapping.values()):
                        raise ValueError(f"Invalid topology for board 0x{addr_id:02X}: {board_mapping}")
                    mapping[addr_id] = board_mapping
                print(f"Address mapping loaded successfully: {mapping}")
                return mapping
        except Exception as e:
            print(f"Error loading address mapping: {e}")
            return {}

    def start_reading(self):
        print("Starting CAN reading...")
        thread = threading.Thread(target=self.read_data, daemon=True)
        thread.start()
        time.sleep(0.1)  

    def stop_reading(self):
        print("Stopping CAN reading...")
        self.running = False

    def read_data(self):
        # data = "@0x11,GETE,10\n"
        # self.write_data(data)
        while self.running:
            line = self.read_until_end()
            if line:
                line_decoded = line.decode('utf-8', errors='replace').strip()
                print(f"Received line: {line_decoded}")
                self.data.append(line_decoded)
                self.parse_and_insert_data(line_decoded)

    def read_until_end(self):
        bus = self.bus
        if bus is None:
            time.sleep(self.timeout_duration)
            return None

        try:
            while self.running:
                received_data = b""
                while self.running:
                    msg = bus.recv(timeout=self.timeout_duration)
                    if msg is None:
                        break

                    received_data += bytes(msg.data)
                    if self.line_ending in received_data:
                        line_end_index = received_data.index(self.line_ending) + len(self.line_ending)
                        return received_data[:line_end_index]
        except (IOError, OSError) as e:
            print(f"Error in read_until_end: {e}")
            time.sleep(0.01)
        except Exception as e:
            print(f"Unexpected CAN receive error: {e}")
            time.sleep(0.05)
        return None

    def write_data(self, data_to_send):
        if isinstance(data_to_send, str):
            if not data_to_send.endswith('\n'):
                data_to_send += "\n"
            try:
                data_bytes = list(data_to_send.encode('ascii'))
                chunk_size = 8  
                for i in range(0, len(data_bytes), chunk_size):
                    chunk = data_bytes[i:i + chunk_size]
                    msg = can.Message(arbitration_id=self.message_id, data=chunk, is_extended_id=False)
                    self.bus.send(msg)
            except Exception as e:
                print(f"Error sending data: {e}")
        else:
            print("Input must be a string")

    def parse_and_insert_data(self, line: str):
        """
        Parses the incoming data line, creates EisMeasurement objects, and inserts them into the database.
        """
        try:
            line = line.strip()
            
            # 1. 扫频数据 (GETE命令) - 完整的一条命令
            if ">0x" in line and "GETE" in line and "CMD_OK" in line and ';' in line:
                try:
                    # 固件响应头: >0x11, GETE, <Cell_ID>, <Param2>,CMD_OK,
                    # 板卡地址决定 Container/Cluster/Pack，Cell_ID 决定 Pack 内 Cell。
                    header_match = re.match(
                        r"^\s*>0x([0-9A-Fa-f]+)\s*,\s*GETE\s*,\s*(\d+)\s*,",
                        line,
                    )
                    if not header_match:
                        print(f"Error: invalid GETE response header: {line}")
                        return False

                    addr_id = int(header_match.group(1), 16)
                    cell_id = int(header_match.group(2))
                    if cell_id <= 0:
                        print(f"Error: invalid Cell_ID {cell_id} from board 0x{addr_id:02X}")
                        return False
                        
                    if addr_id not in self.address_mapping:
                        print(f"Warning: No mapping found for board address 0x{addr_id:02X}")
                        return False
                        
                    mapping = self.address_mapping[addr_id]
                    container_number = mapping["container_number"]
                    cluster_number = mapping["cluster_number"]
                    pack_number = mapping["pack_number"]
                        
                    # 找到CMD_OK之后的数据部分
                    cmd_ok_index = line.find("CMD_OK")
                    if cmd_ok_index == -1:
                        print(f"Error: CMD_OK not found in sweep data: {line}")
                        return False
                        
                    # 获取CMD_OK之后的部分
                    data_part = line[cmd_ok_index + len("CMD_OK"):].strip()
                        
                    # 如果数据以逗号开头，去掉逗号
                    if data_part.startswith(','):
                        data_part = data_part[1:].strip()
                        
                    # 提取数据点
                    data_points = []
                    sections = data_part.split(';')
                        
                    for section in sections:
                        section = section.strip()
                        # 格式: R1,value,I1,value,F1,value
                        if (section.startswith('R') and 'I' in section and 'F' in section and
                                section.count(',') >= 5):
                            try:
                                parts = [part.strip() for part in section.split(',')]
                                if len(parts) >= 6:
                                    # 格式: R1,value,I1,value,F1,value
                                    real_imp = float(parts[1])
                                    imag_imp = float(parts[3])
                                    frequency = float(parts[5])
                                    data_points.append((real_imp, imag_imp, frequency))
                                    print(f"Parsed sweep point: R={real_imp}, I={imag_imp}, F={frequency}")
                            except (ValueError, IndexError) as e:
                                print(f"Error parsing sweep section: {section}, Error: {e}")
                                continue
                        
                    if data_points:
                        self.insert_measurements(
                            addr_id,
                            cell_id,
                            data_points,
                            container_number,
                            cluster_number,
                            pack_number,
                        )
                        return True

                    print(f"Warning: No valid data points in sweep data: {line}")
                    return False
                            
                except (ValueError, IndexError) as e:
                    print(f"Error parsing sweep data: {line}, Error: {e}")
                    return False
            
            # 2. 单频数据 (GETZ命令)
            # elif ">0x" in line and "GETZ" in line and "CMD_OK" in line:
            #     try:
            #         # 格式: >0x28,GETZ,0.000000,0.000000,CMD_OK,Rvalue,Ivalue,Fvalue
            #         header_part = line.split(',')[0]  # >0x28
            #         if header_part.startswith('>0x'):
            #             addr_id = int(header_part[3:], 16)
                        
            #             if addr_id not in self.address_mapping:
            #                 print(f"Warning: No mapping found for address {addr_id}")
            #                 return
                        
            #             mapping = self.address_mapping[addr_id]
            #             container_number = mapping["container_number"]
            #             cluster_number = mapping["cluster_number"]
            #             pack_number = mapping["pack_number"]
            #             cell_id = mapping["cell_id"]
                        
            #             # 提取数据点
            #             data_points = []
            #             try:
            #                 # 查找R,I,F参数的位置
            #                 r_start = line.find('R')
            #                 i_start = line.find('I')
            #                 f_start = line.find('F')
                            
            #                 if r_start != -1 and i_start != -1 and f_start != -1:
            #                     real_str = line[r_start+1:i_start]
            #                     imag_str = line[i_start+1:f_start]
            #                     freq_str = line[f_start+1:]
                                
            #                     real_imp = float(real_str)
            #                     imag_imp = float(imag_str)
            #                     frequency = float(freq_str)
                                
            #                     data_points.append((real_imp, imag_imp, frequency))
            #                     print(f"Parsed single frequency data: R={real_imp}, I={imag_imp}, F={frequency}")
            #             except (ValueError, IndexError) as e:
            #                 print(f"Error parsing single frequency data: {line}, Error: {e}")
                        
            #             if data_points:
            #                 self.insert_measurements(addr_id, cell_id, data_points, 
            #                                     container_number, cluster_number, pack_number)
            #             else:
            #                 print(f"Warning: No valid data points in single frequency data: {line}")
                            
            #     except (ValueError, IndexError) as e:
            #         print(f"Error parsing single frequency: {line}, Error: {e}")
                    
        except Exception as e:
            print(f"Unexpected error in parse_and_insert_data: {e}")
            return False

        return False

    def insert_measurements(self, addr_id: int, cell_id: int, data_points: List[tuple], 
                        container_number: int, cluster_number: int, pack_number: int):
        """
        Insert measurements into database.
        """
        real_time_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        measurements = []
        
        # Create EisMeasurement objects
        for dp in data_points:
            real_impedance, imag_impedance, frequency = dp
            
            measurement = EisMeasurement(
                cell_id=cell_id,
                real_time_id=real_time_id,
                frequency=frequency,
                real_impedance=real_impedance,
                imag_impedance=imag_impedance,
                voltage=0.0,  # 默认值
                temperature=0.0,  # 默认值
                container_number=container_number,
                cluster_number=cluster_number,
                pack_number=pack_number
            )
            measurements.append(measurement)
        
        # Insert into database using Repository
        try:
            print(f"Inserting {len(measurements)} measurements for device 0x{addr_id:X} -> cell {cell_id}")
            
            if measurements:
                self.repo.insert_measurements(measurements)
                print(f"Data inserted successfully. Batch ID: {real_time_id}")

                # 触发扫频完成回调
                if self.on_eis_complete:
                    self.on_eis_complete()
                
        except Exception as e:
            print(f"Error during data insertion: {e}")

    def close(self):
        self.stop_reading()
        if self.bus:
            self.bus.shutdown()
        if self.connection:
            self.cursor.close()
            self.connection.close()
            print("Database connection closed.")
