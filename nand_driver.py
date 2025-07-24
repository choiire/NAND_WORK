import RPi.GPIO as GPIO
import time

class MT29F4G08ABADAWP:
    def __init__(self):
        # GPIO 핀 설정
        self.RB = 13  # Ready/Busy
        self.RE = 26  # Read Enable
        self.CE = 19  # Chip Enable
        self.CLE = 11 # Command Latch Enable  
        self.ALE = 10 # Address Latch Enable
        self.WE = 9   # Write Enable
        
        # 데이터 핀
        self.IO_pins = [21, 20, 16, 12, 25, 24, 23, 18] # IO0-IO7
        
        # GPIO 초기화
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # 컨트롤 핀 출력으로 설정
        GPIO.setup(self.RB, GPIO.IN)
        GPIO.setup(self.RE, GPIO.OUT)
        GPIO.setup(self.CE, GPIO.OUT) 
        GPIO.setup(self.CLE, GPIO.OUT)
        GPIO.setup(self.ALE, GPIO.OUT)
        GPIO.setup(self.WE, GPIO.OUT)
        
        # 데이터 핀 입출력 설정
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
            
        # 초기 상태 설정
        GPIO.output(self.CE, GPIO.HIGH)  # Chip Disable
        GPIO.output(self.RE, GPIO.HIGH)  # Read Disable
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        GPIO.output(self.CLE, GPIO.LOW)  # Command Disable
        GPIO.output(self.ALE, GPIO.LOW)  # Address Disable
        
    def __del__(self):
        GPIO.cleanup()
        
    def wait_ready(self):
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기"""
        while GPIO.input(self.RB) == GPIO.LOW:
            time.sleep(0.00001)  # 10us 대기
            
    def set_data_pins_output(self):
        """데이터 핀을 출력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
            
    def write_data(self, data):
        """8비트 데이터 쓰기"""
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
            
    def read_data(self):
        """8비트 데이터 읽기"""
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
        return data
        
    def write_command(self, cmd):
        """커맨드 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        GPIO.output(self.CLE, GPIO.HIGH) # Command Latch Enable
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        
    def write_address(self, addr):
        """주소 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        GPIO.output(self.ALE, GPIO.HIGH) # Address Latch Enable
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self.write_data(addr)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        
    def write_page(self, page_addr, data):
        """한 페이지 쓰기
        page_addr: 5바이트 주소 (Row Address 3바이트 + Column Address 2바이트)
        data: 쓸 데이터 바이트 배열 (최대 2048+64 바이트)
        """
        # Serial Data Input 커맨드
        self.write_command(0x80)
        
        # 5 바이트 주소 입력
        for i in range(5):
            addr_byte = (page_addr >> (i*8)) & 0xFF
            self.write_address(addr_byte)
            
        # 데이터 쓰기
        for byte in data:
            GPIO.output(self.WE, GPIO.LOW)   # Write Enable
            self.write_data(byte)
            GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
            
        # Program 커맨드
        self.write_command(0x10)
        
        # R/B# 신호가 Ready될 때까지 대기
        self.wait_ready()
        
    def read_page(self, page_addr, length=2048):
        """한 페이지 읽기
        page_addr: 5바이트 주소 (Row Address 3바이트 + Column Address 2바이트)
        length: 읽을 바이트 수 (기본 2048)
        returns: 읽은 데이터 바이트 배열
        """
        # Read 커맨드
        self.write_command(0x00)
        
        # 5 바이트 주소 입력
        for i in range(5):
            addr_byte = (page_addr >> (i*8)) & 0xFF
            self.write_address(addr_byte)
            
        # Read Confirm 커맨드
        self.write_command(0x30)
        
        # R/B# 신호가 Ready될 때까지 대기
        self.wait_ready()
        
        # 데이터 핀을 입력 모드로 변경
        self.set_data_pins_input()
        
        data = []
        for _ in range(length):
            GPIO.output(self.RE, GPIO.LOW)   # Read Enable
            byte = self.read_data()
            GPIO.output(self.RE, GPIO.HIGH)  # Read Disable
            data.append(byte)
            
        # 데이터 핀을 출력 모드로 복귀
        self.set_data_pins_output()
        
        return bytes(data) 