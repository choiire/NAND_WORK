# nand_bad_block_scanner.py

import os
import sys
import time
import RPi.GPIO as GPIO 
from datetime import datetime

# MT29F8G08ADADA 클래스 (nand_driver.py에서 가져옴)
class MT29F8G08ADADA:
    # NAND 플래시 상수
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096 
    
    # 타이밍 상수 (ns) - 데이터시트의 Max/Min 값과 충분한 여유를 고려하여 재조정
    tWB = 200     
    tR_ECC = 70000 
    tRR = 50      
    tWC = 50      
    tWP = 20      
    tWH = 20      
    tADL = 100    
    tREA = 30     
    tREH = 20     
    tWHR = 100    
    tCLS = 20     
    tCLH = 10     
    tALS = 20     
    tALH = 10     
    
    tDS = 20   
    tDH = 10

    def __init__(self):
        # GPIO 핀 설정 
        self.RB = 13  
        self.RE = 26  
        self.CE = 19  
        self.CLE = 11 
        self.ALE = 10 
        self.WE = 9   
        
        # 데이터 핀 (IO0-IO7)
        self.IO_pins = [21, 20, 16, 12, 25, 24, 23, 18] 
        
        # Bad Block 테이블 초기화
        self.bad_blocks = set()

        try:
            # GPIO 초기화
            GPIO.cleanup()  
            time.sleep(0.1)  
            
            GPIO.setmode(GPIO.BCM)  
            GPIO.setwarnings(False) 
            
            # 컨트롤 핀 출력으로 설정
            GPIO.setup(self.RB, GPIO.IN) 
            GPIO.setup(self.RE, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.setup(self.CE, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.setup(self.CLE, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.ALE, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.WE, GPIO.OUT, initial=GPIO.HIGH)
            
            # 데이터 핀 입출력 설정
            for pin in self.IO_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH) 
                
            # 초기 상태 설정
            time.sleep(0.001)  
            self.reset_pins()
            time.sleep(0.001)  
            
            # 파워온 시퀀스
            self.power_on_sequence()

            # 배드 블록 스캔 시에는 ECC를 비활성화하는 것이 좋습니다.
            self.disable_internal_ecc() 
            
        except Exception as e:
            GPIO.cleanup()
            raise RuntimeError(f"GPIO 초기화 실패: {str(e)}")

    def _delay_ns(self, nanoseconds: int):
        """나노초 단위의 정밀한 시간 지연을 수행합니다 (비지 웨이트)."""
        if nanoseconds <= 0:
            return
        end_time = time.perf_counter_ns() + nanoseconds
        while time.perf_counter_ns() < end_time:
            pass
            
    def reset_pins(self):
        """핀 상태를 안전한 기본값으로 리셋"""
        try:
            GPIO.output(self.CE, GPIO.HIGH)  # Chip Disable
            GPIO.output(self.RE, GPIO.HIGH)  # Read Disable
            GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
            GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
            GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
            
            # 데이터 핀을 출력 모드로 설정하고 HIGH로 설정
            for pin in self.IO_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH)
                
            self._delay_ns(200)  # 200ns 대기
        except Exception as e:
            raise RuntimeError(f"핀 리셋 실패: {str(e)}")
            
    def __del__(self):
        """객체가 소멸될 때 GPIO 리소스 정리"""
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

    def check_operation_status(self) -> bool:
        """작업 상태 확인 및 FAIL 비트 반환. FAIL 비트가 1이면 False (실패) 반환."""
        try:
            # 상태 읽기 명령 (70h) [cite: 1645]
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.HIGH)
            GPIO.output(self.ALE, GPIO.LOW)
            self._delay_ns(self.tCLS)  
            
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(0x70)  # Read Status command [cite: 1655]
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
            
            GPIO.output(self.CLE, GPIO.LOW)
            self._delay_ns(self.tCLH)  
            self._delay_ns(self.tWHR)  
            
            # 상태 바이트 읽기
            self.set_data_pins_input()
            GPIO.output(self.RE, GPIO.LOW)
            self._delay_ns(self.tREA)  
            status = self.read_data()
            GPIO.output(self.RE, GPIO.HIGH)
            self._delay_ns(self.tREH)  
            
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output() 
            
            # FAIL 비트 (SR Bit 0) 확인 [cite: 1645]
            if status & 0x01:  
                return False # Fail bit가 1이면 실패
            return True # Fail bit가 0이면 성공
            
        except Exception as e:
            print(f"상태 확인 중 오류: {str(e)}")
            return False

    def power_on_sequence(self):
        """파워온 시퀀스 수행 [cite: 1192]"""
        try:
            # 1. VCC 안정화 대기 [cite: 1194]
            time.sleep(0.001)  # 1ms 대기
            
            # 2. 모든 컨트롤 신호를 HIGH로 설정 (안전한 초기 상태)
            GPIO.output(self.CE, GPIO.HIGH)
            GPIO.output(self.RE, GPIO.HIGH)
            GPIO.output(self.WE, GPIO.HIGH)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            # 3. 추가 대기 (R/B#가 유효해질 때까지)
            time.sleep(0.0002)  # 200us (데이터시트 기준 VCC(MIN) 도달 후 10us 대기 [cite: 1196] )
            
            # 4. RESET 커맨드 전송 (FFh) [cite: 1201]
            for _ in range(3):  # 최대 3번 시도
                try:
                    self.write_command(0xFF) # RESET (FFh) [cite: 1267]
                    
                    # R/B# 신호가 LOW로 변경되는지 확인 (tWB 대기) [cite: 1275]
                    timeout_start = time.time()
                    while GPIO.input(self.RB) == GPIO.HIGH:
                        if time.time() - timeout_start > 0.001:  # 1ms 타임아웃
                            break
                        time.sleep(0.0001)  # 100us 대기
                    
                    # Ready 대기 (t_RST, 최대 1ms) [cite: 1277]
                    self.wait_ready()
                    return  # 성공하면 종료
                except Exception as e:
                    time.sleep(0.001)  # 1ms 대기 후 재시도
                    continue
                    
            raise RuntimeError("RESET 커맨드 실패")
            
        except Exception as e:
            raise RuntimeError(f"파워온 시퀀스 실패: {str(e)}")
            
    def wait_ready(self, max_operation_time_us: int = 2000): # 기본값 2ms
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기."""
        # tWB 대기 (WE# HIGH에서 R/B# LOW까지의 시간)
        self._delay_ns(self.tWB)  

        # R/B# 신호가 HIGH가 될 때까지 대기
        # max_operation_time_us는 해당 작업의 최대 완료 시간 (예: tPROG, tBERS)
        max_wait_time_s = max_operation_time_us / 1_000_000 # us to s

        timeout_start = time.time()
        while GPIO.input(self.RB) == GPIO.LOW:
            if time.time() - timeout_start > max_wait_time_s:
                raise RuntimeError(f"R/B# 시그널 타임아웃 (Busy 상태 지속, {max_operation_time_us} us 초과)")
            time.sleep(0.00001) # 10us 마이크로초 단위로 짧게 대기

        # Ready 상태가 된 후 추가 안정화 대기 (tRR)
        self._delay_ns(self.tRR)
            
    def set_data_pins_output(self):
        """데이터 핀을 출력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
        self._delay_ns(200)  
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
        self._delay_ns(200)  
            
    def write_data(self, data: int):
        """8비트 데이터 쓰기 (타이밍 제어 강화)"""
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
        self._delay_ns(self.tDS) 

    def read_data(self) -> int:
        """8비트 데이터 읽기"""
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
        return data
        
    def write_command(self, cmd: int):
        """커맨드 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)
        self._delay_ns(50)  
        
        GPIO.output(self.CLE, GPIO.HIGH)
        self._delay_ns(self.tCLS)  
        GPIO.output(self.ALE, GPIO.LOW)
        
        GPIO.output(self.WE, GPIO.LOW)
        self._delay_ns(self.tWP)  
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)
        self._delay_ns(self.tWH)  
        
        GPIO.output(self.CLE, GPIO.LOW)
        self._delay_ns(self.tCLH)  

    def write_address(self, addr: int):
        """주소 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   
        self._delay_ns(50)  
        
        GPIO.output(self.CLE, GPIO.LOW)  
        GPIO.output(self.ALE, GPIO.HIGH) 
        self._delay_ns(self.tALS)  
        
        GPIO.output(self.WE, GPIO.LOW)   
        self._delay_ns(self.tWP)  
        self.write_data(addr)
        GPIO.output(self.WE, GPIO.HIGH)  
        self._delay_ns(self.tWH)  
        
        GPIO.output(self.ALE, GPIO.LOW)  
        self._delay_ns(self.tALH)  
        self._delay_ns(self.tADL)  
    
    def enable_internal_ecc(self):
        """내장 ECC 엔진 활성화 [cite: 1518, 1519]"""
        try:
            print("내부 ECC 엔진 활성화 시도...")
            self.write_command(0xEF) # SET FEATURES (EFh) command [cite: 1533]
            self.write_address(0x90) # Feature Address (90h for Array operation mode) [cite: 1530]
            
            params = [0x08, 0x00, 0x00, 0x00] # P1=0x08 for ECC Enable [cite: 1519]
            self.set_data_pins_output() 
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)

            for p in params:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP)
                self.write_data(p)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH)
            
            self.wait_ready(max_operation_time_us=1) # tFEAT [cite: 1541]
            time.sleep(0.001)
            
            print("ECC 활성화 상태를 검증합니다...")
            self.write_command(0xEE) # GET FEATURES (EEh) command [cite: 1567]
            self.write_address(0x90) # Feature Address (90h) [cite: 1573]
            self._delay_ns(2000)  
            
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            params_read = []
            for _ in range(4):
                GPIO.output(self.RE, GPIO.LOW)
                self._delay_ns(self.tREA)
                byte_data = self.read_data()
                GPIO.output(self.RE, GPIO.HIGH)
                self._delay_ns(self.tREH)
                params_read.append(byte_data)
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output() # 데이터 핀 다시 출력으로 설정
            
            p1_value = params_read[0]
            if (p1_value >> 3) & 0x01: # P1의 3번 비트가 ECC 활성화 여부를 나타냄 (데이터시트 Table 14 참조)
                print("✓ 내부 ECC 엔진이 성공적으로 활성화되었습니다.")
                return True
            else:
                print("✗ 내부 ECC 엔진 활성화에 실패했습니다.")
                return False
        except Exception as e:
            print(f"✗ 내부 ECC 활성화 중 오류 발생: {str(e)}")
            return False
        finally:
            self.reset_pins()
    
    def disable_internal_ecc(self):
        """내장 ECC 엔진 비활성화 [cite: 1520]"""
        try:
            print("내부 ECC 엔진 비활성화 시도...")
            self.write_command(0xEF) # SET FEATURES (EFh) command [cite: 1533]
            self.write_address(0x90) # Feature Address (90h) [cite: 1530]
            
            params = [0x00, 0x00, 0x00, 0x00] # P1=0x00 for ECC Disable [cite: 1520, 1531]
            self.set_data_pins_output() 
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            for p in params:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP)
                self.write_data(p)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH)
            
            self.wait_ready(max_operation_time_us=1) # tFEAT [cite: 1541]
            time.sleep(0.001)  
            
            print("ECC 비활성화 상태를 검증합니다...")
            self.write_command(0xEE) # GET FEATURES (EEh) command [cite: 1567]
            self.write_address(0x90) # Feature Address (90h) [cite: 1573]
            self._delay_ns(2000)  
            
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            params_read = []
            for _ in range(4):
                GPIO.output(self.RE, GPIO.LOW)
                self._delay_ns(self.tREA)
                byte_data = self.read_data()
                GPIO.output(self.RE, GPIO.HIGH)
                self._delay_ns(self.tREH)
                params_read.append(byte_data)
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output() # 데이터 핀 다시 출력으로 설정
            
            p1_value = params_read[0]
            if not ((p1_value >> 3) & 0x01): # P1의 3번 비트가 ECC 활성화 여부를 나타냄 (데이터시트 Table 14 참조)
                print("✓ 내부 ECC 엔진이 성공적으로 비활성화되었습니다.")
                return True
            else:
                print("✗ 내부 ECC 엔진 비활성화에 실패했습니다.")
                return False

        except Exception as e:
            print(f"✗ 내부 ECC 비활성화 중 오류 발생: {str(e)}")
            return False
        finally:
            self.reset_pins()

    def _write_full_address(self, page_no: int, col_addr: int = 0):
        """
        데이터시트(Table 2) 사양에 맞게 5바이트 전체 주소(컬럼+로우)를 조합하여 전송합니다.
        개선된 타이밍 적용.
        """
        # 주소 계산 (MT29F8G08ADADA 기준)
        page_in_block = page_no % self.PAGES_PER_BLOCK  # PA[5:0] (0-63) [cite: 678]
        block_no = page_no // self.PAGES_PER_BLOCK      # BA[11:0] (0-4095 for 4Gb) [cite: 678]

        # 데이터시트의 5-Cycle Address 규격에 맞춰 5바이트 주소 생성 (x8 모드) [cite: 678]
        # Cycle 1: Column Address Lower Byte (CA[7:0])
        addr_byte1 = col_addr & 0xFF
        
        # Cycle 2: Column Address Upper Byte (CA[11:8])
        # 페이지 크기가 2112(2048+64)이므로 컬럼 주소는 12비트(0-2111)가 필요합니다.
        addr_byte2 = (col_addr >> 8) & 0x0F
        
        # Cycle 3: {BA[7], BA[6], PA[5], PA[4], PA[3], PA[2], PA[1], PA[0]} [cite: 678]
        # BA[6]는 Plane Selection 비트 [cite: 684]
        addr_byte3 = ((block_no >> 6) & 0x03) | (page_in_block & 0x3F) # BA[7:6]과 PA[5:0] 조합
        
        # Cycle 4: {BA[15], BA[14], BA[13], BA[12], BA[11], BA[10], BA[9], BA[8]} [cite: 678]
        addr_byte4 = (block_no >> 8) & 0xFF
        
        # Cycle 5: {LOW, ..., LOW, BA[17], BA[16]} (4Gb 칩은 BA[17:16]을 사용하지 않으므로 이 바이트는 0) [cite: 678]
        addr_byte5 = (block_no >> 16) & 0x03 # BA[17:16]

        addresses = [addr_byte1, addr_byte2, addr_byte3, addr_byte4, addr_byte5]

        # 생성된 5바이트 주소 전송
        GPIO.output(self.CE, GPIO.LOW)
        self._delay_ns(50)  
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(self.tALS) 

        for addr_byte in addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP) 
            self.write_data(addr_byte)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH) 
            
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(self.tALH) 
        self._delay_ns(self.tADL) 
    
    def _write_row_address(self, page_no: int):
        """
        데이터시트(Table 2) 사양에 맞게 3바이트 Row Address를 조합하여 전송합니다.
        Erase 동작에서는 PA(페이지 주소) 비트들이 무시됩니다. [cite: 2497]
        """
        # 페이지 번호로부터 페이지 주소(PA)와 블록 주소(BA) 계산
        page_in_block = page_no % self.PAGES_PER_BLOCK  
        block_no = page_no // self.PAGES_PER_BLOCK      

        # 데이터시트의 Third, Fourth, Fifth address cycle에 맞춰 3바이트 주소 생성 [cite: 678]
        # Cycle 3: {BA[7], BA[6], PA[5], PA[4], PA[3], PA[2], PA[1], PA[0]}
        addr_byte3 = ((block_no >> 6) & 0x03) | (page_in_block & 0x3F)

        # Cycle 4: {BA[15], BA[14], BA[13], BA[12], BA[11], BA[10], BA[9], BA[8]}
        addr_byte4 = (block_no >> 8) & 0xFF

        # Cycle 5: {LOW, LOW, LOW, LOW, LOW, LOW, BA[17], BA[16]}
        addr_byte5 = (block_no >> 16) & 0xFF

        row_addresses = [addr_byte3, addr_byte4, addr_byte5]

        # 생성된 주소 전송
        GPIO.output(self.CE, GPIO.LOW)
        self._delay_ns(50)  
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(self.tALS) 

        for addr_byte in row_addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP) 
            self.write_data(addr_byte)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH) 
            
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(self.tALH) 
        self._delay_ns(self.tADL) 

    def write_full_page(self, page_no: int, data: bytes) -> bool:
        """
        한 페이지 전체(메인+스페어, 2112 바이트)를 씁니다.
        데이터가 2112 바이트보다 작으면 나머지는 0xFF로 채웁니다.
        """
        full_page_size = self.PAGE_SIZE + self.SPARE_SIZE # 2112 bytes
        if len(data) > full_page_size:
            raise ValueError(f"데이터 크기가 전체 페이지 크기({full_page_size} bytes)를 초과합니다.")
        
        # 데이터가 전체 페이지 크기보다 작을 경우 0xFF로 패딩
        if len(data) < full_page_size:
            data += b'\xFF' * (full_page_size - len(data))

        try:
            self.validate_page(page_no)
            
            # [1] 쓰기 시작 명령 (80h) [cite: 2271]
            self.write_command(0x80)
            
            # [2] 주소 전송 (5 사이클)
            self._write_full_address(page_no, col_addr=0)
            
            # [3] 데이터 전송
            self.set_data_pins_output()
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            for byte_idx, byte in enumerate(data):
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP) 
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH) 
                self._delay_ns(50) # 각 바이트 쓰기 후 짧은 대기

            # [4] 쓰기 확정 명령 (10h) [cite: 2261]
            self.write_command(0x10)
            
            # [5] tPROG_ECC 대기 (내부 ECC 비활성화 시 tPROG) [cite: 2271, 3529]
            self.wait_ready(max_operation_time_us=600) # tPROG/tPROG_ECC Max 600us 
            
            # [6] 상태 확인
            if not self.check_operation_status():
                return False # 쓰기 실패
            return True # 쓰기 성공
                
        except Exception as e:
            print(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
            return False
        finally:
            self.reset_pins()

    def read_page(self, page_no: int, length: int = 2048) -> bytes:
        """
        한 페이지를 읽습니다. (내장 하드웨어 ECC가 비활성화된 상태에서)
        스페어 영역을 포함하여 읽을 수 있습니다.
        """
        try:
            self.validate_page(page_no)
            
            # [1] 읽기 명령 및 주소 전송 (00h) [cite: 1955]
            self.write_command(0x00)
            self._write_full_address(page_no, col_addr=0)
            
            # [2] 읽기 확정 명령 (30h) [cite: 1957]
            self.write_command(0x30)
            
            # [3] 데이터가 캐시로 로드될 때까지 대기 (tR) [cite: 1958]
            self.wait_ready(max_operation_time_us=25) # tR Max 25us (ECC disabled) 
            
            # [4] 데이터 읽기
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            self._delay_ns(50)  # CE# setup time
            
            read_bytes = []
            for i in range(length):
                GPIO.output(self.RE, GPIO.LOW)
                self._delay_ns(self.tREA)  # RE# access time 대기 [cite: 3515, 3520]
                
                byte_data = self.read_data()
                
                GPIO.output(self.RE, GPIO.HIGH)
                self._delay_ns(self.tREH)  # RE# high hold time [cite: 3515, 3520]
                
                read_bytes.append(byte_data)
                
                # tRC (Read Cycle Time) 준수 [cite: 3515, 3520]
                # 이미 tRR(Ready to RE# LOW)에 포함된 개념이므로 추가 지연은 필요 없을 수 있습니다.
                # 그러나 RE# HIGH 구간에서 다음 RE# LOW까지의 최소 시간이 필요할 수 있습니다.
                # 여기서는 tRR에 맞춰 충분한 지연을 주고 있습니다.
            
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output()
                
            return bytes(read_bytes)
            
        except Exception as e:
            print(f"페이지 읽기 실패 (페이지 {page_no}): {str(e)}")
            return b'' # 실패 시 빈 바이트열 반환
        finally:
            self.reset_pins()
    
    def erase_block(self, page_no: int) -> bool:
        """
        한 개의 블록을 지웁니다. [cite: 2494]
        내부적으로 wait_ready()를 사용하여 작업 완료를 기다립니다.
        """
        try:
            # 1. 페이지 및 블록 번호 유효성 검사
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            self.validate_block(block_no)
            
            # --- Block Erase 시퀀스 시작 (60h-Addr-D0h) [cite: 2494] ---
            
            # [1] 지우기 시작 명령 (60h) [cite: 2497]
            self.write_command(0x60)

            # [2] Row Address 전송 (3 사이클) [cite: 2497]
            self._write_row_address(page_no)

            # [3] 지우기 확정 명령 (D0h) [cite: 2498]
            self.write_command(0xD0)
            
            # [4] 작업이 완료될 때까지 대기 (tBERS) [cite: 2499, 3529]
            self.wait_ready(max_operation_time_us=3000) # tBERS Max 3ms = 3000us 
            
            # [5] 작업 상태 확인 [cite: 2500]
            if not self.check_operation_status():
                return False # 지우기 실패
            return True # 지우기 성공
                
        except Exception as e:
            print(f"블록 지우기 실패 (블록 {block_no}): {str(e)}")
            return False
        
        finally:
            self.reset_pins()

    def check_ecc_status(self):
        """GET FEATURES(EEh) 명령을 사용해 칩의 현재 ECC 설정 상태를 읽고 출력합니다. [cite: 1567]"""
        print(".-" * 20)
        print("칩의 현재 ECC 상태를 확인합니다...")
        try:
            self.write_command(0xEE) # GET FEATURES (EEh) command [cite: 1567]
            self.write_address(0x90) # Feature Address (90h for Array operation mode) [cite: 1573]

            self._delay_ns(2000)  # 2us 대기 

            # 결과 파라미터 읽기
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            
            params = []
            for _ in range(4):
                GPIO.output(self.RE, GPIO.LOW)
                self._delay_ns(self.tREA)
                byte_data = self.read_data()
                GPIO.output(self.RE, GPIO.HIGH)
                self._delay_ns(self.tREH)
                params.append(byte_data)
            
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output()
            
            p1 = params[0]
            # 데이터시트에 따르면 P1의 3번 비트가 ECC 활성화 여부를 나타냄 (Table 14) [cite: 1530]
            if (p1 >> 3) & 0x01:
                print(">>> 내장 ECC 상태: 활성화됨 (Enabled)")
            else:
                print(">>> 내장 ECC 상태: 비활성화됨 (Disabled)")
            print("-" * 20)

        except Exception as e:
            print(f"ECC 상태 확인 중 오류 발생: {e}")
        finally:
            self.reset_pins()

    def scan_bad_blocks(self):
        """
        NAND 플래시를 스캔하여 쓰기 및 지우기 테스트를 통해 배드 블록을 식별합니다.
        성공/실패 여부는 칩의 상태 레지스터를 통해 확인하며, 이 정보는 칩에 기록되지 않습니다.
        """
        print("Bad Block 스캔 시작 (쓰기/지우기 테스트 기준)...")
        self.bad_blocks = set() # 기존 Bad Block 목록 초기화
        
        # 테스트에 사용할 데이터 패턴 (전체 FF인 상태에서 쉽게 구별하기 위함)
        TEST_PATTERN_WRITE = b'\x55' * (self.PAGE_SIZE + self.SPARE_SIZE)
        TEST_PATTERN_READ = b'\xFF' * (self.PAGE_SIZE + self.SPARE_SIZE) # 읽기 검증용 (지운 후)

        try:
            for block in range(self.TOTAL_BLOCKS):
                first_page_of_block = block * self.PAGES_PER_BLOCK
                is_current_block_bad = False
                
                # 진행률 표시
                sys.stdout.write(f"\rBad Block 스캔 진행 중: {block}/{self.TOTAL_BLOCKS} 블록 테스트 중...")
                sys.stdout.flush()

                # 1. 쓰기 테스트 (첫 페이지에 특정 패턴 쓰기)
                try:
                    # ECC가 비활성화된 상태에서 진행
                    if not self.write_full_page(first_page_of_block, TEST_PATTERN_WRITE):
                        raise RuntimeError("쓰기 작업 실패")
                    
                    # 쓰기 후 읽어서 검증 (선택 사항이지만 정확도를 높임)
                    read_data_after_write = self.read_page(first_page_of_block, len(TEST_PATTERN_WRITE))
                    if read_data_after_write != TEST_PATTERN_WRITE:
                        raise RuntimeError("쓰기 후 읽기 검증 실패 (데이터 불일치)")
                        
                except Exception as e:
                    print(f"\nBad Block 발견: 블록 {block} (쓰기 테스트 실패 - {e})")
                    is_current_block_bad = True
                    self.mark_bad_block(block)
                    self.reset_pins() # 실패 시 칩 상태 정리

                # 2. 지우기 테스트 (쓰기 테스트 통과한 블록만)
                if not is_current_block_bad:
                    try:
                        if not self.erase_block(first_page_of_block):
                            raise RuntimeError("지우기 작업 실패")
                        
                        # 지우기 후 읽어서 검증 (모두 FFh인지 확인)
                        read_data_after_erase = self.read_page(first_page_of_block, len(TEST_PATTERN_READ))
                        if read_data_after_erase != TEST_PATTERN_READ:
                            raise RuntimeError("지우기 후 읽기 검증 실패 (데이터 불일치, FFh가 아님)")

                    except Exception as e:
                        print(f"\nBad Block 발견: 블록 {block} (지우기 테스트 실패 - {e})")
                        is_current_block_bad = True
                        self.mark_bad_block(block)
                        self.reset_pins() # 실패 시 칩 상태 정리
                
                self.reset_pins() # 매 블록 테스트 후 핀 상태 정리 (중요)

            sys.stdout.write("\n") # 최종 진행률 출력 후 줄바꿈
            print(f"Bad Block 스캔 완료. 총 {len(self.bad_blocks)}개의 Bad Block 발견.")
            if self.bad_blocks:
                print("Bad Block 목록:", sorted(list(self.bad_blocks)))
                print("이 정보는 프로그램 내에서만 관리되며, 칩에는 기록되지 않았습니다.")
            else:
                print("모든 블록이 Good Block입니다! (쓰기/지우기 테스트 기준)")
                
        except Exception as e:
            print(f"Bad Block 스캔 중 심각한 오류 발생: {str(e)}")


# --- Bad Block 스캐너 메인 함수 ---
def main():
    nand = None
    try:
        print("NAND 플래시 드라이버 초기화 중...")
        nand = MT29F8G08ADADA()
        
        print("\n내부 ECC 엔진 설정을 확인합니다...")
        ecc_disabled = nand.disable_internal_ecc()
        if not ecc_disabled:
            print("경고: ECC 비활성화에 실패했습니다. 스캔 결과의 정확도에 영향을 줄 수 있습니다.")
        # ECC 비활성화 상태 재확인 (선택 사항)
        nand.check_ecc_status()

        print("\n--- Bad Block 스캔 시작 ---")
        start_time = datetime.now()
        
        nand.scan_bad_blocks() # 배드 블록 스캔 실행

        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n--- Bad Block 스캔 완료 ---")
        print(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"완료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 소요 시간: {duration}")

        if nand.bad_blocks:
            print("\n!!! 다음 블록들은 Bad Block으로 식별되었습니다 (칩에 마킹되지 않음):")
            for block_num in sorted(list(nand.bad_blocks)):
                print(f"    - 블록 {block_num}")
            print("\n이 정보는 프로그램 내에서만 관리되며, 칩에는 기록되지 않았습니다.")
            sys.exit(1) # Bad Block이 발견되면 종료 코드 1
        else:
            print("\n모든 블록이 Good Block입니다! (쓰기/지우기 테스트 기준)")
            sys.exit(0) # Bad Block이 없으면 종료 코드 0

    except Exception as e:
        print(f"\n치명적인 오류 발생: {str(e)}")
        sys.exit(1)
    finally:
        if nand:
            print("\nGPIO 리소스를 정리합니다.")
            del nand # __del__ 메서드 호출을 통해 GPIO 정리


if __name__ == "__main__":
    main()