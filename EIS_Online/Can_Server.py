import time
from tools.CAN_Tool import CANReader

class CAN_SERVER():
     
    def __init__(self):
        self.reader = None

    def start_loop(self):
 
        # Initialize CAN Reader with identifiers and configuration
        self.reader = CANReader()  
        self.reader.start_reading()
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping CAN server...")            
            self.stop_loop()

    def stop_loop(self):
        if self.reader:
            self.reader.close()

if __name__ == "__main__":
    
    server = CAN_SERVER()
    server.start_loop()