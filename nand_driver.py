import RPi.GPIO as GPIO
import time

class MT29F4G08ABADAWP:
    # NAND 플래시 상수
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096
    
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
        
        try:
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
            self.reset_pins()
            
        except Exception as e:
            GPIO.cleanup()
            raise RuntimeError(f"GPIO 초기화 실패: {str(e)}")
            
    def reset_pins(self):
        """핀 상태를 안전한 기본값으로 리셋"""
        try:
            GPIO.output(self.CE, GPIO.HIGH)  # Chip Disable
            GPIO.output(self.RE, GPIO.HIGH)  # Read Disable
            GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
            GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
            GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
            self.set_data_pins_output()      # 데이터 핀을 출력 모드로 설정
        except Exception as e:
            raise RuntimeError(f"핀 리셋 실패: {str(e)}")
            
    def __del__(self):
        try:
            self.reset_pins()
            GPIO.cleanup()
        except:
            pass

    def validate_page(self, page_no: int):
        """페이지 번호 유효성 검사"""
        if not isinstance(page_no, int):
            raise TypeError("페이지 번호는 정수여야 합니다")
        if page_no < 0 or page_no >= self.TOTAL_BLOCKS * self.PAGES_PER_BLOCK:
            raise ValueError(f"유효하지 않은 페이지 번호: {page_no}")

    def validate_block(self, block_no: int):
        """블록 번호 유효성 검사"""
        if not isinstance(block_no, int):
            raise TypeError("블록 번호는 정수여야 합니다")
        if block_no < 0 or block_no >= self.TOTAL_BLOCKS:
            raise ValueError(f"유효하지 않은 블록 번호: {block_no}")

    def validate_data_size(self, data: bytes):
        """데이터 크기 유효성 검사"""
        if not isinstance(data, bytes):
            raise TypeError("데이터는 bytes 타입이어야 합니다")
        if len(data) > self.PAGE_SIZE + self.SPARE_SIZE:
            raise ValueError(f"데이터 크기가 너무 큽니다: {len(data)} bytes")
        if len(data) == 0:
            raise ValueError("데이터가 비어있습니다")

    def check_operation_status(self):
        """작업 상태 확인"""
        self.write_command(0x70)  # Read Status
        status = self.read_data()
        if status & 0x01:  # Fail bit
            raise RuntimeError("작업 실패")
        return True

    def wait_ready(self):
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기"""
        while GPIO.input(self.RB) == GPIO.LOW:
            time.sleep(0.00001)  # 10us 대기
            
    def set_data_pins_output(self):
        """데이터 핀을 출력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
        time.sleep(0.00001)  # 10us 대기
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
        time.sleep(0.00001)  # 10us 대기
            
    def write_data(self, data):
        """8비트 데이터 쓰기"""
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
        time.sleep(0.00001)  # 10us 대기
            
    def read_data(self):
        """8비트 데이터 읽기"""
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
        time.sleep(0.00001)  # 10us 대기
        return data
        
    def write_command(self, cmd):
        """커맨드 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.CLE, GPIO.HIGH) # Command Latch Enable
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        time.sleep(0.00001)  # 10us 대기
        
    def write_address(self, addr):
        """주소 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        GPIO.output(self.ALE, GPIO.HIGH) # Address Latch Enable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self.write_data(addr)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        time.sleep(0.00001)  # 10us 대기
        
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        time.sleep(0.00001)  # 10us 대기
        
    def write_page(self, page_no: int, data: bytes):
        """한 페이지 쓰기"""
        try:
            self.validate_page(page_no)
            self.validate_data_size(data)
            
            # 데이터 핀을 미리 출력으로 설정
            self.set_data_pins_output()

            # Serial Data Input 커맨드
            self.write_command(0x80)

            # Column & Row Address 한번에 처리
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            
            # Column Address (고정 0x0000)
            GPIO.output(self.WE, GPIO.LOW)
            self.write_data(0x00)
            GPIO.output(self.WE, GPIO.HIGH)
            
            GPIO.output(self.WE, GPIO.LOW)
            self.write_data(0x00)
            GPIO.output(self.WE, GPIO.HIGH)

            # Row Address (3바이트)
            for i in range(3):
                GPIO.output(self.WE, GPIO.LOW)
                self.write_data((page_no >> (8 * i)) & 0xFF)
                GPIO.output(self.WE, GPIO.HIGH)
                
            GPIO.output(self.ALE, GPIO.LOW)

            # 데이터 쓰기
            for byte in data:
                GPIO.output(self.WE, GPIO.LOW)
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                
            # Program 커맨드
            self.write_command(0x10)
            
            # Ready 대기 및 상태 확인
            self.wait_ready()
            self.check_operation_status()
            
        except Exception as e:
            self.reset_pins()
            raise RuntimeError(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
            
    def read_page(self, page_no: int, length: int = 2048):
        """한 페이지 읽기"""
        try:
            self.validate_page(page_no)
            if length > self.PAGE_SIZE + self.SPARE_SIZE or length < 1:
                raise ValueError(f"유효하지 않은 길이: {length}")

            # Read 커맨드
            self.write_command(0x00)

            # Column & Row Address 한번에 처리
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)

            # Column Address (0x0000)
            GPIO.output(self.WE, GPIO.LOW)
            self.write_data(0x00)
            GPIO.output(self.WE, GPIO.HIGH)
            
            GPIO.output(self.WE, GPIO.LOW)
            self.write_data(0x00)
            GPIO.output(self.WE, GPIO.HIGH)

            # Row Address (3바이트)
            for i in range(3):
                GPIO.output(self.WE, GPIO.LOW)
                self.write_data((page_no >> (8 * i)) & 0xFF)
                GPIO.output(self.WE, GPIO.HIGH)
                
            GPIO.output(self.ALE, GPIO.LOW)

            # Read Confirm 커맨드
            self.write_command(0x30)
            
            # Ready 대기
            self.wait_ready()
            
            # 데이터 핀을 입력 모드로 변경
            self.set_data_pins_input()
            
            # 데이터 읽기
            data = []
            for _ in range(length):
                GPIO.output(self.RE, GPIO.LOW)
                byte = self.read_data()
                GPIO.output(self.RE, GPIO.HIGH)
                data.append(byte)
                
            return bytes(data)
            
        except Exception as e:
            self.reset_pins()
            raise RuntimeError(f"페이지 읽기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.set_data_pins_output()
            
    def erase_block(self, page_no: int):
        """블록 단위 erase"""
        try:
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            self.validate_block(block_no)
            
            # Block Erase 커맨드 (0x60)
            self.write_command(0x60)
    
            # Row Address (3바이트)
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            
            for i in range(3):
                GPIO.output(self.WE, GPIO.LOW)
                self.write_data((page_no >> (8 * i)) & 0xFF)
                GPIO.output(self.WE, GPIO.HIGH)
                
            GPIO.output(self.ALE, GPIO.LOW)
    
            # Confirm (0xD0)
            self.write_command(0xD0)
    
            # Ready 대기 및 상태 확인
            self.wait_ready()
            self.check_operation_status()
            
        except Exception as e:
            self.reset_pins()
            raise RuntimeError(f"블록 삭제 실패 (블록 {page_no // self.PAGES_PER_BLOCK}): {str(e)}") 