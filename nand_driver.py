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
        
        # Bad Block 테이블 초기화
        self.bad_blocks = set()

        try:
            # GPIO 초기화
            GPIO.cleanup()  # 이전 설정 초기화
            time.sleep(0.1)  # 초기화 후 잠시 대기
            
            GPIO.setmode(GPIO.BCM)  # BCM 모드로 명시적 설정
            GPIO.setwarnings(False)
            
            # 컨트롤 핀 출력으로 설정
            GPIO.setup(self.RB, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # R/B# 핀은 풀업 저항 사용
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
            
            # Bad Block 스캔
            self.scan_bad_blocks()
            
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
            
            # 데이터 핀을 출력 모드로 설정하고 HIGH로 설정
            for pin in self.IO_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH)
                
            time.sleep(0.0001)  # 100us 대기
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
        time.sleep(self.tWB / 1_000_000_000)  # 100ns
        
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
        time.sleep(0.00001)  # 10us 대기
            
    def set_data_pins_input(self):
        """데이터 핀을 입력 모드로 설정"""
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN)
        time.sleep(0.00001)  # 10us 대기
            
    def write_data(self, data):
        """8비트 데이터 쓰기 (타이밍 제어 추가)"""
        # WE# 사이클 타임 준수
        cycle_start = time.time_ns()
        
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
            
        # tWC 타이밍 준수
        elapsed = time.time_ns() - cycle_start
        if elapsed < self.tWC:
            time.sleep((self.tWC - elapsed) / 1_000_000_000)

    def read_data(self):
        """8비트 데이터 읽기 (타이밍 제어 추가)"""
        # RE# 사이클 타임 준수
        cycle_start = time.time_ns()
        
        data = 0
        for i in range(8):
            data |= GPIO.input(self.IO_pins[i]) << i
            
        # tRR 타이밍 준수
        elapsed = time.time_ns() - cycle_start
        if elapsed < self.tRR:
            time.sleep((self.tRR - elapsed) / 1_000_000_000)
            
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
        
    def hamming_encode(self, data):
        """해밍 코드로 데이터 인코딩"""
        def calculate_parity(data, position):
            parity = 0
            for i in range(len(data)):
                if i & position:
                    parity ^= data[i]
            return parity

        # 데이터 비트 수에 따른 패리티 비트 수 계산
        m = len(data)
        r = 1
        while (1 << r) < (m + r + 1):
            r += 1

        # 인코딩된 데이터 준비
        encoded = [0] * (m + r)
        j = 0  # 원본 데이터 인덱스
        
        # 데이터와 패리티 비트 위치 설정
        for i in range(1, m + r + 1):
            if i & (i - 1):  # i가 2의 거듭제곱이 아닌 경우
                encoded[i-1] = data[j]
                j += 1

        # 패리티 비트 계산
        for i in range(r):
            pos = 1 << i
            encoded[pos-1] = calculate_parity(encoded, pos)

        return encoded

    def hamming_decode(self, encoded):
        """해밍 코드로 데이터 디코딩 및 오류 검출/수정"""
        # 패리티 비트 수 계산
        r = 1
        while (1 << r) < len(encoded):
            r += 1

        # 신드롬 계산
        syndrome = 0
        for i in range(r):
            pos = 1 << i
            parity = 0
            for j in range(len(encoded)):
                if j & pos:
                    parity ^= encoded[j]
            if parity:
                syndrome |= pos

        # 오류 검출 및 수정
        if syndrome:
            if syndrome <= len(encoded):
                encoded[syndrome-1] ^= 1  # 오류 비트 수정
            else:
                raise RuntimeError("수정 불가능한 오류 발견")

        # 원본 데이터 추출
        data = []
        for i in range(1, len(encoded) + 1):
            if i & (i - 1):  # i가 2의 거듭제곱이 아닌 경우
                data.append(encoded[i-1])

        return data

    def is_bad_block(self, block_no):
        """해당 블록이 Bad Block인지 확인"""
        return block_no in self.bad_blocks

    def mark_bad_block(self, block_no):
        """블록을 Bad Block으로 표시"""
        self.bad_blocks.add(block_no)
        
    def scan_bad_blocks(self):
        """전체 NAND를 스캔하여 Bad Block 테이블 구성"""
        print("Bad Block 스캔 시작...")
        MAX_RETRIES = 3  # 최대 재시도 횟수
        
        try:
            for block in range(self.TOTAL_BLOCKS):
                page = block * self.PAGES_PER_BLOCK
                retry_count = 0
                block_scan_success = False
                
                # 진행 상황 표시 (100블록마다)
                if block % 100 == 0:
                    print(f"Bad Block 스캔 진행 중: {block}/{self.TOTAL_BLOCKS} 블록 완료")
                
                try:
                    # 첫 페이지와 마지막 페이지의 첫 바이트 확인
                    try:
                        first_page = self.read_page(page, 1)
                        first_byte = first_page[0] if first_page else 0x00
                    except Exception as e:
                        print(f"첫 페이지 읽기 실패 (블록 {block}): {str(e)}")
                        first_byte = 0x00  # 오류 발생 시 Bad Block으로 처리하기 위해
                    
                    try:
                        last_page = self.read_page(page + self.PAGES_PER_BLOCK - 1, 1)
                        last_byte = last_page[0] if last_page else 0x00
                    except Exception as e:
                        print(f"마지막 페이지 읽기 실패 (블록 {block}): {str(e)}")
                        last_byte = 0x00  # 오류 발생 시 Bad Block으로 처리하기 위해
                    
                    # 첫 바이트가 0xFF가 아니면 Bad Block
                    if first_byte != 0xFF or last_byte != 0xFF:
                        self.mark_bad_block(block)
                        print(f"Bad Block 발견: 블록 {block} (첫 페이지: 0x{first_byte:02X}, 마지막 페이지: 0x{last_byte:02X})")
                    
                except Exception as e:
                    print(f"블록 {block} 스캔 중 오류 발생: {str(e)}")
                    # 안전을 위해 스캔에 실패한 블록은 Bad Block으로 표시
                    self.mark_bad_block(block)
            
            print(f"Bad Block 스캔 완료. 총 {len(self.bad_blocks)}개의 Bad Block 발견.")
            if self.bad_blocks:
                print("Bad Block 목록:", sorted(list(self.bad_blocks)))
                
        except Exception as e:
            print(f"Bad Block 스캔 중 심각한 오류 발생: {str(e)}")
            print("스캔을 중단하고 계속 진행합니다.")

    def find_good_block(self, start_block):
        """주어진 블록부터 시작하여 사용 가능한 블록 찾기"""
        current_block = start_block
        while current_block < self.TOTAL_BLOCKS:
            if not self.is_bad_block(current_block):
                return current_block
            current_block += 1
        raise RuntimeError("사용 가능한 블록이 없습니다")

    def write_page(self, page_no: int, data: bytes):
        """한 페이지 쓰기 (ECC 적용) - 데이터시트 사양 준수"""
        try:
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            
            # Bad Block 체크
            if self.is_bad_block(block_no):
                new_block = self.find_good_block(block_no + 1)
                page_no = new_block * self.PAGES_PER_BLOCK + (page_no % self.PAGES_PER_BLOCK)
                
            # ECC 생성 및 데이터 준비
            encoded_data = []
            for i in range(0, len(data), 256):  # 256바이트 단위로 ECC 생성
                chunk = data[i:i+256]
                if len(chunk) < 256:  # 패딩
                    chunk = chunk + b'\xFF' * (256 - len(chunk))
                encoded = self.hamming_encode(list(chunk))
                encoded_data.extend(encoded)
            
            # 데이터시트 PROGRAM PAGE (80h-10h) 시퀀스
            self.set_data_pins_output()
            
            # [1] 쓰기 시작 명령 (80h)
            self.write_command(0x80)
            
            # [2] 주소 전송 (5사이클) - 데이터시트 순서 준수
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            
            # 1~2번째 바이트: 컬럼 주소 (페이지 내 시작 위치)
            # 컬럼 주소 하위 바이트
            GPIO.output(self.WE, GPIO.LOW)
            time.sleep(0.00001)  # tWP (WE# pulse width): 10ns 최소
            self.write_data(0x00)
            time.sleep(0.00001)
            GPIO.output(self.WE, GPIO.HIGH)
            time.sleep(0.00001)  # tWH (WE# high hold time)
            
            # 컬럼 주소 상위 바이트  
            GPIO.output(self.WE, GPIO.LOW)
            time.sleep(0.00001)
            self.write_data(0x00)
            time.sleep(0.00001)
            GPIO.output(self.WE, GPIO.HIGH)
            time.sleep(0.00001)
            
            # 3~5번째 바이트: 로우 주소 (블록 및 페이지)
            for i in range(3):
                GPIO.output(self.WE, GPIO.LOW)
                time.sleep(0.00001)
                self.write_data((page_no >> (8 * i)) & 0xFF)
                time.sleep(0.00001)
                GPIO.output(self.WE, GPIO.HIGH)
                time.sleep(0.00001)
                
            GPIO.output(self.ALE, GPIO.LOW)
            time.sleep(0.0001)  # tADL (ALE to data loading time): 100ns
            
            # [3] 데이터 전송
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            # 인코딩된 데이터 쓰기
            for byte in encoded_data:
                GPIO.output(self.WE, GPIO.LOW)
                time.sleep(0.00001)  # tWP
                self.write_data(byte)
                time.sleep(0.00001)
                GPIO.output(self.WE, GPIO.HIGH)
                time.sleep(0.00001)  # tWH
                
            # [4] 쓰기 확정 명령 (10h)
            self.write_command(0x10)
            
            # [5] tPROG 대기 (최대 600µs)
            time.sleep(0.0006)  # 600µs 대기
            self.wait_ready()
            
            # [6] 상태 확인
            if not self.check_operation_status():
                self.mark_bad_block(block_no)
                raise RuntimeError("페이지 쓰기 실패")
                
        except Exception as e:
            self.reset_pins()
            raise RuntimeError(f"페이지 쓰기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.set_data_pins_output()

    def read_page(self, page_no: int, length: int = 2048):
        """한 페이지 읽기 (ECC 적용) - 데이터시트 사양 준수"""
        try:
            self.validate_page(page_no)
            block_no = page_no // self.PAGES_PER_BLOCK
            
            # Bad Block 체크
            if self.is_bad_block(block_no):
                raise RuntimeError(f"Bad Block 접근 시도: 블록 {block_no}")
            
            # 데이터시트 READ PAGE (00h-30h) 시퀀스
            # [1] 읽기 시작 명령 (00h)
            self.write_command(0x00)
            
            # [2] 주소 전송 (5사이클) - 데이터시트 순서 준수
            GPIO.output(self.CE, GPIO.LOW)
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.HIGH)
            
            # 1~2번째 바이트: 컬럼 주소
            GPIO.output(self.WE, GPIO.LOW)
            time.sleep(0.00001)
            self.write_data(0x00)
            time.sleep(0.00001)
            GPIO.output(self.WE, GPIO.HIGH)
            time.sleep(0.00001)
            
            GPIO.output(self.WE, GPIO.LOW)
            time.sleep(0.00001)
            self.write_data(0x00)
            time.sleep(0.00001)
            GPIO.output(self.WE, GPIO.HIGH)
            time.sleep(0.00001)
            
            # 3~5번째 바이트: 로우 주소
            for i in range(3):
                GPIO.output(self.WE, GPIO.LOW)
                time.sleep(0.00001)
                self.write_data((page_no >> (8 * i)) & 0xFF)
                time.sleep(0.00001)
                GPIO.output(self.WE, GPIO.HIGH)
                time.sleep(0.00001)
                
            GPIO.output(self.ALE, GPIO.LOW)
            time.sleep(0.0001)  # tADL
            
            # [3] 읽기 확정 명령 (30h)
            self.write_command(0x30)
            
            # [4] tR 대기 (최대 25µs)
            time.sleep(0.000025)  # 25µs 대기
            self.wait_ready()
            
            # [5] 데이터 읽기 준비
            self.set_data_pins_input()
            GPIO.output(self.CLE, GPIO.LOW)
            GPIO.output(self.ALE, GPIO.LOW)
            
            # 첫 바이트만 읽을 경우 ECC 없이 직접 읽기
            if length == 1:
                # RE# 토글: HIGH -> LOW -> HIGH (데이터시트 사양)
                GPIO.output(self.RE, GPIO.HIGH)  # 초기 상태 확인
                time.sleep(0.00001)
                GPIO.output(self.RE, GPIO.LOW)   # LOW로 토글 (데이터 출력)
                time.sleep(0.00001)              # tREA (RE# access time)
                byte = self.read_data()          # 데이터 읽기
                time.sleep(0.00001)
                GPIO.output(self.RE, GPIO.HIGH)  # HIGH로 복원
                return bytes([byte])
            
            # [6] 전체 페이지 데이터 읽기
            encoded_data = []
            total_bytes = length + (length // 256) * 32  # ECC 오버헤드 포함
            
            for _ in range(total_bytes):
                # RE# 토글 시퀀스 (데이터시트 사양)
                GPIO.output(self.RE, GPIO.HIGH)  # 시작 상태
                time.sleep(0.00001)              # tRHZ (RE# high to output hi-z)
                GPIO.output(self.RE, GPIO.LOW)   # LOW로 토글
                time.sleep(0.00001)              # tREA (RE# access time) 
                byte = self.read_data()          # 데이터 읽기
                time.sleep(0.00001)              # tRH (RE# high hold time)
                GPIO.output(self.RE, GPIO.HIGH)  # HIGH로 복원
                time.sleep(0.00001)              # tRHZ
                encoded_data.append(byte)
            
            # ECC 디코딩 및 오류 수정
            decoded_data = []
            for i in range(0, len(encoded_data), 288):  # 256 + 32 (ECC)
                chunk = encoded_data[i:i+288]
                if len(chunk) == 288:
                    try:
                        decoded = self.hamming_decode(chunk)
                        decoded_data.extend(decoded[:256])
                    except RuntimeError as e:
                        print(f"ECC 오류 발생 (페이지 {page_no}, 오프셋 {i}): {str(e)}")
                        decoded_data.extend([0xFF] * 256)  # 오류 발생 시 0xFF로 채움
            
            return bytes(decoded_data[:length])
            
        except Exception as e:
            self.reset_pins()
            raise RuntimeError(f"페이지 읽기 실패 (페이지 {page_no}): {str(e)}")
        finally:
            self.set_data_pins_output()
            
    def erase_block(self, page_no: int):
        """블록 단위 erase
        
        타이밍:
        - tWB (WE# high to R/B# low): 100ns
        - tBERS (Block Erase Time): ~3.5ms
        - tRST (Device Reset Time): 5us ~ 500us
        """
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

            # tADL (ALE to data loading time) 대기
            time.sleep(0.0001)  # 100us

            # Confirm (0xD0)
            self.write_command(0xD0)
            # tWB 대기 (WE# high to R/B# low)
            time.sleep(self.tWB / 1_000_000_000)  # 100ns

            # Ready 대기 (tBERS)
            timeout_start = time.time()
            while GPIO.input(self.RB) == GPIO.LOW:
                if time.time() - timeout_start > 0.01:  # 10ms (최대 tBERS)
                    # 타임아웃 시 리셋 후 재시도
                    self.write_command(0xFF)  # Reset command
                    time.sleep(0.000005)  # 5us (최소 tRST)
                    raise RuntimeError("블록 삭제 타임아웃")
                time.sleep(0.0001)  # 100us 간격으로 체크
            
            # 상태 확인
            status = self.check_operation_status()
            if not status:
                raise RuntimeError("블록 삭제 실패")
                
        except Exception as e:
            raise RuntimeError(f"블록 삭제 실패 (블록 {page_no // self.PAGES_PER_BLOCK}): {str(e)}")
        
        finally:
            # 항상 안전한 상태로 복원
            try:
                self.reset_pins()
                time.sleep(0.001)  # 1ms 대기
            except:
                pass 