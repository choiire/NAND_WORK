# -*- coding: utf-8 -*-
import RPi.GPIO as GPIO
import time

class MT2F4G08ABADAWP:
    """
    Micron MT29F4G08ABADAWP NAND Flash 드라이버 (Raspberry Pi 5 용)
    - 비동기식 인터페이스 제어
    - 2-Plane Erase 최적화 기능 추가
    """
    # NAND 플래시 상수 (데이터시트 기반)
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096

    # 타이밍 상수 (단위: 초)
    T_WB_S = 100 / 1_000_000_000  # 100ns
    T_WC_S = 25 / 1_000_000_000   # 25ns
    T_ADL_S = 100 / 1_000_000_000 # 100ns (데이터시트 tADL은 70ns 이상)
    T_BERS_MAX_S = 0.003          # 3ms (Block Erase 최대 시간)
    T_PROG_MAX_S = 0.0007         # 700us (Page Program 최대 시간)
    T_R_MAX_S = 0.000025          # 25us (Page Read 최대 시간)

    def __init__(self):
        # GPIO 핀 설정 (BCM 모드)
        self.RB = 13
        self.RE = 26
        self.CE = 19
        self.CLE = 11
        self.ALE = 10
        self.WE = 9
        self.IO_pins = [21, 20, 16, 12, 25, 24, 23, 18]

        self.bad_blocks = set()
        self._initialize_gpio()
        self.power_on_sequence()
        self.scan_bad_blocks()

    def _initialize_gpio(self):
        """GPIO 핀을 초기화하고 설정합니다."""
        try:
            # 스크립트 시작 시 GPIO 상태를 초기화합니다.
            # GPIO.cleanup() # 다른 스크립트와 함께 사용할 경우 충돌을 막기 위해 주석 처리할 수 있습니다.
            time.sleep(0.01)
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.RB, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            control_pins = [self.RE, self.CE, self.WE]
            for pin in control_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            latch_pins = [self.CLE, self.ALE]
            for pin in latch_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            self.set_data_pins_output()
            print("GPIO 초기화 완료.")
        except Exception as e:
            GPIO.cleanup()
            raise RuntimeError(f"GPIO 초기화 실패: {e}")

    def __del__(self):
        """객체 소멸 시 GPIO 리소스를 정리합니다."""
        print("GPIO 리소스를 정리합니다.")
        GPIO.cleanup()

    def set_data_pins_output(self):
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.OUT)

    def set_data_pins_input(self):
        for pin in self.IO_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

    def _write_to_bus(self, value):
        for i in range(8):
            GPIO.output(self.IO_pins[i], (value >> i) & 1)

    def _read_from_bus(self):
        value = 0
        for i in range(8):
            if GPIO.input(self.IO_pins[i]):
                value |= (1 << i)
        return value

    def _strobe_we(self):
        time.sleep(self.T_WC_S)
        GPIO.output(self.WE, GPIO.LOW)
        time.sleep(self.T_WC_S)
        GPIO.output(self.WE, GPIO.HIGH)
        time.sleep(self.T_WC_S)
        
    def _strobe_re(self):
        time.sleep(self.T_WC_S)
        GPIO.output(self.RE, GPIO.LOW)
        time.sleep(self.T_WC_S)
        val = self._read_from_bus()
        GPIO.output(self.RE, GPIO.HIGH)
        time.sleep(self.T_WC_S)
        return val

    def wait_ready(self, timeout_s=0.1):
        time.sleep(self.T_WB_S)
        start_time = time.time()
        while GPIO.input(self.RB) == GPIO.LOW:
            if time.time() - start_time > timeout_s:
                raise TimeoutError("NAND Flash가 Ready 상태로 전환되지 않았습니다 (타임아웃).")
        return

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
        addr_bytes = []
        addr_bytes.append(col_addr & 0xFF)
        addr_bytes.append((col_addr >> 8) & 0xFF)
        addr_bytes.append(page_no & 0xFF)
        addr_bytes.append((page_no >> 8) & 0xFF)
        addr_bytes.append((page_no >> 16) & 0xFF)
        return addr_bytes

    def power_on_sequence(self):
        try:
            GPIO.output(self.CE, GPIO.HIGH)
            time.sleep(0.001)
            GPIO.output(self.CE, GPIO.LOW)
            self.reset()
            print("NAND 칩 리셋 완료.")
        except Exception as e:
             raise RuntimeError(f"파워온 시퀀스 실패: {e}")

    def reset(self):
        self.send_command(0xFF)
        self.wait_ready()

    def read_id(self):
        GPIO.output(self.CE, GPIO.LOW)
        self.send_command(0x90)
        self.send_address([0x00])
        self.set_data_pins_input()
        id_bytes = [self._strobe_re() for _ in range(5)]
        self.set_data_pins_output()
        GPIO.output(self.CE, GPIO.HIGH)
        return bytes(id_bytes)

    def check_status(self):
        GPIO.output(self.CE, GPIO.LOW)
        self.send_command(0x70)
        self.set_data_pins_input()
        status = self._read_from_bus()
        self.set_data_pins_output()
        GPIO.output(self.CE, GPIO.HIGH)
        return status

    def mark_bad_block(self, block_no: int):
        """지정한 블록을 Bad Block 리스트에 추가합니다."""
        if block_no not in self.bad_blocks:
            self.bad_blocks.add(block_no)
            # 실제 NAND에 마킹하는 로직이 필요하다면 여기에 추가할 수 있습니다.
            # 예: 첫 페이지의 특정 위치에 0x00 같은 마커를 쓰는 작업
            print(f"블록 {block_no}이(가) 수동으로 Bad Block으로 마킹되었습니다.")

    def is_bad_block(self, block_no: int) -> bool:
        return block_no in self.bad_blocks

    def scan_bad_blocks(self):
        print("Bad Block 스캔 시작...")
        self.bad_blocks.clear()
        for block_no in range(self.TOTAL_BLOCKS):
            if block_no % 100 == 0:
                print(f"  스캔 진행 중: {block_no}/{self.TOTAL_BLOCKS}")
            page_no = block_no * self.PAGES_PER_BLOCK
            try:
                first_byte = self.read_page(page_no, length=1)[0]
                if first_byte != 0xFF:
                    self.bad_blocks.add(block_no)
                    print(f"  -> Bad Block 발견: 블록 {block_no} (마커: 0x{first_byte:02X})")
            except (IOError, TimeoutError, ValueError) as e:
                print(f"  -> 블록 {block_no} 읽기 실패. Bad Block으로 처리. 오류: {e}")
                self.bad_blocks.add(block_no)
        print(f"Bad Block 스캔 완료. 총 {len(self.bad_blocks)}개의 Bad Block을 찾았습니다.")

    def erase_block(self, block_no: int):
        """지정한 단일 블록을 삭제합니다."""
        if self.is_bad_block(block_no):
            # print(f"경고: Bad Block {block_no} 삭제 시도 건너뜀.")
            return
        page_no = block_no * self.PAGES_PER_BLOCK
        addr_bytes = self._build_address(page_no)[2:]
        try:
            GPIO.output(self.CE, GPIO.LOW)
            self.send_command(0x60)
            self.send_address(addr_bytes)
            self.send_command(0xD0)
            self.wait_ready(timeout_s=self.T_BERS_MAX_S * 1.2)
            status = self.check_status()
            if status & 0x01:
                print(f"블록 {block_no} 삭제 실패. Bad Block으로 마킹합니다.")
                self.bad_blocks.add(block_no)
                raise IOError(f"블록 {block_no} 삭제 실패.")
        finally:
            GPIO.output(self.CE, GPIO.HIGH)
            
    def erase_two_blocks(self, block_even: int, block_odd: int):
        """
        [최적화] 2-Plane Erase 기능을 사용하여 짝수 블록과 홀수 블록을 동시에 삭제합니다.
        """
        if block_even % 2 != 0 or block_odd % 2 == 0:
            raise ValueError("첫 번째 인자는 짝수 블록, 두 번째 인자는 홀수 블록이어야 합니다.")
        if self.is_bad_block(block_even) or self.is_bad_block(block_odd):
            # print(f"경고: Bad Block {block_even} 또는 {block_odd}이 포함되어 2-Plane 삭제를 건너뛰고 단일 삭제를 시도합니다.")
            if not self.is_bad_block(block_even): self.erase_block(block_even)
            if not self.is_bad_block(block_odd): self.erase_block(block_odd)
            return

        page_even = block_even * self.PAGES_PER_BLOCK
        addr_even = self._build_address(page_even)[2:]
        page_odd = block_odd * self.PAGES_PER_BLOCK
        addr_odd = self._build_address(page_odd)[2:]

        try:
            GPIO.output(self.CE, GPIO.LOW)
            # 1. 첫 번째 플레인(짝수 블록) 설정
            self.send_command(0x60)
            self.send_address(addr_even)
            self.send_command(0xD1)
            self.wait_ready(timeout_s=0.001) 

            # 2. 두 번째 플레인(홀수 블록) 설정 및 동시 삭제 시작
            self.send_command(0x60)
            self.send_address(addr_odd)
            self.send_command(0xD0)
            self.wait_ready(timeout_s=self.T_BERS_MAX_S * 1.2)
            
            status = self.check_status()
            if status & 0x01:
                print(f"2-Plane 블록 삭제 실패: ({block_even}, {block_odd}). Bad Block으로 마킹합니다.")
                self.bad_blocks.add(block_even)
                self.bad_blocks.add(block_odd)
                raise IOError(f"2-Plane 블록 삭제 실패: ({block_even}, {block_odd})")
        finally:
            GPIO.output(self.CE, GPIO.HIGH)

    def read_page(self, page_no: int, length: int = PAGE_SIZE):
        block_no = page_no // self.PAGES_PER_BLOCK
        if self.is_bad_block(block_no):
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
        block_no = page_no // self.PAGES_PER_BLOCK
        if self.is_bad_block(block_no):
            raise ValueError(f"Bad Block {block_no} 쓰기 시도.")
        if len(data) > self.PAGE_SIZE:
            raise ValueError(f"데이터 크기가 페이지 크기({self.PAGE_SIZE} bytes)를 초과합니다.")
        addr_bytes = self._build_address(page_no, 0)
        try:
            GPIO.output(self.CE, GPIO.LOW)
            self.send_command(0x80)
            self.send_address(addr_bytes)
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
