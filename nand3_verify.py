import os
import sys
import time
import hashlib
from datetime import datetime
from nand_driver import MT29F8G08ADADA

def calculate_file_hash(filepath: str) -> str:
    """파일의 SHA256 해시를 계산합니다."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def verify_nand_sequential(input_filepath: str):
    """
    NAND 데이터를 순차적으로 읽어 파일로 저장한 뒤, 원본과 비교 검증합니다.
    (Bad Block도 읽기 시도)
    """
    output_filepath = "output.bin"
    MAX_RETRIES = 5  # 최대 재시도 횟수
    RETRY_DELAY = 1    # 재시도 간 대기 시간 (초)
    
    try:
        print("NAND 드라이버 초기화 중 (공장 Bad Block 스캔)...")
        nand = MT29F8G08ADADA()
        
        # 1. 입력 파일 유효성 검사
        if not os.path.exists(input_filepath):
            raise FileNotFoundError(f"입력 파일 없음: {input_filepath}")
        
        expected_size = os.path.getsize(input_filepath)
        total_blocks_to_process = expected_size // (nand.PAGE_SIZE * nand.PAGES_PER_BLOCK)
        
        # 2. output.bin 파일이 있다면 삭제
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
            
        print(f"\n파일 '{input_filepath}'와 NAND 칩의 첫 {total_blocks_to_process}개 블록을 비교합니다.")
        print("경고: Bad Block으로 표시된 블록도 강제로 읽기를 시도합니다.")
        start_time = datetime.now()
        
        # 3. 블록 단위로 NAND 읽기 -> output.bin에 쓰기
        with open(output_filepath, 'ab') as f_out:
            for block in range(total_blocks_to_process):
                sys.stdout.write(f"\r블록 처리 중: {block + 1}/{total_blocks_to_process}")
                sys.stdout.flush()

                # [수정] Bad Block 건너뛰기 로직 삭제
                if nand.is_bad_block(block):
                    print(f"\n정보: 블록 {block}은 Bad Block입니다. 데이터 읽기를 시도합니다.")

                # 정상 블록과 동일하게 페이지 단위로 순차 읽기 시도
                # 페이지 단위로 순차 읽기
                for page_offset in range(nand.PAGES_PER_BLOCK):
                    page_no = block * nand.PAGES_PER_BLOCK + page_offset
                    
                    # [수정] 페이지 읽기 재시도 루프 추가
                    read_success = False
                    for attempt in range(MAX_RETRIES):
                        try:
                            page_data = nand.read_page(page_no)
                            f_out.write(page_data)
                            read_success = True
                            break # 성공 시 재시도 루프 탈출
                        except Exception as e:
                            print(f"\n경고: 페이지 {page_no} 읽기 실패 (시도 {attempt + 1}/{MAX_RETRIES}). {RETRY_DELAY}초 후 재시도... 오류: {e}")
                            time.sleep(RETRY_DELAY)
                    
                    if not read_success:
                        print(f"\n오류: 페이지 {page_no} 최종 읽기 실패. 0xFF로 채웁니다.")
                        f_out.write(b'\xFF' * nand.PAGE_SIZE)


        read_duration = datetime.now() - start_time
        print(f"\n\nNAND 데이터 읽기 및 파일 저장 완료. (소요 시간: {read_duration})")

        # 4. 최종 검증 (크기 및 해시 비교) - 기존과 동일
        print("\n최종 파일 검증 시작...")
        
        print("입력 파일 해시 계산 중...")
        expected_hash = calculate_file_hash(input_filepath)
        
        print("출력 파일 해시 계산 중...")
        actual_size = os.path.getsize(output_filepath)
        actual_hash = calculate_file_hash(output_filepath)
        
        print("\n--- 검증 결과 ---")
        print(f"예상 크기 : {expected_size} Bytes")
        print(f"실제 크기 : {actual_size} Bytes")
        print(f"예상 해시 : {expected_hash}")
        print(f"실제 해시 : {actual_hash}")
        
        if actual_size == expected_size and actual_hash == expected_hash:
            print("\n[성공] 데이터가 완벽하게 일치합니다! 🎉")
            return True
        else:
            print("\n[실패] 데이터가 일치하지 않습니다!")
            return False

    except Exception as e:
        print(f"\n치명적 오류 발생: {e}")
        return False

if __name__ == "__main__":
    input_file = "input.bin"
    verify_nand_sequential(input_file)