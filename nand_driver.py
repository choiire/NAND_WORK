import RPi.GPIO as GPIO
import time

class MT29F4G08ABADAWP:
    # NAND 플래시 상수
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096
    
    # 타이밍 상수 (ns)
    tWB = 100   # WE# high to R/B# low
    tR = 25000  # Data Transfer from Cell to Register
    tRR = 20    # RE# low to RE# high
    tWC = 25    # Write Cycle Time
    tWP = 10    # WE# pulse width
    tWH = 10    # WE# high hold time
    tADL = 70   # ALE to data loading time
    tREA = 20   # RE# access time
    tREH = 10   # RE# high hold time
    tWHR = 60   # WE# high to RE# low
    
    def __init__(self, skip_bad_block_scan=False):
        # GPIO 핀 설정
        self.RB = 13  # Ready/Busy
        self.RE = 26  # Read Enable
        self.CE = 19  # Chip Enable
        self.CLE = 11 # Command Latch Enable  
        self.ALE = 10 # Address Latch Enable
        self.WE = 9   # Write Enable
        
        # 데이터 핀
        self.IO_pins = [21, 20, 16, 12, 25, 24, 23, 18] # IO0-IO7
        
        # Bad Block 테이블 초기화
        self.bad_blocks = set()

        try:
            # GPIO 초기화
            GPIO.cleanup()  # 이전 설정 초기화
            time.sleep(0.1)  # 초기화 후 잠시 대기
            
            GPIO.setmode(GPIO.BCM)  # BCM 모드로 명시적 설정
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
            time.sleep(0.001)  # 1ms 대기
            self.reset_pins()
            time.sleep(0.001)  # 1ms 대기
            
            # 파워온 시퀀스
            self.power_on_sequence()

            # 내부 ECC 엔진 활성화
            self.enable_internal_ecc()
            
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
                
            self._delay_ns(100)  # 100ns 대기
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
        """작업 상태 확인 (핀 방향 전환 로직 추가)"""
        try:
            self.write_command(0x70)  # Read Status

            # 데이터를 읽기 전에 핀 방향을 '입력'으로 설정
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            
            # RE#를 토글하여 데이터 읽기
            GPIO.output(self.RE, GPIO.LOW)
            self._delay_ns(self.tREA)  # RE# access time
            status = self.read_data()
            GPIO.output(self.RE, GPIO.HIGH)
            
            GPIO.output(self.CE, GPIO.HIGH)
            
            if status & 0x01:  # Bit 0 (FAIL)
                raise RuntimeError(f"작업 실패 (상태 레지스터: 0x{status:02X})")
                
            # 데이터시트에 따라, 상태 확인 후에는 READ MODE(00h)로 전환하여
            # 데이터 출력을 활성화해야 할 수 있습니다.
            self.write_command(0x00)
                
            return True

        finally:
            # 작업 후에는 항상 핀을 '출력' 모드로 복원
            self.set_data_pins_output()
            self.reset_pins()

    def power_on_sequence(self):
        """파워온 시퀀스 수행"""
        try:
            # 1. VCC 안정화 대기
            time.sleep(0.001)  # 1ms 대기
            
            # 2. 모든 컨트롤 신호를 HIGH로 설정
            GPIO.output(self.CE, GPIO.HIGH)
            GPIO.output(self.RE, GPIO.HIGH)
            GPIO.output(self.WE, GPIO.HIGH)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            # 3. 추가 대기
            time.sleep(0.0002)  # 200us
            
            # 4. RESET 커맨드 전송 (여러 번 시도)
            for _ in range(3):  # 최대 3번 시도
                try:
                    self.write_command(0xFF)
                    
                    # R/B# 신호가 LOW로 변경되는지 확인
                    timeout_start = time.time()
                    while GPIO.input(self.RB) == GPIO.HIGH:
                        if time.time() - timeout_start > 0.001:  # 1ms 타임아웃
                            break
                        time.sleep(0.0001)  # 100us 대기
                    
                    # Ready 대기
                    self.wait_ready()
                    return  # 성공하면 종료
                except Exception as e:
                    time.sleep(0.001)  # 1ms 대기 후 재시도
                    continue
                    
            raise RuntimeError("RESET 커맨드 실패")
            
        except Exception as e:
            raise RuntimeError(f"파워온 시퀀스 실패: {str(e)}")
            
    def wait_ready(self):
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기"""
        # tWB 대기
        self._delay_ns(self.tWB)  # 100ns
        
        # R/B# 신호가 HIGH가 될 때까지 대기
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            timeout_start = time.time()
            while GPIO.input(self.RB) == GPIO.LOW:
                if time.time() - timeout_start > 0.01:  # 10ms 타임아웃
                    break
                time.sleep(0.0001)  # 100us 간격으로 체크
                
            if GPIO.input(self.RB) == GPIO.HIGH:
                return  # Ready 상태 확인
                
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(0.001)  # 1ms 대기 후 재시도
                
        raise RuntimeError("R/B# 시그널 타임아웃")
            
    def set_data_pins_output(self):
        """데이터 핀을 출력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
        self._delay_ns(100)  # 100ns 대기
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
        self._delay_ns(100)  # 100ns 대기
            
    def write_data(self, data):
        """8비트 데이터 쓰기 (타이밍 제어 추가)"""
        # WE# 사이클 타임 준수
        cycle_start = time.perf_counter_ns()
        
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
            
        # tWC 타이밍 준수
        elapsed = time.perf_counter_ns() - cycle_start
        if elapsed < self.tWC:
            self._delay_ns(self.tWC - elapsed)

    def read_data(self):
        """8비트 데이터 읽기 (타이밍 제어 추가)"""
        # RE# 사이클 타임 준수
        cycle_start = time.perf_counter_ns()
        
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
            
        # tRR 타이밍 준수
        elapsed = time.perf_counter_ns() - cycle_start
        if elapsed < self.tRR:
            self._delay_ns(self.tRR - elapsed)
            
        return data
        
    def write_command(self, cmd):
        """커맨드 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.HIGH)
        GPIO.output(self.ALE, GPIO.LOW)
        
        GPIO.output(self.WE, GPIO.LOW)
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)
        
        GPIO.output(self.CLE, GPIO.LOW)

    def write_address(self, addr):
        """주소 쓰기"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        self._delay_ns(100)  # 100ns 대기
        
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        GPIO.output(self.ALE, GPIO.HIGH) # Address Latch Enable
        self._delay_ns(100)  # 100ns 대기
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self.write_data(addr)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        self._delay_ns(self.tWH)  # WE# high hold time
        
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        self._delay_ns(100)  # 100ns 대기

    def enable_internal_ecc(self):
        """데이터시트 사양에 따라 칩의 내장 ECC 엔진을 활성화합니다."""
        try:
            print("내부 ECC 엔진 활성화 시도...")
            # SET FEATURES (EFh) 명령
            self.write_command(0xEF)

            # Feature Address (90h) 전송
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            self._delay_ns(10) # tALS

            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(12) # tWP
            self.write_data(0x90) # Feature Address
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(10) # tWH
            
            GPIO.output(self.ALE, GPIO.LOW)
            self._delay_ns(70) # tADL (Address to Data Latch Delay)

            # Parameters (P1=08h for ECC Enable, P2-P4=00h) 전송
            params = [0x08, 0x00, 0x00, 0x00]
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)

            for p in params:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(12) # tWP
                self.write_data(p)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(10) # tWH
            
            self.wait_ready() # tFEAT (Feature operation time) 대기
            print("내부 ECC 엔진이 성공적으로 활성화되었습니다.")

        except Exception as e:
            raise RuntimeError(f"내부 ECC 활성화 실패: {str(e)}")
        finally:
            self.reset_pins()

    def is_bad_block(self, block_no):
        """해당 블록이 Bad Block인지 확인"""
        return block_no in self.bad_blocks

    def mark_bad_block(self, block_no):
        """블록을 Bad Block으로 표시"""
        self.bad_blocks.add(block_no)
        
    def scan_bad_blocks(self):
        """
        전체 NAND를 스캔하여 데이터시트 사양에 맞는 Bad Block 테이블을 구성합니다.
        공장 출하 시 Bad Block은 첫 페이지의 스페어 영역 첫 바이트(2048)에 0x00으로 표시됩니다.
        """
        print("Bad Block 스캔 시작 (데이터시트 기준)...")
        self.bad_blocks = set()
        
        # 스페어 영역의 첫 바이트 주소
        BAD_BLOCK_MARKER_ADDR = 2048

        try:
            for block in range(self.TOTAL_BLOCKS):
                if block % 100 == 0:
                    print(f"Bad Block 스캔 진행 중: {block}/{self.TOTAL_BLOCKS} 블록 완료")

                first_page_of_block = block * self.PAGES_PER_BLOCK
                
                try:
                    # [1] 읽기 명령 (00h)
                    self.write_command(0x00)
                    
                    # [2] 주소 전송 (스페어 영역의 첫 바이트)
                    self._write_full_address(first_page_of_block, col_addr=BAD_BLOCK_MARKER_ADDR)
                    
                    # [3] 읽기 확정 (30h)
                    self.write_command(0x30)
                    
                    # [4] 데이터 전송 대기
                    self.wait_ready()
                    
                    # [5] 1바이트 읽기
                    self.set_data_pins_input()
                    GPIO.output(self.CE, GPIO.LOW)
                    
                    GPIO.output(self.RE, GPIO.LOW)
                    self._delay_ns(22) # tREA (22ns)
                    marker_byte = self.read_data()
                    GPIO.output(self.RE, GPIO.HIGH)
                    
                    GPIO.output(self.CE, GPIO.HIGH)
                    self.set_data_pins_output()

                    # [6] Bad Block 마크(0x00) 확인
                    if marker_byte == 0x00:
                        self.bad_blocks.add(block)
                        print(f"Bad Block 발견: 블록 {block}")

                except Exception as e:
                    print(f"블록 {block} 스캔 중 오류 발생, Bad Block으로 처리합니다: {str(e)}")
                    self.bad_blocks.add(block)
                finally:
                    self.reset_pins() # 각 블록 스캔 후 핀 상태 리셋

            print(f"Bad Block 스캔 완료. 총 {len(self.bad_blocks)}개의 Bad Block 발견.")
            if self.bad_blocks:
                print("Bad Block 목록:", sorted(list(self.bad_blocks)))
                
        except Exception as e:
            print(f"Bad Block 스캔 중 심각한 오류 발생: {str(e)}")

    def find_good_block(self, start_block):
        """주어진 블록부터 시작하여 사용 가능한 블록 찾기"""
        current_block = start_block
        while current_block < self.TOTAL_BLOCKS:
            if not self.is_bad_block(current_block):
                return current_block
            current_block += 1
        raise RuntimeError("사용 가능한 블록이 없습니다")

    def write_page(self, page_no: int, data: bytes):
        """한 페이지 쓰기 (내장 하드웨어 ECC 사용)"""
        # 데이터 크기 유효성 검사 (페이지 크기만 확인)
        if len(data) > self.PAGE_SIZE:
            raise ValueError(f"데이터 크기가 페이지 크기({self.PAGE_SIZE} bytes)를 초과합니다.")
        
        # 페이지 크기에 맞게 데이터 패딩
        if len(data) < self.PAGE_SIZE:
            data += b'\xFF' * (self.PAGE_SIZE - len(data))

        try:
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            if self.is_bad_block(block_no):
                raise RuntimeError(f"Bad Block({block_no})에 쓰기 시도")
            
            # [1] 쓰기 시작 명령 (80h)
            self.write_command(0x80)
            
            # [2] 주소 전송 (5 사이클)
            self._write_full_address(page_no, col_addr=0)
            
            # [3] 데이터 전송 (인코딩 없이 원본 데이터 전송)
            self.set_data_pins_output()
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            for byte in data:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(12) # tWP
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(10) # tWH
                
            # [4] 쓰기 확정 명령 (10h)
            self.write_command(0x10)
            
            # [5] tPROG_ECC 대기
            self.wait_ready()
            
            # [6] 상태 확인
            if not self.check_operation_status():
                self.mark_bad_block(block_no)
                raise RuntimeError("페이지 쓰기 실패 (상태 확인)")
                
        except Exception as e:
            raise RuntimeError(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.reset_pins()

    def _write_full_address(self, page_no: int, col_addr: int = 0):
        """
        데이터시트(Table 2) 사양에 맞게 5바이트 전체 주소(컬럼+로우)를 조합하여 전송합니다.
        """
        # 주소 계산
        page_in_block = page_no % self.PAGES_PER_BLOCK  # PA[5:0] (0-63)
        block_no = page_no // self.PAGES_PER_BLOCK      # BA[11:0] (0-4095 for 4Gb)

        # 데이터시트의 5-Cycle Address 규격에 맞춰 5바이트 주소 생성
        # Cycle 1: Column Address Lower Byte (CA[7:0])
        addr_byte1 = col_addr & 0xFF
        
        # Cycle 2: Column Address Upper Byte (CA[11:8])
        # 페이지 크기가 2112(2048+64)이므로 컬럼 주소는 12비트(0-2111)가 필요합니다.
        addr_byte2 = (col_addr >> 8) & 0x0F
        
        # Cycle 3: {BA[7], BA[6], PA[5], PA[4], PA[3], PA[2], PA[1], PA[0]}
        addr_byte3 = (block_no & 0xC0) | page_in_block
        
        # Cycle 4: {BA[15], BA[14], BA[13], BA[12], BA[11], BA[10], BA[9], BA[8]}
        addr_byte4 = (block_no >> 8) & 0xFF
        
        # Cycle 5: {LOW, ..., LOW, BA[17], BA[16]}
        addr_byte5 = (block_no >> 16) & 0xFF

        addresses = [addr_byte1, addr_byte2, addr_byte3, addr_byte4, addr_byte5]

        # 생성된 5바이트 주소 전송
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(10) # tALS (ALE setup time)

        for addr_byte in addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(12) # tWP (WE# Pulse Width)
            self.write_data(addr_byte)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(10) # tWH (WE# High Hold Time)
            
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(70) # tADL (ALE to Data Loading time)

    def read_page(self, page_no: int, length: int = 2048):
        """한 페이지 읽기 (내장 하드웨어 ECC 사용)"""
        try:
            self.validate_page(page_no)
            if self.is_bad_block(page_no // self.PAGES_PER_BLOCK):
                raise RuntimeError(f"Bad Block({page_no // self.PAGES_PER_BLOCK}) 읽기 시도")
            
            # [1] 읽기 명령 및 주소 전송 (00h)
            self.write_command(0x00)
            self._write_full_address(page_no, col_addr=0)
            
            # [2] 읽기 확정 명령 (30h)
            self.write_command(0x30)
            
            # [3] 데이터가 캐시로 로드될 때까지 대기 (tR_ECC)
            self.wait_ready()
            
            # [4] ECC 처리 결과 확인 (중요!)
            status = self.check_read_status() # 아래에 추가할 새 함수
            if status == "UNCORRECTABLE_ERROR":
                print(f"경고: 페이지 {page_no}에서 수정 불가능한 ECC 오류 발생!")
                # 수정 불가능한 경우, FF로 채워진 데이터를 반환하거나 예외 발생
                return b'\xFF' * length
            elif status == "CORRECTED_WITH_REWRITE_RECOMMENDED":
                print(f"정보: 페이지 {page_no}에서 ECC 오류가 수정되었으나, 해당 블록을 재기록(refresh)하는 것을 권장합니다.")

            # [5] (오류 수정된) 데이터 읽기
            self.set_data_pins_input()
            GPIO.output(self.CE, GPIO.LOW)
            read_bytes = [self.read_data() for _ in range(length)]
            GPIO.output(self.CE, GPIO.HIGH)
            # 읽기 후에는 finally 블록에서 출력 모드로 자동 복원됨
                
            return bytes(read_bytes)
            
        except Exception as e:
            raise RuntimeError(f"페이지 읽기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.reset_pins()

    def check_read_status(self) -> str:
        """읽기 동작 후 ECC 상태를 확인합니다."""
        self.write_command(0x70)  # Read Status
        status_byte = self.read_data()
        
        # READ MODE(00h)로 다시 전환하여 데이터 출력을 활성화해야 함
        self.write_command(0x00)

        if status_byte & 0x01:  # Bit 0 (FAIL): Uncorrectable error
            return "UNCORRECTABLE_ERROR"
        if status_byte & 0x08:  # Bit 3 (Rewrite recommended)
            return "CORRECTED_WITH_REWRITE_RECOMMENDED"
            
        return "SUCCESS"
    
    def read_page_two_plane(self, page_no1: int, page_no2: int, length: int = 2048) -> (bytes, bytes):
        """
        서로 다른 플레인에 있는 두 페이지를 동시에 읽어옵니다.

        요구 조건:
        - 두 블록은 서로 다른 플레인에 있어야 합니다. (블록 번호의 6번째 비트가 달라야 함)
        - 두 주소의 페이지 오프셋(PA[5:0]) 및 컬럼 주소는 동일해야 합니다.
        """
        try:
            # 1. 주소 및 요구 조건 유효성 검사
            self.validate_page(page_no1)
            self.validate_page(page_no2)
            block_no1 = page_no1 // self.PAGES_PER_BLOCK
            block_no2 = page_no2 // self.PAGES_PER_BLOCK

            if ((block_no1 >> 6) & 1) == ((block_no2 >> 6) & 1):
                raise ValueError("두 블록이 동일한 플레인에 있습니다.")
            if (page_no1 % self.PAGES_PER_BLOCK) != (page_no2 % self.PAGES_PER_BLOCK):
                raise ValueError("두 주소의 페이지 오프셋이 다릅니다.")
            if self.is_bad_block(block_no1) or self.is_bad_block(block_no2):
                raise RuntimeError(f"Bad Block 접근 시도: 블록 {block_no1} 또는 {block_no2}")

            # --- Two-Plane Read 시퀀스 시작 (00h-Addr1-00h-Addr2-30h) ---
            
            # [1] 첫 번째 플레인 주소 설정
            self.write_command(0x00)
            self._write_full_address(page_no1)
            
            # [2] 두 번째 플레인 주소 설정
            self.write_command(0x00)
            self._write_full_address(page_no2)

            # [3] 동시 읽기 시작 명령
            self.write_command(0x30)
            
            # [4] 두 페이지 데이터가 캐시로 로드될 때까지 대기 (tR)
            self.wait_ready()
            
            # [5] page_no2의 ECC 상태 확인 및 데이터 읽기
            status2 = self.check_read_status()
            if status2 == "UNCORRECTABLE_ERROR":
                print(f"\n경고: 페이지 {page_no2}에서 수정 불가능한 ECC 오류 발생!")
                data2 = b'\xFF' * length
            else:
                self.set_data_pins_input() # <<-- 읽기 직전에 입력으로 변경
                GPIO.output(self.CE, GPIO.LOW)
                read_bytes_2 = [self.read_data() for _ in range(length)]
                data2 = bytes(read_bytes_2)
                GPIO.output(self.CE, GPIO.HIGH)
                self.set_data_pins_output() # <<-- 읽기 직후에 출력으로 복원

            # [6] 6. 플레인 변경 (이제 핀이 출력 모드이므로 안전)
            self.write_command(0x06)
            self._write_full_address(page_no1)
            self.write_command(0xE0)
            self._delay_ns(self.tWHR)

            # [7] 7. page_no1의 ECC 상태 확인 및 데이터 읽기
            status1 = self.check_read_status()
            if status1 == "UNCORRECTABLE_ERROR":
                print(f"\n경고: 페이지 {page_no1}에서 수정 불가능한 ECC 오류 발생!")
                data1 = b'\xFF' * length
            else:
                self.set_data_pins_input() # <<-- 다시 읽기 직전에 입력으로 변경
                GPIO.output(self.CE, GPIO.LOW)
                read_bytes_1 = [self.read_data() for _ in range(length)]
                data1 = bytes(read_bytes_1)
                GPIO.output(self.CE, GPIO.HIGH)

            return data1, data2

        except Exception as e:
            raise RuntimeError(f"Two-plane 페이지 읽기 실패 ({page_no1}, {page_no2}): {str(e)}")
        finally:
            self.reset_pins() # 최종적으로 핀 상태를 안전하게 복원
            
    def _write_row_address(self, page_no: int):
        """
        데이터시트(Table 2) 사양에 맞게 3바이트 Row Address를 조합하여 전송합니다.
        Erase 동작에서는 PA(페이지 주소) 비트들이 무시됩니다.
        """
        # 페이지 번호로부터 페이지 주소(PA)와 블록 주소(BA) 계산
        page_in_block = page_no % self.PAGES_PER_BLOCK  # PA[5:0] (0-63)
        block_no = page_no // self.PAGES_PER_BLOCK      # BA[11:0] (0-4095)

        # 데이터시트의 Third, Fourth, Fifth address cycle에 맞춰 3바이트 주소 생성
        # Cycle 3: {BA[7], BA[6], PA[5], PA[4], PA[3], PA[2], PA[1], PA[0]}
        addr_byte3 = (block_no & 0xC0) | (page_in_block & 0x3F)

        # Cycle 4: {BA[15], BA[14], BA[13], BA[12], BA[11], BA[10], BA[9], BA[8]}
        # 4Gb 칩은 BA[11:0]만 사용하므로 상위 비트는 0이 됩니다.
        addr_byte4 = (block_no >> 8) & 0xFF

        # Cycle 5: {LOW, LOW, LOW, LOW, LOW, LOW, BA[17], BA[16]}
        # 4Gb 칩은 BA[17:16]을 사용하지 않으므로 이 바이트는 0입니다.
        addr_byte5 = (block_no >> 16) & 0xFF

        row_addresses = [addr_byte3, addr_byte4, addr_byte5]

        # 생성된 주소 전송
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(10) # tALS

        for addr_byte in row_addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(12) # tWP
            self.write_data(addr_byte)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(10) # tWH
            
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(70) # tADL
    
    def erase_block(self, page_no: int):
        """
        한 개의 블록을 지웁니다. (수정된 버전)
        내부적으로 wait_ready()를 사용하여 작업 완료를 기다립니다.
        """
        try:
            # 1. 페이지 및 블록 번호 유효성 검사
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            self.validate_block(block_no)
            
            # 2. 이미 알려진 Bad Block 지우기 시도 방지
            if self.is_bad_block(block_no):
                raise RuntimeError(f"Bad Block({block_no})에 지우기 시도")

            # --- Block Erase 시퀀스 시작 (60h-Addr-D0h) ---
            
            # [1] 지우기 시작 명령 (60h)
            self.write_command(0x60)

            # [2] Row Address 전송 (3 사이클)
            self._write_row_address(page_no)

            # [3] 지우기 확정 명령 (D0h)
            self.write_command(0xD0)
            
            # [4] 작업이 완료될 때까지 대기 (tBERS)
            self.wait_ready()
            
            # [5] 작업 상태 확인
            if not self.check_operation_status():
                # 지우기 실패 시, 해당 블록을 Bad Block으로 처리
                self.mark_bad_block(block_no)
                raise RuntimeError("블록 지우기 실패 (상태 확인)")
                
        except Exception as e:
            # 실패 시 블록 번호를 포함하여 예외 발생
            block_no_for_error = page_no // self.PAGES_PER_BLOCK if 'page_no' in locals() else 'N/A'
            raise RuntimeError(f"블록 지우기 실패 (블록 {block_no_for_error}): {str(e)}")
        
        finally:
            # 작업 성공/실패와 관계없이 핀 상태를 안전하게 복원
            self.reset_pins()
    
    def erase_block_two_plane(self, page_no1: int, page_no2: int):
        """
        서로 다른 플레인에 있는 두 개의 블록을 동시에 지웁니다.
        
        요구 조건:
        - 두 블록은 서로 다른 플레인에 있어야 합니다. (블록 번호의 6번째 비트가 달라야 함)
        - 두 주소의 페이지 오프셋(PA[5:0])은 동일해야 합니다.
        """
        try:
            # 1. 두 페이지 주소 및 블록 번호 유효성 검사
            self.validate_page(page_no1)
            self.validate_page(page_no2)
            block_no1 = page_no1 // self.PAGES_PER_BLOCK
            block_no2 = page_no2 // self.PAGES_PER_BLOCK
            self.validate_block(block_no1)
            self.validate_block(block_no2)
            
            # 2. Two-Plane 동작 요구 조건 검사
            # 조건 1: 서로 다른 플레인에 위치해야 함 (BA[6] 비트 비교)
            if ((block_no1 >> 6) & 1) == ((block_no2 >> 6) & 1):
                raise ValueError("두 블록이 동일한 플레인에 있습니다. Two-plane erase가 불가능합니다.")
            
            # 조건 2: 페이지 오프셋이 동일해야 함 (PA[5:0] 비교)
            if (page_no1 % self.PAGES_PER_BLOCK) != (page_no2 % self.PAGES_PER_BLOCK):
                raise ValueError("두 주소의 페이지 오프셋이 다릅니다. Two-plane erase가 불가능합니다.")

            # --- Two-Plane Erase 시퀀스 시작 ---

            # [Plane 1] 첫 번째 블록 주소 전송
            self.write_command(0x60)
            self._write_row_address(page_no1)
            self.write_command(0xD1) # 첫 번째 플레인 확정
            
            # tDBSY 대기 (Busy for Two-Plane Operation). 데이터시트 상 최대 1us.
            self._delay_ns(1000) # 1us

            # [Plane 2] 두 번째 블록 주소 전송 및 동시 실행
            self.write_command(0x60)
            self._write_row_address(page_no2)
            self.write_command(0xD0) # 두 번째 플레인 확정 및 동시 삭제 시작
            
            # tWB 대기
            time.sleep(0.00015)

            # Ready 대기 (tBERS). 기존 erase_block과 동일한 로직 사용
            timeout_start = time.time()
            while GPIO.input(self.RB) == GPIO.LOW:
                if time.time() - timeout_start > 0.020: # 20ms 타임아웃
                    self.write_command(0xFF) # Reset
                    time.sleep(0.001)
                    self.wait_ready()
                    raise RuntimeError(f"블록 삭제 타임아웃 (블록 {block_no1}, {block_no2})")
                time.sleep(0.0002)

            time.sleep(0.001)

            # 상태 확인
            # 참고: 실패 시(FAIL=1), 어떤 플레인이 실패했는지 알려면 78h(READ STATUS ENHANCED) 명령이 필요.
            # 여기서는 간소하게 둘 중 하나라도 실패하면 에러로 처리.
            if not self.check_operation_status():
                raise RuntimeError("Two-plane 블록 삭제 상태 확인 실패")

        except Exception as e:
            raise RuntimeError(f"Two-plane 블록 삭제 실패 (블록 {block_no1}, {block_no2}): {str(e)}")
        finally:
            self.reset_pins()
            time.sleep(0.002)

    # nand_driver.py 파일
    def write_full_page(self, page_no: int, data: bytes):
        """
        한 페이지 전체를 쓰며, 각 단계를 상세히 출력합니다.
        """
        full_page_size = self.PAGE_SIZE + self.SPARE_SIZE
        if len(data) > full_page_size:
            raise ValueError(f"데이터 크기가 전체 페이지 크기({full_page_size} bytes)를 초과합니다.")
        
        if len(data) < full_page_size:
            data += b'\xFF' * (full_page_size - len(data))

        try:
            self.validate_page(page_no)
            print(f"    [쓰기 시작] Page {page_no}")
            
            # [1] 쓰기 시작 명령 (80h)
            print("      -> 1. 쓰기 시작 명령(80h) 전송")
            self.write_command(0x80)
            
            # [2] 주소 전송 (5 사이클)
            print("      -> 2. 주소 5바이트 전송")
            self._write_full_address(page_no, col_addr=0)
            
            # [3] 데이터 전송
            print(f"      -> 3. 데이터 {len(data)}바이트 전송 시작")
            self.set_data_pins_output()
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            for byte in data:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(12) # tWP
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(10) # tWH
            
            print("      -> 4. 데이터 전송 완료")
            
            # [4] 쓰기 확정 명령 (10h)
            print("      -> 5. 쓰기 확정 명령(10h) 전송 (이제 칩이 Busy 상태로 전환됩니다)")
            self.write_command(0x10)
            
            # [5] 프로그래밍 완료 대기
            self.wait_ready()
            print("      -> 6. 칩 Ready 상태 확인 (작업 완료)")
            
            # [6] 상태 확인
            print("      -> 7. 최종 상태 레지스터 확인")
            if not self.check_operation_status():
                raise RuntimeError("페이지 쓰기 실패 (상태 확인)")
                
        except Exception as e:
            raise RuntimeError(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.reset_pins()