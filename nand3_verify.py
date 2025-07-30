import os
import sys
import time
import hashlib
import pickle
from datetime import datetime
from nand_driver import MT29F4G08ADADA

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
    pickle_filepath = "nand_data.pkl"
    MAX_RETRIES = 5  # 최대 재시도 횟수
    RETRY_DELAY = 1    # 재시도 간 대기 시간 (초)
    
    try:
        print("NAND 드라이버 초기화 중 (공장 Bad Block 스캔)...")
        nand = MT29F4G08ADADA()
        
        # 1. 입력 파일 유효성 검사
        if not os.path.exists(input_filepath):
            raise FileNotFoundError(f"입력 파일 없음: {input_filepath}")
        
        expected_size = os.path.getsize(input_filepath)
        total_blocks_to_process = nand.TOTAL_BLOCKS
        
        # 2. 기존 파일들 삭제
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        if os.path.exists(pickle_filepath):
            os.remove(pickle_filepath)
            
        print(f"\n파일 '{input_filepath}'와 NAND 칩의 첫 {total_blocks_to_process}개 블록을 비교합니다.")
        print("경고: Bad Block으로 표시된 블록도 강제로 읽기를 시도합니다.")
        start_time = datetime.now()
        
        # 3. 블록 단위로 NAND 읽기 -> 실시간 pickle 저장
        for block in range(total_blocks_to_process):
            # 진행률 및 예상 완료 시간 계산
            current_time = datetime.now()
            elapsed_time = current_time - start_time
            progress = (block + 1) / total_blocks_to_process
            
            if progress > 0:
                estimated_total_time = elapsed_time / progress
                remaining_time = estimated_total_time - elapsed_time
                
                # 남은 시간을 시:분:초 형태로 변환
                remaining_seconds = int(remaining_time.total_seconds())
                hours, remainder = divmod(remaining_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if hours > 0:
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    time_str = f"{minutes:02d}:{seconds:02d}"
                
                sys.stdout.write(f"\r블록 처리 중: {block + 1}/{total_blocks_to_process} ({progress*100:.1f}%) - 남은 시간: {time_str}")
            else:
                sys.stdout.write(f"\r블록 처리 중: {block + 1}/{total_blocks_to_process}")
            sys.stdout.flush()

            # [수정] Bad Block 건너뛰기 로직 삭제
            if nand.is_bad_block(block):
                print(f"\n정보: 블록 {block}은 Bad Block입니다. 데이터 읽기를 시도합니다.")

            # 현재 블록의 페이지 데이터를 저장할 리스트
            block_pages = []
            
            # 정상 블록과 동일하게 페이지 단위로 순차 읽기 시도
            # 페이지 단위로 순차 읽기
            for page_offset in range(nand.PAGES_PER_BLOCK):
                page_no = block * nand.PAGES_PER_BLOCK + page_offset
                
                # [수정] 페이지 읽기 재시도 루프 추가
                read_success = False
                for attempt in range(MAX_RETRIES):
                    try:
                        page_data = nand.read_page(page_no, nand.PAGE_SIZE + nand.SPARE_SIZE)
                        block_pages.append(page_data)
                        read_success = True
                        break # 성공 시 재시도 루프 탈출
                    except Exception as e:
                        print(f"\n경고: 페이지 {page_no} 읽기 실패 (시도 {attempt + 1}/{MAX_RETRIES}). {RETRY_DELAY}초 후 재시도... 오류: {e}")
                        time.sleep(RETRY_DELAY)
                
                if not read_success:
                    print(f"\n오류: 페이지 {page_no} 최종 읽기 실패. 0xFF로 채웁니다.")
                    block_pages.append(b'\xFF' * (nand.PAGE_SIZE + nand.SPARE_SIZE))

            # 현재 블록의 모든 페이지 데이터를 pickle 파일에 추가 저장
            if block == 0:
                # 첫 번째 블록일 때는 새로 생성
                with open(pickle_filepath, 'wb') as f_pickle:
                    pickle.dump(block_pages, f_pickle)
            else:
                # 이후 블록들은 기존 데이터에 추가
                # 기존 데이터 로드
                with open(pickle_filepath, 'rb') as f_pickle:
                    existing_data = pickle.load(f_pickle)
                
                # 새 블록 데이터 추가
                existing_data.extend(block_pages)
                
                # 다시 저장
                with open(pickle_filepath, 'wb') as f_pickle:
                    pickle.dump(existing_data, f_pickle)

        read_duration = datetime.now() - start_time
        print(f"\n\nNAND 데이터 읽기 및 pickle 저장 완료. (소요 시간: {read_duration})")

        # 4. pickle 파일을 bin 파일로 변환
        print("pickle 파일을 bin 파일로 변환 중...")
        with open(pickle_filepath, 'rb') as f_pickle:
            all_page_data = pickle.load(f_pickle)
        
        with open(output_filepath, 'wb') as f_out:
            for page_data in all_page_data:
                f_out.write(page_data)

        # 5. 최종 검증 (크기 및 해시 비교) - 기존과 동일
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