import RPi.GPIO as GPIO
import time

#2

class MT29F8G08ADADA:
    # NAND 플래시 상수
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096 # <<< 8192에서 4096으로 변경
    
    # 타이밍 상수 (ns) - 데이터시트의 Max/Min 값과 충분한 여유를 고려하여 재조정
    # 라즈베리 파이 Python GPIO 제어의 비결정성(non-determinism)을 감안하여 더 큰 값으로 설정
    tWB = 200     # WE# high to R/B# low (데이터시트 Max 100ns -> 200ns)
    tR_ECC = 70000  # Data Transfer from Cell to Register (데이터시트 Max 70us -> 70000ns)
    tRR = 50      # RE# low to RE# high (데이터시트 Min 20ns -> 50ns, Read Cycle Time tRC Min 20ns 고려)
    tWC = 50      # Write Cycle Time (데이터시트 Min 20ns -> 50ns)
    tWP = 20      # WE# pulse width (데이터시트 Min 10ns -> 20ns)
    tWH = 20      # WE# high hold time (데이터시트 Min 7ns -> 20ns)
    tADL = 100    # ALE to data loading time (데이터시트 Min 70ns -> 100ns)
    tREA = 30     # RE# access time (데이터시트 Max 16ns -> 30ns)
    tREH = 20     # RE# high hold time (데이터시트 Min 7ns -> 20ns)
    tWHR = 100    # WE# high to RE# low (데이터시트 Min 60ns -> 100ns)
    tCLS = 20     # CLE setup time (데이터시트 Min 10ns -> 20ns)
    tCLH = 10     # CLE hold time (데이터시트 Min 5ns -> 10ns)
    tALS = 20     # ALE setup time (데이터시트 Min 10ns -> 20ns)
    tALH = 10     # ALE hold time (데이터시트 Min 5ns -> 10ns)
    
    # 새로 추가된/조정된 타이밍 상수
    # tDS (Data setup time): 데이터시트 3.3V Min 7ns, 1.8V Min 10ns. 여유롭게 20ns. 
    tDS = 20   
    # tDH (Data hold time): 데이터시트 3.3V Min 5ns, 1.8V Min 5ns. 여유롭게 10ns. 
    tDH = 10

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
                
            self._delay_ns(200)  # 100ns -> 200ns 대기
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
        """작업 상태 확인 - 개선된 버전"""
        try:
            # 상태 읽기 명령
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.HIGH)
            GPIO.output(self.ALE, GPIO.LOW)
            self._delay_ns(self.tCLS)  # CLE setup time
            
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(0x70)  # Read Status command
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
            
            GPIO.output(self.CLE, GPIO.LOW)
            self._delay_ns(self.tCLH)  # CLE hold time
            self._delay_ns(self.tWHR)  # WE# high to RE# low
            
            # 상태 바이트 읽기
            self.set_data_pins_input()
            GPIO.output(self.RE, GPIO.LOW)
            self._delay_ns(self.tREA)  # RE# access time
            status = self.read_data()
            GPIO.output(self.RE, GPIO.HIGH)
            self._delay_ns(self.tREH)  # RE# high hold time
            
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output()
            
            if status & 0x01:  # Fail bit
                print(f"상태 확인 실패: 0x{status:02X}")
                return False
            return True
            
        except Exception as e:
            print(f"상태 확인 중 오류: {str(e)}")
            return False

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
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기 - 개선된 버전"""
        # tWB 대기
        self._delay_ns(self.tWB)  # 200ns
        
        # R/B# 신호가 HIGH가 될 때까지 대기
        retry_count = 0
        max_retries = 10  # 5 -> 10으로 증가
        
        while retry_count < max_retries:
            timeout_start = time.time()
            while GPIO.input(self.RB) == GPIO.LOW:
                if time.time() - timeout_start > 0.02:
                    break
                time.sleep(0.0001)
                
            if GPIO.input(self.RB) == GPIO.HIGH:
                # 추가 안정화 대기
                self._delay_ns(100)
                return  # Ready 상태 확인
                
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(0.001)  # 1ms 대기 후 재시도
                
        raise RuntimeError("R/B# 시그널 타임아웃")
            
    def set_data_pins_output(self):
        """데이터 핀을 출력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)
        self._delay_ns(200)  # 100ns -> 200ns 대기
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
        self._delay_ns(200)  # 100ns -> 200ns 대기
            
    def write_data(self, data):
        """8비트 데이터 쓰기 (타이밍 제어 강화)"""
        # WE# 사이클 타임 준수
        cycle_start = time.perf_counter_ns()
        
        # 데이터 설정
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
            self._delay_ns(1)
            
        # 데이터 설정 후 안정화 대기
        #self._delay_ns(50)  # 추가된 안정화 대기
        # 데이터 설정 후 안정화 대기 (tDS: Data setup time 확보)
        self._delay_ns(self.tDS) # 
        
        # tWC 타이밍 준수
        elapsed = time.perf_counter_ns() - cycle_start
        if elapsed < self.tWC:
            self._delay_ns(self.tWC - elapsed)

    def read_data(self):
        """8비트 데이터 읽기 (RE# 사이클 없이 순수 GPIO 읽기)"""
        # RE# 사이클은 상위 함수에서 처리됨
        # 여기서는 GPIO 핀 상태만 읽음
        self._delay_ns(self.tREA)  # RE# access time 대기
        
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
            
        return data
        
    def write_command(self, cmd):
        """커맨드 쓰기 - 개선된 타이밍"""
        GPIO.output(self.CE, GPIO.LOW)
        self._delay_ns(50)  # CE# setup time
        
        GPIO.output(self.CLE, GPIO.HIGH)
        self._delay_ns(self.tCLS)  # CLE setup time
        GPIO.output(self.ALE, GPIO.LOW)
        
        GPIO.output(self.WE, GPIO.LOW)
        self._delay_ns(self.tWP)  # WE# pulse width
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)
        self._delay_ns(self.tWH)  # WE# high hold time
        
        GPIO.output(self.CLE, GPIO.LOW)
        self._delay_ns(self.tCLH)  # CLE hold time

    def write_address(self, addr):
        """주소 쓰기 - 개선된 타이밍"""
        GPIO.output(self.CE, GPIO.LOW)   # Chip Enable
        self._delay_ns(50)  # CE# setup time
        
        GPIO.output(self.CLE, GPIO.LOW)  # Command Latch Disable
        GPIO.output(self.ALE, GPIO.HIGH) # Address Latch Enable
        self._delay_ns(self.tALS)  # ALE setup time
        
        GPIO.output(self.WE, GPIO.LOW)   # Write Enable
        self._delay_ns(self.tWP)  # WE# pulse width
        self.write_data(addr)
        GPIO.output(self.WE, GPIO.HIGH)  # Write Disable
        self._delay_ns(self.tWH)  # WE# high hold time
        
        GPIO.output(self.ALE, GPIO.LOW)  # Address Latch Disable
        self._delay_ns(self.tALH)  # ALE hold time
        self._delay_ns(self.tADL)  # ALE to data loading time

    
    def enable_internal_ecc(self):
        """데이터시트 사양에 따라 칩의 내장 ECC 엔진을 활성화하고 상태를 검증합니다."""
        try:
            print("내부 ECC 엔진 활성화 시도...")
            
            # [1] SET FEATURES (EFh) 명령
            self.write_command(0xEF)

            # [2] Feature Address (90h) 전송
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            self._delay_ns(self.tALS)

            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(0x90)  # Feature Address
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
            
            GPIO.output(self.ALE, GPIO.LOW)
            self._delay_ns(self.tALH)
            self._delay_ns(self.tADL)

            # [3] Parameters (P1=08h for ECC Enable, P2-P4=00h) 전송
            params = [0x08, 0x00, 0x00, 0x00]
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)

            for p in params:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP)
                self.write_data(p)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH)
            
            # [4] tFEAT 대기
            self.wait_ready()
            time.sleep(0.001)
            
            # [5] ECC 상태 검증 - GET FEATURES로 확인
            print("ECC 활성화 상태를 검증합니다...")
            
            # GET FEATURES (EEh) 명령
            self.write_command(0xEE)
            
            # Feature Address (90h)
            self.write_address(0x90)
            
            # tFEAT 대기
            self._delay_ns(2000)  # 2us 대기
            
            # 4바이트 파라미터 읽기
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
            
            # [6] P1 파라미터 검증
            p1_value = params_read[0]
            
            if p1_value == 0x08:
                print("✓ 내부 ECC 엔진이 성공적으로 활성화되었습니다.")
                print(f"  검증 결과: P1=0x{p1_value:02X} (ECC Enabled)")
                return True
            elif p1_value == 0x00:
                print("✗ 내부 ECC 엔진 활성화에 실패했습니다.")
                print(f"  검증 결과: P1=0x{p1_value:02X} (ECC Still Disabled)")
                return False
            else:
                print(f"⚠ 예상하지 못한 P1 값: 0x{p1_value:02X}")
                print("  ECC 상태를 정확히 판단할 수 없습니다.")
                return False

        except Exception as e:
            print(f"✗ 내부 ECC 활성화 중 오류 발생: {str(e)}")
            return False
        finally:
            self.reset_pins()
    
    def disable_internal_ecc(self):
        """데이터시트 사양에 따라 칩의 내장 ECC 엔진을 비활성화합니다."""
        try:
            print("내부 ECC 엔진 비활성화 시도...")
            # SET FEATURES (EFh) 명령
            self.write_command(0xEF)

            # Feature Address (90h) 전송
            self.write_address(0x90)

            # Parameters (P1=00h for ECC Disable, P2-P4=00h) 전송 [cite: 1520, 1531]
            params = [0x00, 0x00, 0x00, 0x00]
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            self.set_data_pins_output() # 데이터 핀을 출력으로 설정
            for p in params:
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP)
                self.write_data(p)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH)
            # [4] tFEAT 시간 대기 (기능 설정 완료까지)
            self.wait_ready()
            time.sleep(0.001)  # 명령이 완전히 처리될 시간을 보장
            
            # [5] ECC 상태 검증 - GET FEATURES로 확인
            print("ECC 비활성화 상태를 검증합니다...")
            
            # GET FEATURES (EEh) 명령
            self.write_command(0xEE)
            
            # Feature Address (90h for Array operation mode)
            self.write_address(0x90)
            
            # tFEAT 대기 (칩이 파라미터를 준비하는 시간)
            self._delay_ns(2000)  # 2us 대기
            
            # 4바이트 파라미터(P1-P4) 읽기
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
            
            # [6] P1 파라미터 검증
            p1_value = params_read[0]
            
            if p1_value == 0x00:
                print("✓ 내부 ECC 엔진이 성공적으로 비활성화되었습니다.")
                print(f"  검증 결과: P1=0x{p1_value:02X} (ECC Disabled)")
                return True
            elif p1_value == 0x08:
                print("✗ 내부 ECC 엔진 비활성화에 실패했습니다.")
                print(f"  검증 결과: P1=0x{p1_value:02X} (ECC Still Enabled)")
                return False
            else:
                print(f"⚠ 예상하지 못한 P1 값: 0x{p1_value:02X}")
                print("  ECC 상태를 정확히 판단할 수 없습니다.")
                return False
            #self.wait_ready() # tFEAT 시간 대기
            #time.sleep(0.001) # 명령이 완전히 처리될 시간을 보장
            #print("내부 ECC 엔진이 성공적으로 비활성화되었습니다.")

        except Exception as e:
            #raise RuntimeError(f"내부 ECC 비활성화 실패: {str(e)}")
            print(f"✗ 내부 ECC 비활성화 중 오류 발생: {str(e)}")
            return False
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
                    self._delay_ns(self.tREA) # RE# access time
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
        """한 페이지 쓰기 (내장 하드웨어 ECC 사용) - 개선된 버전"""
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
            
            # [3] 데이터 전송 (개선된 타이밍)
            self.set_data_pins_output()
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            for byte_idx, byte in enumerate(data):
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP) # WE# pulse width
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH) # WE# high hold time
                
                # 매 256바이트마다 짧은 대기 (버퍼링 고려)
                if (byte_idx + 1) % 256 == 0:
                    self._delay_ns(1000)  # 1us 대기
                
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

    def read_page(self, page_no: int, length: int = 2048):
        """한 페이지 읽기 (내장 하드웨어 ECC 사용) - 개선된 버전"""
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
            
            # [4] ECC 처리 결과 확인
            status = self.check_read_status()
            if status == "UNCORRECTABLE_ERROR":
                print(f"경고: 페이지 {page_no}에서 수정 불가능한 ECC 오류 발생!")
                # 수정 불가능한 경우, FF로 채워진 데이터를 반환하거나 예외 발생
                return b'\xFF' * length
            elif status == "CORRECTED_WITH_REWRITE_RECOMMENDED":
                print(f"정보: 페이지 {page_no}에서 ECC 오류가 수정되었으나, 해당 블록을 재기록(refresh)하는 것을 권장합니다.")

            # [5] (오류 수정된) 데이터 읽기
            self.set_data_pins_input()
            self._delay_ns(200)
            GPIO.output(self.CE, GPIO.LOW)
            self._delay_ns(50)  # CE# setup time
            
            read_bytes = []
            for i in range(length):
                # 올바른 RE# 사이클 타이밍 구현
                cycle_start = time.perf_counter_ns()
                
                # RE# LOW (읽기 시작)
                GPIO.output(self.RE, GPIO.LOW)
                self._delay_ns(self.tREA)  # RE# access time 대기
                
                # 데이터 읽기 (RE# LOW 상태에서)
                byte_data = self.read_data()
                
                # RE# HIGH (읽기 완료)
                GPIO.output(self.RE, GPIO.HIGH)
                self._delay_ns(self.tREH)  # RE# high hold time
                
                read_bytes.append(byte_data)
                
                # tRC (Read Cycle Time) 준수
                elapsed = time.perf_counter_ns() - cycle_start
                if elapsed < self.tRR:  # tRR은 실제로 tRC와 같음
                    self._delay_ns(self.tRR - elapsed)

            GPIO.output(self.CE, GPIO.HIGH)
            # 읽기 후에는 finally 블록에서 출력 모드로 자동 복원됨
                
            return bytes(read_bytes)
            
        except Exception as e:
            raise RuntimeError(f"페이지 읽기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.reset_pins()

    def check_read_status(self) -> str:
        """읽기 동작 후 ECC 상태를 확인합니다. - 개선된 버전"""
        try:
            # 상태 읽기 명령
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.HIGH)
            GPIO.output(self.ALE, GPIO.LOW)
            self._delay_ns(self.tCLS)  # CLE setup time
            
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(0x70)  # Read Status command
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
            
            GPIO.output(self.CLE, GPIO.LOW)
            self._delay_ns(self.tCLH)  # CLE hold time
            self._delay_ns(self.tWHR)  # WE# high to RE# low
            
            # 상태 바이트 읽기
            self.set_data_pins_input()
            GPIO.output(self.RE, GPIO.LOW)
            self._delay_ns(self.tREA)  # RE# access time
            status_byte = self.read_data()
            GPIO.output(self.RE, GPIO.HIGH)
            self._delay_ns(self.tREH)  # RE# high hold time
            
            GPIO.output(self.CE, GPIO.HIGH)
            self.set_data_pins_output()
            
            # READ MODE(00h)로 다시 전환하여 데이터 출력을 활성화해야 함
            self.write_command(0x00)

            if status_byte & 0x01:  # Bit 0 (FAIL): Uncorrectable error
                return "UNCORRECTABLE_ERROR"
            if status_byte & 0x08:  # Bit 3 (Rewrite recommended)
                return "CORRECTED_WITH_REWRITE_RECOMMENDED"
                
            return "SUCCESS"
            
        except Exception as e:
            print(f"상태 확인 중 오류: {str(e)}")
            return "ERROR"
    
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
                self.set_data_pins_input()
                GPIO.output(self.CE, GPIO.LOW)
                read_bytes_2 = [self.read_data() for _ in range(length)]
                data2 = bytes(read_bytes_2)
                GPIO.output(self.CE, GPIO.HIGH)
                self.set_data_pins_output()

            # [6] 플레인 변경 (이제 핀이 출력 모드이므로 안전)
            self.write_command(0x06)
            self._write_full_address(page_no1)
            self.write_command(0xE0)
            self._delay_ns(self.tWHR)

            # [7] page_no1의 ECC 상태 확인 및 데이터 읽기
            status1 = self.check_read_status()
            if status1 == "UNCORRECTABLE_ERROR":
                print(f"\n경고: 페이지 {page_no1}에서 수정 불가능한 ECC 오류 발생!")
                data1 = b'\xFF' * length
            else:
                self.set_data_pins_input()
                GPIO.output(self.CE, GPIO.LOW)
                read_bytes_1 = [self.read_data() for _ in range(length)]
                data1 = bytes(read_bytes_1)
                GPIO.output(self.CE, GPIO.HIGH)

            return data1, data2

        except Exception as e:
            raise RuntimeError(f"Two-plane 페이지 읽기 실패 ({page_no1}, {page_no2}): {str(e)}")
        finally:
            self.reset_pins()
    
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

    def write_full_page(self, page_no: int, data: bytes):
        """
        한 페이지 전체(메인+스페어, 2112 바이트)를 씁니다.
        데이터가 2112 바이트보다 작으면 나머지는 0xFF로 채웁니다.
        개선된 버전
        """
        # 전체 페이지 크기 (2112 바이트) 유효성 검사
        full_page_size = self.PAGE_SIZE + self.SPARE_SIZE
        if len(data) > full_page_size:
            raise ValueError(f"데이터 크기가 전체 페이지 크기({full_page_size} bytes)를 초과합니다.")
        
        # 데이터가 전체 페이지 크기보다 작을 경우 0xFF로 패딩
        if len(data) < full_page_size:
            data += b'\xFF' * (full_page_size - len(data))

        try:
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            if self.is_bad_block(block_no):
                raise RuntimeError(f"Bad Block({block_no})에 쓰기 시도")
            
            # [1] 쓰기 시작 명령 (80h)
            self.write_command(0x80)
            
            # [2] 주소 전송 (5 사이클)
            self._write_full_address(page_no, col_addr=0)
            
            # [3] 데이터 전송 (개선된 타이밍)
            self.set_data_pins_output()
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            for byte_idx, byte in enumerate(data):
                GPIO.output(self.WE, GPIO.LOW)
                self._delay_ns(self.tWP) # WE# pulse width
                self.write_data(byte)
                GPIO.output(self.WE, GPIO.HIGH)
                self._delay_ns(self.tWH) # WE# high hold time
                
                # 매 256바이트마다 짧은 대기 (버퍼링 고려)
                #if (byte_idx + 1) % 256 == 0:
                #    self._delay_ns(1000)  # 1us 대기
                self._delay_ns(50)

            # [4] 쓰기 확정 명령 (10h)
            self.write_command(0x10)
            
            # [5] tPROG_ECC 대기
            self.wait_ready()
            
            # [6] 상태 확인
            if not self.check_operation_status():
                # self.mark_bad_block(block_no) # Bad block 없다고 가정하므로 주석 처리하거나 제거
                raise RuntimeError("페이지 쓰기 실패 (상태 확인)")
                
        except Exception as e:
            raise RuntimeError(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.reset_pins()
    
    def check_ecc_status(self):
        """GET FEATURES(EEh) 명령을 사용해 칩의 현재 ECC 설정 상태를 읽고 출력합니다."""
        print(".-" * 20)
        print("칩의 현재 ECC 상태를 확인합니다...")
        try:
            # GET FEATURES (EEh) 명령
            self.write_command(0xEE)
            # Feature Address (90h for Array operation mode)
            self.write_address(0x90)

            self._delay_ns(2000)  # 2us 대기 (안정성을 위해 2배)

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
            
            p1 = params[0]
            # 데이터시트에 따르면 P1의 3번 비트가 ECC 활성화 여부를 나타냄
            if (p1 >> 3) & 0x01:
                print(">>> 내장 ECC 상태: 활성화됨 (Enabled)")
            else:
                print(">>> 내장 ECC 상태: 비활성화됨 (Disabled)")
            print("-" * 20)

        except Exception as e:
            print(f"ECC 상태 확인 중 오류 발생: {e}")
        finally:
            self.reset_pins()

    def _write_full_address(self, page_no: int, col_addr: int = 0):
        """
        4Gb 모델(MT29F4G)의 데이터시트(Table 2) 사양에 맞게 
        5바이트 전체 주소(컬럼+로우)를 조합하여 전송합니다.
        """
        page_in_block = page_no % self.PAGES_PER_BLOCK
        block_no = page_no // self.PAGES_PER_BLOCK

        # 4096개 블록은 12비트(0~11)로 표현됩니다. (2^12 = 4096)
        # 데이터시트는 이 12개 비트를 BA6 ~ BA17로 매핑합니다.
        # block_no의 0번째 비트 -> BA6, 11번째 비트 -> BA17

        addresses = [0] * 5

        # Cycle 1 & 2: Column Address (2바이트)
        addresses[0] = col_addr & 0xFF
        addresses[1] = (col_addr >> 8) & 0x0F # 12비트 컬럼 주소

        # Cycle 3: {BA7, BA6, PA5, PA4, PA3, PA2, PA1, PA0}
        # block_no의 하위 2비트(BA7, BA6)와 페이지 주소를 조합합니다.
        addresses[2] = (page_in_block & 0x3F) | ((block_no & 0x03) << 6)
        
        # Cycle 4: {BA15, BA14, BA13, BA12, BA11, BA10, BA9, BA8}
        # block_no의 중간 8비트를 전송합니다.
        addresses[3] = (block_no >> 2) & 0xFF
        
        # Cycle 5: {LOW, LOW, LOW, LOW, LOW, LOW, BA17, BA16}
        # block_no의 상위 2비트(BA17, BA16)를 전송합니다.
        # 8Gb의 (>> 10) & 0x07 에서 4Gb에 맞게 (>> 10) & 0x03으로 수정
        addresses[4] = (block_no >> 10) & 0x03

        # 생성된 5바이트 주소를 전송
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

    def _write_row_address(self, page_no: int):
        """
        4Gb 모델(MT29F4G)의 데이터시트(Table 2) 사양에 맞게 
        3바이트 Row Address(블록+페이지)를 조합하여 전송합니다.
        """
        page_in_block = page_no % self.PAGES_PER_BLOCK
        block_no = page_no // self.PAGES_PER_BLOCK

        row_addresses = [
            # Cycle 3: {BA7, BA6, PA5:PA0}
            (page_in_block & 0x3F) | ((block_no & 0x03) << 6),
            # Cycle 4: {BA15:BA8}
            (block_no >> 2) & 0xFF,
            # Cycle 5: {BA17, BA16}
            # 8Gb의 (>> 10) & 0x07 에서 4Gb에 맞게 (>> 10) & 0x03으로 수정
            (block_no >> 10) & 0x03
        ]

        # 생성된 주소를 전송
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