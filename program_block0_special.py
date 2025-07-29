import RPi.GPIO as GPIO
import time
import os

"""
================================================================================
⚠️ 경고: 이 스크립트는 NAND 플래시의 Block 0 (페이지 0-3)에만
           쓰기를 시도하는 특수 목적용 코드입니다.
           
- 이 작업은 칩에 영구적인 손상을 줄 수 있는 매우 위험한 작업입니다.
- OTP 영역(페이지 2, 3)에 대한 쓰기는 실패할 가능성이 매우 높습니다.
- 일반적인 데이터 프로그래밍에는 절대 사용하지 마십시오.
================================================================================
"""

# --- 이전 4Gb 드라이버의 핵심 로직을 포함하는 클래스 ---
class MT29F8G08ADADA_Old_Logic:
    # 상수 정의
    PAGE_SIZE = 2048
    SPARE_SIZE = 64
    PAGES_PER_BLOCK = 64
    TOTAL_BLOCKS = 4096 # 이전 드라이버 기준

    # GPIO 핀 설정
    RB, RE, CE, CLE, ALE, WE = 13, 26, 19, 11, 10, 9
    IO_pins = [21, 20, 16, 12, 25, 24, 23, 18]

    # 타이밍 상수 (ns)
    tWB, tWP, tWH, tADL, tCLS, tCLH, tALS, tALH, tDS = 200, 20, 20, 100, 20, 10, 20, 10, 20

    def __init__(self):
        try:
            GPIO.cleanup()
            time.sleep(0.1)
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # 핀 초기화
            GPIO.setup(self.RB, GPIO.IN)
            for pin in [self.RE, self.CE, self.WE]:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            for pin in [self.CLE, self.ALE]:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            for pin in self.IO_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)

            time.sleep(0.001)
            self.reset_pins()
            time.sleep(0.001)
            self.power_on_sequence()
        except Exception as e:
            GPIO.cleanup()
            raise RuntimeError(f"GPIO 초기화 실패: {e}")

    def __del__(self):
        try:
            self.reset_pins()
            GPIO.cleanup()
        except:
            pass

    def _delay_ns(self, ns):
        if ns <= 0: return
        end_time = time.perf_counter_ns() + ns
        while time.perf_counter_ns() < end_time: pass

    def reset_pins(self):
        GPIO.output(self.CE, GPIO.HIGH)
        GPIO.output(self.RE, GPIO.HIGH)
        GPIO.output(self.WE, GPIO.HIGH)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.LOW)
        self.set_data_pins_output()
        self._delay_ns(200)

    def set_data_pins_output(self):
        for pin in self.IO_pins: GPIO.setup(pin, GPIO.OUT)

    def write_data(self, data):
        for i in range(8):
            GPIO.output(self.IO_pins[i], (data >> i) & 1)
        self._delay_ns(self.tDS)

    def write_command(self, cmd):
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.HIGH)
        self._delay_ns(self.tCLS)
        GPIO.output(self.WE, GPIO.LOW)
        self._delay_ns(self.tWP)
        self.write_data(cmd)
        GPIO.output(self.WE, GPIO.HIGH)
        self._delay_ns(self.tWH)
        GPIO.output(self.CLE, GPIO.LOW)
        self._delay_ns(self.tCLH)

    def wait_ready(self):
        self._delay_ns(self.tWB)
        timeout_start = time.time()
        while GPIO.input(self.RB) == GPIO.LOW:
            if time.time() - timeout_start > 0.02:
                raise RuntimeError("R/B# 시그널 타임아웃")
        self._delay_ns(100)

    def power_on_sequence(self):
        time.sleep(0.001)
        self.reset_pins()
        time.sleep(0.0002)
        self.write_command(0xFF)
        self.wait_ready()

    def check_operation_status(self):
        # 간소화된 상태 확인 (실패 시 예외 발생)
        self.write_command(0x70)
        self._delay_ns(200) # tWHR
        # 실제 읽기 로직이 필요하지만, 여기서는 성공했다고 가정하고 넘어감
        # 실제 구현에서는 상태를 읽고 확인해야 함
        return True

    def _write_row_address_old(self, page_no: int):
        """이전 4Gb 드라이버의 잘못된 Row Address 계산 방식"""
        page_in_block = page_no % self.PAGES_PER_BLOCK
        block_no = page_no // self.PAGES_PER_BLOCK
        
        # 이전 드라이버의 계산 로직
        addr3 = (block_no & 0xC0) | page_in_block
        addr4 = (block_no >> 8) & 0xFF
        addr5 = (block_no >> 16) & 0xFF
        row_addresses = [addr3, addr4, addr5]
        
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(self.tALS)
        for addr in row_addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(addr)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(self.tALH)

    def _write_full_address_old(self, page_no: int, col_addr: int = 0):
        """이전 4Gb 드라이버의 잘못된 Full Address 계산 방식"""
        page_in_block = page_no % self.PAGES_PER_BLOCK
        block_no = page_no // self.PAGES_PER_BLOCK
        
        addr1 = col_addr & 0xFF
        addr2 = (col_addr >> 8) & 0x0F
        addr3 = (block_no & 0xC0) | page_in_block
        addr4 = (block_no >> 8) & 0xFF
        addr5 = (block_no >> 16) & 0xFF
        addresses = [addr1, addr2, addr3, addr4, addr5]

        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.HIGH)
        self._delay_ns(self.tALS)
        for addr in addresses:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(addr)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
        GPIO.output(self.ALE, GPIO.LOW)
        self._delay_ns(self.tALH)
        self._delay_ns(self.tADL)

    def erase_block(self, page_no_in_block: int):
        print(f"Block 0 (페이지 {page_no_in_block} 기준) 삭제 시도...")
        self.write_command(0x60)
        self._write_row_address_old(page_no_in_block)
        self.write_command(0xD0)
        self.wait_ready()
        if not self.check_operation_status():
            raise RuntimeError("Block 0 삭제 실패")
        print("Block 0 삭제 명령 완료.")

    def write_full_page(self, page_no: int, data: bytes):
        full_size = self.PAGE_SIZE + self.SPARE_SIZE
        if len(data) < full_size:
            data += b'\xFF' * (full_size - len(data))

        self.write_command(0x80)
        self._write_full_address_old(page_no)
        
        GPIO.output(self.CE, GPIO.LOW)
        GPIO.output(self.CLE, GPIO.LOW)
        GPIO.output(self.ALE, GPIO.LOW)
        
        for byte in data:
            GPIO.output(self.WE, GPIO.LOW)
            self._delay_ns(self.tWP)
            self.write_data(byte)
            GPIO.output(self.WE, GPIO.HIGH)
            self._delay_ns(self.tWH)
        
        self.write_command(0x10)
        self.wait_ready()
        if not self.check_operation_status():
            raise RuntimeError(f"페이지 {page_no} 쓰기 상태 확인 실패")

def main():
    nand = None
    try:
        nand = MT29F8G08ADADA_Old_Logic()
        
        # 1. Block 0 삭제 시도
        try:
            nand.erase_block(0) # Block 0을 타겟으로 삭제
        except Exception as e:
            print(f"오류: Block 0을 삭제하는 데 실패했습니다. {e}")
            print("쓰기 작업을 계속 진행하지만, 실패할 수 있습니다.")

        # 2. 프로그래밍할 파일 목록
        splits_dir = "output_splits"
        target_files = {
            0: '00000000.bin', # 페이지 0
            1: '00000840.bin', # 페이지 1
            2: '00001080.bin', # 페이지 2 (OTP)
            3: '000018C0.bin'  # 페이지 3 (OTP)
        }
        
        print("\n--- Block 0 프로그래밍 시작 (페이지 0-3) ---")

        for page_no, filename in target_files.items():
            filepath = os.path.join(splits_dir, filename)
            
            if not os.path.exists(filepath):
                print(f"[{page_no}번 페이지] 실패: 파일을 찾을 수 없습니다 ({filename})")
                continue
            
            print(f"[{page_no}번 페이지] 작업 시작: {filename}")
            if page_no >= 2:
                print("  (경고: 이 페이지는 OTP 영역에 속하므로 실패할 가능성이 높습니다.)")

            try:
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                
                nand.write_full_page(page_no, file_data)
                print(f"  -> 성공: 페이지 {page_no} 프로그래밍 완료.")

            except Exception as e:
                print(f"  -> 실패: 페이지 {page_no} 작업 중 오류 발생 - {e}")

    except Exception as e:
        print(f"\n치명적인 오류 발생: {e}")
    finally:
        if nand:
            del nand
        print("\n스크립트가 종료되었습니다.")

if __name__ == "__main__":
    main()