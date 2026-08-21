#!/usr/bin/env python3
"""
CAN测试上位机系统 - 基于CANReader类
支持：定期测试、EIS扫频测试、异常监控、日志记录
"""

import json
import time
import logging
import threading
import os
import csv
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import queue

# 导入你的CANReader类
from tools.CAN_Tool import CANReader

class TestResult(Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NO_RESPONSE = "NO_RESPONSE"

@dataclass
class TestCommand:
    command: str
    param1: float = 0.0
    param2: float = 0.0
    description: str = ""
    expected_timeout: float = 2.0

@dataclass
class TestResponse:
    command: str
    response_data: str
    timestamp: datetime
    result: TestResult
    error_message: str = ""

class CAN_Tester:
    def __init__(self, config_file="test_command.json"):

        
        self.config = self.load_config(config_file)
        self.setup_logging()
        
        # 使用CANReader处理CAN总线
        self.can_reader = None
        self.running = False
        self.test_thread = None
        self.response_queue = queue.Queue()
        self.command_history = []
        self.response_history = []
        
        # EIS状态扫频状态
        self.eis_sweep_in_progress = False
        # 初始化CANReader
        self.setup_can_reader()
        
    def load_config(self, config_file: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"配置文件加载成功: {config_file}")
            return config
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            # 使用默认配置
            return {
                "can_config": {
                    "channel": "can0",
                    "bitrate": 500000,
                    "message_id": 16,
                    "timeout": 0.1
                },
                "test_config": {
                    "test_interval_seconds": 10,
                    "max_retries": 3,
                    "retry_delay_seconds": 1,
                    "eis_sweep_enabled": True,
                    "eis_sweep_interval_seconds": 300
                }
            }
    
    def setup_logging(self):
        """设置日志系统"""
        log_config = self.config.get("logging_config", {})
        log_file = log_config.get("log_file", "can_test_log.txt")
        error_log_file = log_config.get("error_log_file", "can_error_log.txt")
        
        # 主日志
        self.logger = logging.getLogger("CAN_Tester")
        self.logger.setLevel(logging.INFO)
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 错误文件处理器
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        error_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.logger.addHandler(console_handler)
        
        # 数据日志文件
        self.data_log_file = log_config.get("data_log_file", "eis_data_log.csv")
        self.setup_data_logging()
        
        self.log_info("日志系统初始化完成")
    
    def setup_data_logging(self):
        """设置数据日志（CSV格式）"""
        try:
            # 创建CSV文件并写入标题
            if not os.path.exists(self.data_log_file):
                with open(self.data_log_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'command', 'param1', 'param2',
                        'response', 'result', 'error_message'
                    ])
        except Exception as e:
            self.log_error(f"设置数据日志失败: {e}")
    
    def log_info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
        print(f"[INFO] {message}")
    
    def log_error(self, message: str):
        """记录错误日志"""
        self.logger.error(message)
        print(f"[ERROR] {message}")
    
    def log_data(self, command: str, param1: float, param2: float, 
                response: str, result: TestResult, error_msg: str = ""):
        """记录测试数据到CSV"""
        try:
            with open(self.data_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    command,
                    param1,
                    param2,
                    response,
                    result.value,
                    error_msg
                ])
        except Exception as e:
            self.log_error(f"记录数据失败: {e}")
    
    def setup_can_reader(self):
        """初始化CANReader"""
        can_config = self.config.get("can_config", {})
        channel = can_config.get("channel", "can1")
        bitrate = can_config.get("bitrate", 500000)
        timeout = can_config.get("timeout", 0.1)
        
        # 解析十六进制的message_id
        message_id_str = can_config.get("message_id", "0x10")
        if isinstance(message_id_str, str) and message_id_str.startswith("0x"):
            message_id = int(message_id_str, 16)
        else:
            message_id = int(message_id_str)
        
        try:
            # 创建CANReader实例
            self.can_reader = CANReader(
                channel=channel,
                bitrate=str(bitrate),
                timeout_duration=timeout,
                message_id=message_id,  # 传入整数类型
                on_eis_complete=self._on_eis_sweep_complete  # 设置回调
            )
            
            self.can_reader.start_reading()
            
            self.log_info(f"CANReader初始化成功: {channel}@{bitrate}bps, Message ID: 0x{message_id:X}")
            return True
            
        except Exception as e:
            self.log_error(f"初始化CANReader失败: {e}")
            self.can_reader = None
            return False
    
    def build_command(self, address: int, cmd: str, param1: float = 0.0, param2: float = 0.0) -> str:
        """构建下位机命令字符串"""
        # 根据你的协议格式: @0x地址,命令,参数1,参数2
        command_str = f"@0x{address:02X},{cmd},{param1:.6f},{param2:.6f}\n"
        return command_str
    
    def send_command(self, command: TestCommand) -> TestResponse:
        """使用CANReader发送单个命令并等待响应"""
        if not self.can_reader:
            return TestResponse(
                command=command.command,
                response_data="",
                timestamp=datetime.now(),
                result=TestResult.ERROR,
                error_message="CANReader未初始化"
            )
        
        # 解析目标地址（支持十六进制字符串）
        target_addr_str = self.config["device_config"]["target_address"]
        if isinstance(target_addr_str, str) and target_addr_str.startswith("0x"):
            target_addr = int(target_addr_str, 16)
        else:
            target_addr = int(target_addr_str)
        
        command_str = self.build_command(target_addr, command.command, command.param1, command.param2)
        
        self.log_info(f"发送命令: {command_str.strip()}")
        
        # 使用CANReader的write_data方法发送命令
        try:
            self.can_reader.write_data(command_str)
            
            # 等待响应
            response = self.wait_for_response(command)
            return response
            
        except Exception as e:
            error_msg = f"发送命令失败: {e}"
            self.log_error(error_msg)
            return TestResponse(
                command=command.command,
                response_data="",
                timestamp=datetime.now(),
                result=TestResult.ERROR,
                error_message=error_msg
            )
    
    def wait_for_response(self, command: TestCommand) -> TestResponse:
        """等待并解析响应"""
        timeout = command.expected_timeout
        start_time = time.time()
        
        # 清空之前的接收数据
        if hasattr(self.can_reader, 'data'):
            self.can_reader.data.clear()
        
        while time.time() - start_time < timeout:
            try:
                # 检查CANReader是否接收到新数据
                if hasattr(self.can_reader, 'data') and self.can_reader.data:
                    # 获取最新接收的数据
                    response_str = self.can_reader.data[-1]
                    
                    self.log_info(f"收到响应: {response_str}")
                    
                    # 解析响应（根据你的下位机响应格式）
                    if "CMD_OK" in response_str or ">" in response_str:
                        return TestResponse(
                            command=command.command,
                            response_data=response_str,
                            timestamp=datetime.now(),
                            result=TestResult.SUCCESS
                        )
                    elif "ERROR" in response_str or "FAIL" in response_str:
                        return TestResponse(
                            command=command.command,
                            response_data=response_str,
                            timestamp=datetime.now(),
                            result=TestResult.ERROR,
                            error_message=response_str
                        )
                    else:
                        # 其他类型的响应
                        return TestResponse(
                            command=command.command,
                            response_data=response_str,
                            timestamp=datetime.now(),
                            result=TestResult.SUCCESS,
                            error_message=""
                        )
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.01)
                
            except Exception as e:
                self.log_error(f"接收响应时出错: {e}")
                time.sleep(0.1)
        
        # 超时
        return TestResponse(
            command=command.command,
            response_data="",
            timestamp=datetime.now(),
            result=TestResult.TIMEOUT,
            error_message="响应超时"
        )
    
    def run_basic_test(self):
        """执行基本命令测试"""
        self.log_info("开始基本命令测试...")
        
        commands = [
            TestCommand("STAT", 0, 0, "获取系统状态", 10.0),
            # TestCommand("GETT", 0, 0, "获取温度", 2.0),
            TestCommand("GETID", 0, 0, "获取ID信息", 10.0),
            TestCommand("GETRT", 0, 0, "获取运行时间", 10.0),
            TestCommand("GETCFG", 0, 0, "获取配置", 10.0),
        ]
        
        results = []
        for cmd in commands:
            response = self.send_command(cmd)
            results.append(response)
            
            # 记录结果
            self.log_data(
                cmd.command, cmd.param1, cmd.param2,
                response.response_data, response.result,
                response.error_message
            )
            
            # 短暂延迟
            time.sleep(0.5)
        
        # 统计结果
        success_count = sum(1 for r in results if r.result == TestResult.SUCCESS)
        self.log_info(f"基本测试完成: 成功 {success_count}/{len(commands)}")
        
        return results
    
    def _on_eis_sweep_complete(self):
        """EIS扫频完成回调"""
        self.eis_sweep_in_progress = False
        self.log_info("EIS扫频完成（数据已存入数据库）")

    def run_eis_sweep_test(self):
        """执行EIS扫频测试"""
        self.log_info("开始EIS扫频测试...")
        
        # 检查是否已有扫频在进行
        if self.eis_sweep_in_progress:
            self.log_warning("EIS扫频正在进行中，请等待完成")
            return
        

        self.configure_eis_parameters()
        
        # 启动扫频测试
        sweep_cmd = TestCommand("GETE", 10, 0, "启动EIS扫频", 30.0)
        response = self.send_command(sweep_cmd)
        
        # 记录扫频开始时间
        if response.result == TestResult.SUCCESS:
            self.last_eis_start_time = datetime.now()
            self.eis_sweep_in_progress = True
            self.log_info(f"EIS扫频测试已启动，ID: {self.last_eis_start_time.strftime('%Y%m%d_%H%M%S')}")
            
            # 启动后台线程监控扫频进度（可选）
            if self.config.get("test_config", {}).get("monitor_eis_progress", True):
                threading.Thread(
                    target=self.monitor_eis_progress,
                    args=(self.last_eis_start_time,),
                    daemon=True
                ).start()
    
        else:
            self.log_error(f"EIS扫频测试启动失败: {response.error_message}")
        
        return response
    
    def monitor_eis_progress(self, start_time):
        """后台监控EIS扫频进度"""
        max_duration = 1000  # 最大预计持续时间（秒）
        check_interval = 10  # 检查间隔（秒）
        
        self.log_info(f"开始监控EIS扫频进度，预计最大时长: {max_duration}秒")
        
        elapsed = 0
        while elapsed < max_duration and self.eis_sweep_in_progress:
            time.sleep(check_interval)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # 可以在这里添加进度检查逻辑
            if elapsed % 30 == 0:  # 每30秒输出一次进度
                self.log_info(f"EIS扫频进行中... 已运行: {elapsed:.0f}秒")
        

    def configure_eis_parameters(self):
        """配置EIS参数"""
        eis_config = self.config.get("eis_config", {})
        
        commands = [
            TestCommand("SET_EIS_AMP", eis_config.get("amplitude", 0.6), 0, "设置振幅"),
            TestCommand("SET_EIS_BIAS", eis_config.get("bias", 200), 0, "设置偏置"),
            TestCommand("SET_EIS_FREQ_START", eis_config.get("freq_start", 10000), 0, "设置起始频率"),
            TestCommand("SET_EIS_FREQ_END", eis_config.get("freq_end", 10), 0, "设置结束频率"),
            TestCommand("SET_EIS_FREQ_POINTS", eis_config.get("freq_points", 5), 0, "设置频率点数"),
        ]
        
        for cmd in commands:
            response = self.send_command(cmd)
            self.log_info(f"{cmd.description}: {response.result}")
            time.sleep(0.5)
    
    def periodic_test_loop(self):
        """周期性测试循环"""
        test_config = self.config.get("test_config", {})
        interval = test_config.get("test_interval_seconds", 10)
        eis_interval = test_config.get("eis_sweep_interval_seconds", 300)
        eis_enabled = test_config.get("eis_sweep_enabled", True)
        
        last_eis_time = 0
        
        self.log_info(f"周期性测试启动，间隔: {interval}秒")
        
        while self.running:
            try:
                current_time = time.time()
                
                # 执行基本测试
                self.log_info("=" * 50)
                self.log_info(f"执行周期性测试 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                # self.run_basic_test()
                
                # 检查是否执行EIS扫频测试
                if eis_enabled and not self.eis_sweep_in_progress and (current_time - last_eis_time) >= eis_interval:
                    self.log_info("执行定期EIS扫频测试...")
                    self.run_eis_sweep_test()
                    last_eis_time = current_time
                
                # 等待下一个周期
                for i in range(interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                self.log_error(f"周期性测试出错: {e}")
                time.sleep(5)
    
    def start_testing(self):
        """启动测试系统"""
        if not self.can_reader:
            self.log_error("CANReader未初始化，无法启动测试")
            return False
        
        self.running = True
        
        # 启动周期性测试线程
        self.test_thread = threading.Thread(target=self.periodic_test_loop, daemon=True)
        # self.test_thread = threading.Thread(target=self.run_basic_test, daemon=True)
        self.test_thread.start()
        
        self.log_info("测试系统已启动")
        return True
    
    def stop_testing(self):
        """停止测试系统"""
        self.log_info("停止测试系统...")
        self.running = False
        
        if self.test_thread:
            self.test_thread.join(timeout=5)
        
        if self.can_reader:
            try:
                self.can_reader.stop_reading()
                self.can_reader.close()
                self.log_info("CANReader已关闭")
            except Exception as e:
                self.log_error(f"关闭CANReader时出错: {e}")
        
        self.log_info("测试系统已停止")
    
    def interactive_mode(self):
        """交互式命令模式"""
        self.log_info("进入交互式命令模式，输入 'help' 查看命令，'exit' 退出")
        
        commands_help = """
可用命令:
  help - 显示帮助信息
  exit - 退出交互模式
  list - 列出所有支持的指令
  send <cmd> [param1] [param2] - 发送命令
  test - 执行基本测试
  eis - 执行EIS扫频测试
  config - 配置EIS参数
  status - 查看测试状态
  log <level> <message> - 记录日志
  data - 查看最近接收的数据
  clear - 清空接收缓冲区
        """
        
        while True:
            try:
                user_input = input("\nCAN测试> ").strip()
                
                if not user_input:
                    continue
                
                parts = user_input.split()
                cmd = parts[0].lower()
                
                if cmd == "exit":
                    self.log_info("退出交互模式")
                    break
                
                elif cmd == "help":
                    print(commands_help)
                
                elif cmd == "list":
                    self.list_supported_commands()
                
                elif cmd == "send" and len(parts) >= 2:
                    command = parts[1]
                    param1 = float(parts[2]) if len(parts) > 2 else 0.0
                    param2 = float(parts[3]) if len(parts) > 3 else 0.0
                    
                    test_cmd = TestCommand(command, param1, param2, f"手动发送: {command}")
                    response = self.send_command(test_cmd)
                    print(f"响应: {response.response_data}")
                    print(f"结果: {response.result}")
                    if response.error_message:
                        print(f"错误: {response.error_message}")
                
                elif cmd == "test":
                    self.run_basic_test()
                
                elif cmd == "eis":
                    self.run_eis_sweep_test()
                
                elif cmd == "config":
                    self.configure_eis_parameters()
                
                elif cmd == "status":
                    self.show_status()
                
                elif cmd == "log" and len(parts) >= 3:
                    level = parts[1].upper()
                    message = " ".join(parts[2:])
                    
                    if level == "INFO":
                        self.log_info(f"[手动] {message}")
                    elif level == "ERROR":
                        self.log_error(f"[手动] {message}")
                    else:
                        print(f"未知日志级别: {level}")
                
                elif cmd == "data":
                    self.show_received_data()
                
                elif cmd == "clear":
                    if hasattr(self.can_reader, 'data'):
                        self.can_reader.data.clear()
                        print("接收缓冲区已清空")
                
                else:
                    print(f"未知命令: {cmd}")
                    print("输入 'help' 查看可用命令")
                    
            except KeyboardInterrupt:
                print("\n接收到中断信号")
                break
            except Exception as e:
                print(f"执行命令时出错: {e}")
    
    def show_received_data(self):
        """显示最近接收的数据"""
        if hasattr(self.can_reader, 'data') and self.can_reader.data:
            print(f"\n最近接收的 {len(self.can_reader.data)} 条数据:")
            for i, data in enumerate(self.can_reader.data[-10:], 1):  # 显示最近10条
                print(f"  {i}. {data}")
        else:
            print("暂无接收数据")
    
    def list_supported_commands(self):
        """列出所有支持的指令"""
        commands = [
            # 状态查询
            "STAT", "GETID", "GETRT", "GETCFG", "GETLOG",
            # 数据获取
            "GETV", "GETI", "GETT", "GETE", "GETZ",
            # EIS设置
            "SET_EIS_AMP", "SET_EIS_BIAS", "SET_EIS_CYCLES",
            "SET_EIS_FREQ_START", "SET_EIS_FREQ_END", "SET_EIS_FREQ_POINTS",
            # 报警设置
            "SET_TEMP_HIGH_ALARM", "SET_VOLT_CELL_HIGH", "SET_VOLT_CELL_LOW",
            "SET_CURR_CHG_ALARM", "SET_CURR_DIS_ALARM", "SET_CELL_COUNT",
            # 系统控制
            "RST", "PAUSE", "RESUME", "ABORT", "CALIBRATE",
            "IDRST", "RTRST", "ERASEALL", "SET_CALIB_DATA"
        ]
        
        print("\n支持的指令列表:")
        for i, cmd in enumerate(commands, 1):
            print(f"  {i:2d}. {cmd}")
    
    def show_status(self):
        """显示系统状态"""
        print("\n=== 系统状态 ===")
        print(f"运行状态: {'运行中' if self.running else '已停止'}")
        print(f"CANReader: {'已连接' if self.can_reader else '未连接'}")
        print(f"命令历史: {len(self.command_history)} 条")
        print(f"响应历史: {len(self.response_history)} 条")
        
        if hasattr(self.can_reader, 'data'):
            print(f"接收数据: {len(self.can_reader.data)} 条")
        
        if self.response_history:
            last_resp = self.response_history[-1]
            print(f"最后响应: {last_resp.command} - {last_resp.result}")

def main():
    """主函数"""
    print("=" * 60)
    print("CAN测试上位机系统 (基于CANReader)")
    print("=" * 60)
    
    # 创建测试器
    tester = CAN_Tester("test_command.json")
    
    if not tester.can_reader:
        print("CANReader初始化失败，请检查硬件连接")
        return
    
    try:
        # 启动测试系统
        if tester.start_testing():
            # 进入交互模式
            tester.interactive_mode()
        else:
            print("测试系统启动失败")
            
    except KeyboardInterrupt:
        print("\n接收到中断信号")
    finally:
        # 停止测试
        tester.stop_testing()
        print("程序退出")

if __name__ == "__main__":
    main()