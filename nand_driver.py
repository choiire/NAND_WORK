# -*- coding: utf-8 -*-
import RPi.GPIO as GPIO
import time

class MT29F4G08ABADAWP:
    """
    Micron MT29F4G08ABADAWP NAND Flash 드라이버 (Raspberry Pi 5 용)
    - 비동기식 인터페이스 제어
    - 안정성 및 데이터시트 준수를 위한 개선 사항 포함
    """
    # NAND 플래시 상수 (데이터시트 기반)
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096

    # 타이밍 상수 (단위: 초) - 실제 시스템에서는 더 정밀한 지연 필요
    # Python의 time.sleep()은 ns 단위 정밀도를 보장하지 못하므로
    # 최소한의 지연을 보장하기 위한 값으로 사용합니다.
    T_WB_S = 100 / 1_000_000_000  # 100ns
    T_WC_S = 25 / 1_000_000_000   # 25ns
    T_ADL_S = 100 / 1_000_000_000 # 100ns (데이터시트 tADL은 70ns 이상)
    T_BERS_MAX_S = 0.003          # 3ms (Block Erase 최대 시간)
    T_PROG_MAX_S = 0.0007         # 700us (Page Program 최대 시간)
    T_R_MAX_S = 0.000025          # 25us (Page Read 최대 시간)

    def __init__(self):
        # GPIO 핀 설정 (BCM 모드)
        self.RB = 13  # Ready/Busy (Input, Pull-up)
        self.RE = 26  # Read Enable (Output)
        self.CE = 19  # Chip Enable (Output)
        self.CLE = 11 # Command Latch Enable (Output)
        self.ALE = 10 # Address Latch Enable (Output)
        self.WE = 9   # Write Enable (Output)
        self.IO_pins = [21, 20, 16, 12, 25, 24, 23, 18] # IO0-IO7

        self.bad_blocks = set()
        self._initialize_gpio()
        self.power_on_sequence()
        # self.scan_bad_blocks() # 초기화 시 시간이 오래 걸릴 수 있으므로 필요시 호출

    def _initialize_gpio(self):
        """GPIO 핀을 초기화하고 설정합니다."""
        try:
            GPIO.cleanup()
            time.sleep(0.01)
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # 제어 핀 설정
            GPIO.setup(self.RB, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            control_pins = [self.RE, self.CE, self.WE]
            for pin in control_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            
            latch_pins = [self.CLE, self.ALE]
            for pin in latch_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

            # 데이터 핀을 기본 출력 모드로 설정
            self.set_data_pins_output()
            print("GPIO 초기화 완료.")
        except Exception as e:
            GPIO.cleanup()
            raise RuntimeError(f"GPIO 초기화 실패: {e}")

    def __del__(self):
        """객체 소멸 시 GPIO 리소스를 정리합니다."""
        print("GPIO 리소스를 정리합니다.")
        GPIO.cleanup()

    # --- Low-Level GPIO Control ---
    def set_data_pins_output(self):
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)

    def set_data_pins_input(self):
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

    def _write_to_bus(self, value):
        """8비트 값을 데이터 버스에 씁니다."""
        for i in range(8):
            GPIO.output(self.IO_pins[i], (value >> i) & 1)

    def _read_from_bus(self):
        """데이터 버스에서 8비트 값을 읽습니다."""
        value = 0
        for i in range(8):
            if GPIO.input(self.IO_pins[i]):
                value |= (1 << i)
        return value

    def _strobe_we(self):
        """WE# 핀을 토글하여 쓰기 동작을 수행합니다."""
        time.sleep(self.T_WC_S)
        GPIO.output(self.WE, GPIO.LOW)
        time.sleep(self.T_WC_S)
        GPIO.output(self.WE, GPIO.HIGH)
        time.sleep(self.T_WC_S)
        
    def _strobe_re(self):
        """RE# 핀을 토글하여 읽기 동작을 수행하고 값을 반환합니다."""
        time.sleep(self.T_WC_S)
        GPIO.output(self.RE, GPIO.LOW)
        time.sleep(self.T_WC_S)
        val = self._read_from_bus()
        GPIO.output(self.RE, GPIO.HIGH)
        time.sleep(self.T_WC_S)
        return val

    def wait_ready(self, timeout_s=0.1):
        """R/B# 핀이 Ready(HIGH) 상태가 될 때까지 대기합니다."""
        time.sleep(self.T_WB_S)
        start_time = time.time()
        while GPIO.input(self.RB) == GPIO.LOW:
            if time.time() - start_time > timeout_s:
                raise TimeoutError("NAND Flash가 Ready 상태로 전환되지 않았습니다 (타임아웃).")
        return

    # --- NAND Command & Address Functions ---
    def send_command(self, cmd):
        GPIO.output(self.CLE, GPIO.HIGH)
        self._write_to_bus(cmd)
        self._strobe_we()
        GPIO.output(self.CLE, GPIO.LOW)

    def send_address(self, addr_bytes):
        GPIO.output(self.ALE, GPIO.HIGH)
        for byte in addr_bytes:
            self._write_to_bus(byte)
            self._strobe_we()
        GPIO.output(self.ALE, GPIO.LOW)

    def _build_address(self, page_no, col_addr=0):
        """페이지 및 컬럼 주소로부터 5바이트 주소 배열을 생성합니다."""
        addr_bytes = []
        addr_bytes.append(col_addr & 0xFF)
        addr_bytes.append((col_addr >> 8) & 0xFF)
        addr_bytes.append(page_no & 0xFF)
        addr_bytes.append((page_no >> 8) & 0xFF)
        addr_bytes.append((page_no >> 16) & 0xFF)
        return addr_bytes

    # --- High-Level NAND Operations ---
    def power_on_sequence(self):
        """전원 인가 후 리셋 시퀀스를 수행합니다."""
        try:
            GPIO.output(self.CE, GPIO.HIGH)
            time.sleep(0.001) # 1ms
            GPIO.output(self.CE, GPIO.LOW)
            self.reset()
            print("NAND 칩 리셋 완료.")
        except Exception as e:
             raise RuntimeError(f"파워온 시퀀스 실패: {e}")

    def reset(self):
        """NAND 칩을 리셋합니다."""
        self.send_command(0xFF)
        self.wait_ready()

    def read_id(self):
        """칩 ID를 읽습니다."""
        GPIO.output(self.CE, GPIO.LOW)
        self.send_command(0x90)
        self.send_address([0x00])
        
        self.set_data_pins_input()
        id_bytes = [self._strobe_re() for _ in range(5)]
        self.set_data_pins_output()
        
        GPIO.output(self.CE, GPIO.HIGH)
        return bytes(id_bytes)

    def check_status(self):
        """칩의 상태를 읽습니다."""
        GPIO.output(self.CE, GPIO.LOW)
        self.send_command(0x70)
        self.set_data_pins_input()
        status = self._strobe_re()
        self.set_data_pins_output()
        GPIO.output(self.CE, GPIO.HIGH)
        return status

    def erase_block(self, block_no: int):
        """지정한 블록을 삭제합니다."""
        if block_no in self.bad_blocks:
            print(f"경고: Bad Block {block_no} 삭제 시도 건너뜀.")
            return

        page_no = block_no * self.PAGES_PER_BLOCK
        addr_bytes = self._build_address(page_no)[2:] # 블록 주소는 Row 주소만 사용

        try:
            GPIO.output(self.CE, GPIO.LOW)
            self.send_command(0x60)
            self.send_address(addr_bytes)
            self.send_command(0xD0)
            
            self.wait_ready(timeout_s=self.T_BERS_MAX_S * 1.2) # 타임아웃을 넉넉하게 설정
            
            status = self.check_status()
            if status & 0x01: # 실패 비트 확인
                print(f"블록 {block_no} 삭제 실패. Bad Block으로 마킹합니다.")
                self.bad_blocks.add(block_no)
                raise IOError(f"블록 {block_no} 삭제 실패.")
        finally:
            GPIO.output(self.CE, GPIO.HIGH)
            
    def read_page(self, page_no: int, length: int = PAGE_SIZE):
        """지정한 페이지에서 데이터를 읽습니다."""
        block_no = page_no // self.PAGES_PER_BLOCK
        if block_no in self.bad_blocks:
            raise ValueError(f"Bad Block {block_no} 읽기 시도.")

        addr_bytes = self._build_address(page_no, 0)

        try:
            GPIO.output(self.CE, GPIO.LOW)
            self.send_command(0x00)
            self.send_address(addr_bytes)
            self.send_command(0x30)
            self.wait_ready(timeout_s=self.T_R_MAX_S * 1.2)

            self.set_data_pins_input()
            data = bytes([self._strobe_re() for _ in range(length)])
            self.set_data_pins_output()
            
            return data
        finally:
            GPIO.output(self.CE, GPIO.HIGH)

    def write_page(self, page_no: int, data: bytes):
        """지정한 페이지에 데이터를 씁니다."""
        block_no = page_no // self.PAGES_PER_BLOCK
        if block_no in self.bad_blocks:
            raise ValueError(f"Bad Block {block_no} 쓰기 시도.")

        if len(data) > self.PAGE_SIZE:
            raise ValueError(f"데이터 크기가 페이지 크기({self.PAGE_SIZE} bytes)를 초과합니다.")

        addr_bytes = self._build_address(page_no, 0)
        
        try:
            GPIO.output(self.CE, GPIO.LOW)
            self.send_command(0x80)
            self.send_address(addr_bytes)
            
            # 데이터 쓰기
            time.sleep(self.T_ADL_S)
            for byte in data:
                self._write_to_bus(byte)
                self._strobe_we()
            
            self.send_command(0x10)
            self.wait_ready(timeout_s=self.T_PROG_MAX_S * 1.2)
            
            status = self.check_status()
            if status & 0x01:
                print(f"페이지 {page_no} 쓰기 실패. 블록 {block_no}을 Bad Block으로 마킹합니다.")
                self.bad_blocks.add(block_no)
                raise IOError(f"페이지 {page_no} 쓰기 실패.")
        finally:
            GPIO.output(self.CE, GPIO.HIGH)

# --- 사용 예제 ---
if __name__ == '__main__':
    try:
        nand = MT29F4G08ABADAWP()
        
        # 1. 칩 ID 읽기
        chip_id = nand.read_id()
        print(f"NAND 칩 ID: {chip_id.hex()}")
        if chip_id[0] != 0x2c: # Micron Manufacturer ID
            print("경고: Micron 칩이 아닌 것 같거나 통신 오류가 있습니다.")

        # 2. 특정 블록 삭제 (예: 블록 10)
        target_block = 10
        print(f"\n블록 {target_block} 삭제 시도...")
        nand.erase_block(target_block)
        print(f"블록 {target_block} 삭제 완료.")

        # 3. 삭제된 블록의 첫 페이지 읽어서 0xFF로 채워졌는지 확인
        target_page = target_block * MT29F4G08ABADAWP.PAGES_PER_BLOCK
        print(f"\n페이지 {target_page} (블록 {target_block}의 첫 페이지) 검증...")
        read_data = nand.read_page(target_page, 32) # 앞 32바이트만 확인
        
        if all(b == 0xFF for b in read_data):
            print(f"검증 성공: 페이지가 0xFF로 초기화되었습니다.")
            print(f"읽은 데이터 (앞 32바이트): {read_data.hex()}")
        else:
            print(f"검증 실패: 페이지가 0xFF로 초기화되지 않았습니다.")
            print(f"읽은 데이터 (앞 32바이트): {read_data.hex()}")

        # 4. 특정 페이지에 데이터 쓰기
        write_data = b'Hello, NAND Flash! This is a test.' + b'\x00' * 500
        print(f"\n페이지 {target_page}에 데이터 쓰기 시도...")
        nand.write_page(target_page, write_data)
        print("쓰기 완료.")

        # 5. 쓴 데이터 다시 읽어서 확인
        print(f"\n페이지 {target_page}에서 데이터 다시 읽어서 검증...")
        read_back_data = nand.read_page(target_page, len(write_data))
        
        if read_back_data == write_data:
            print("쓰기/읽기 검증 성공!")
        else:
            print("쓰기/읽기 검증 실패!")
            print(f"원본 데이터: {write_data.hex()}")
            print(f"읽은 데이터: {read_back_data.hex()}")

    except (RuntimeError, IOError, TimeoutError) as e:
        print(f"\n오류 발생: {e}")
    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
    finally:
        GPIO.cleanup()
        print("\nGPIO가 정리되었습니다. 프로그램을 종료합니다.")
