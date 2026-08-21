import can
import os

# os.system(f'sudo ifconfig can1 down 2>/dev/null')

os.system('sudo ifconfig can0 down')
os.system(f'sudo ip link set can0 type can bitrate {500000}')
os.system('sudo ifconfig can0 up')

bus = can.interface.Bus(channel="can0", bustype='socketcan', bitrate=500000)

def read_data():
    while True:
        line = read_until_end()
        if line:
            line_decoded = line.encode('utf-8', errors='replace').strip()
            print(f"Received line: {line_decoded}")
                
def read_until_end():

    received_data = ""
    bus.set_filters([])  
    print("Start receiving...")
    while True:
        msg = bus.recv(timeout=1) 
        if msg is None:
            print("Timeout waiting for CAN message")
            break
        print(f"Raw frame: ID=0x{msg.arbitration_id:X}, Data={msg.data}")
        segment = bytes(msg.data).decode('ascii')
        print(f"Received: {segment}")
        received_data += segment
        if '<' in received_data:
            line_end_index = received_data.index('<') + len('<')
            received_data = received_data[:line_end_index]
            return received_data

read_data()
