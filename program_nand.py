import os
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP
import time # Added for time.time() and time.sleep()

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ValueError(f"잘못된 파일명 형식: {hex_str}")

def validate_block_number(block_no: int) -> bool:
    """블록 번호 유효성 검사"""
    return 0 <= block_no < 4096  # 4Gb = 4096 blocks

def validate_file_size(filepath: str) -> int:
    """파일 크기 유효성 검사"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"파일을 찾을 수 없음: {filepath}")
        
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValueError(f"파일이 비어있음: {filepath}")
        
    # ECC 오버헤드를 고려한 최대 크기 계산
    max_size = 2048 + 64 + ((2048 // 256) * 32)  # 데이터 + 스페어 + ECC
    if file_size > max_size:
        raise ValueError(f"파일 크기가 너무 큼: {filepath} ({file_size} bytes)")
        
    return file_size

def calculate_block_number(address: int) -> int:
    """주소를 블록 번호로 변환"""
    # NAND 플래시 전체 크기로 마스킹 (4Gb = 512MB = 0x20000000)
    NAND_SIZE_MASK = 0x1FFFFFFF
    masked_address = address & NAND_SIZE_MASK
    
    # 블록 크기 = 페이지 크기(0x800 = 2KB) * 페이지 수(64)
    block_no = masked_address // (0x800 * 64)
    if not validate_block_number(block_no):
        raise ValueError(
            f"주소 0x{address:08X}(마스킹 후: 0x{masked_address:08X})에서 "
            f"계산된 블록 번호({block_no})가 유효하지 않습니다"
        )
    return block_no

def calculate_page_number(address: int) -> int:
    """주소를 페이지 번호로 변환"""
    # NAND 플래시 전체 크기로 마스킹
    NAND_SIZE_MASK = 0x1FFFFFFF
    masked_address = address & NAND_SIZE_MASK
    
    # 페이지 번호 계산 (2KB = 0x800 단위)
    page_no = masked_address // 0x800
    if page_no >= 256 * 1024:  # 4Gb = 256K 페이지
        raise ValueError(f"유효하지 않은 페이지 번호: {page_no}")
    return page_no

def validate_directory(dirpath: str) -> None:
    """디렉토리 유효성 검사"""
    if not os.path.exists(dirpath):
        raise NotADirectoryError(f"디렉토리를 찾을 수 없음: {dirpath}")
    if not os.path.isdir(dirpath):
        raise NotADirectoryError(f"유효한 디렉토리가 아님: {dirpath}")

def program_nand():
    try:
        # NAND 드라이버 초기화
        nand = MT29F4G08ABADAWP()
        
        # output_splits 디렉토리 검증
        splits_dir = "output_splits"
        validate_directory(splits_dir)
        
        # 파일 목록 가져오기 및 정렬
        files = [f for f in os.listdir(splits_dir) if f.endswith('.bin')]
        if not files:
            raise ValueError(f"프로그래밍할 파일이 없음: {splits_dir}")
        files.sort()
        
        total_files = len(files)
        processed_files = 0
        failed_files = []
        MAX_RETRIES = 5
        TIMEOUT_SECONDS = 5
        
        start_datetime = datetime.now()
        error_log_filename = f"program_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        
        print(f"\n=== 프로그래밍 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {total_files}개 파일 프로그래밍 예정")
        print(f"오류 로그 파일: {error_log_filename}")
        
        # 초기 진행률 표시
        sys.stdout.write("\033[K")  # 현재 줄 지우기
        sys.stdout.write("\r진행률: 0% (0/{total_files}) - 예상 남은 시간: 계산 중...")
        sys.stdout.flush()
        
        # 작업 시간 추적을 위한 변수들
        last_update_time = time.time()
        files_since_update = 0
        avg_time_per_file = None
        
        for filename in files:
            try:
                # 파일 검증
                filepath = os.path.join(splits_dir, filename)
                validate_file_size(filepath)
                
                # 주소 계산
                address = hex_to_int(filename.split('.')[0])
                page_no = calculate_page_number(address)
                block_no = page_no // 64
                
                # 데이터 읽기
                with open(filepath, 'rb') as f:
                    write_data = f.read()
                
                # 최대 5번 재시도
                success = False
                for retry in range(MAX_RETRIES):
                    try:
                        timeout_start = time.time()
                        while True:
                            try:
                                # 1. 페이지 쓰기
                                nand.write_page(page_no, write_data)
                                
                                # 2. 데이터 정착 대기
                                time.sleep(0.001)  # 1ms 대기
                                
                                # 3. 검증
                                read_data = nand.read_page(page_no)
                                
                                # 4. 데이터 비교
                                if read_data != write_data:
                                    # 불일치하는 바이트 위치와 값 찾기
                                    mismatch_positions = []
                                    for i, (w, r) in enumerate(zip(write_data, read_data)):
                                        if w != r:
                                            mismatch_positions.append({
                                                'offset': i,
                                                'written': w,
                                                'read': r
                                            })
                                            if len(mismatch_positions) >= 5:  # 최대 5개까지만 기록
                                                break
                                    
                                    error_msg = (
                                        f"데이터 검증 실패:\n" + 
                                        "\n".join([
                                            f"  오프셋 0x{m['offset']:04X}: "
                                            f"쓰기 0x{m['written']:02X} != "
                                            f"읽기 0x{m['read']:02X}"
                                            for m in mismatch_positions
                                        ])
                                    )
                                    raise ValueError(error_msg)
                                
                                success = True
                                break
                                
                            except Exception as e:
                                if time.time() - timeout_start > TIMEOUT_SECONDS:
                                    raise TimeoutError("페이지 프로그래밍/검증 타임아웃")
                                time.sleep(0.1)
                        break
                        
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            error_msg = f"\n파일 '{filename}' 프로그래밍/검증 실패 (최대 재시도 횟수 초과):\n"
                            error_msg += f"주소: 0x{address:08X}\n"
                            error_msg += f"페이지: {page_no} (블록 {block_no})\n"
                            error_msg += f"오류: {str(e)}"
                            
                            # 오류를 파일에 즉시 기록
                            with open(error_log_filename, 'a', encoding='utf-8') as f:
                                f.write(f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                                f.write(error_msg + "\n")
                            
                            failed_files.append({
                                'file': filename,
                                'error': str(e)
                            })
                            print(f"\n{error_msg}")
                        else:
                            print(f"\n파일 '{filename}' 프로그래밍/검증 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.5)  # 재시도 간격 증가
                
                if success:
                    processed_files += 1
                    files_since_update += 1
                    
                    # 진행률 및 예상 시간 업데이트 (1초에 한 번만)
                    current_time = time.time()
                    if current_time - last_update_time >= 1.0:
                        # 평균 처리 시간 계산
                        time_per_batch = (current_time - last_update_time) / files_since_update
                        if avg_time_per_file is None:
                            avg_time_per_file = time_per_batch
                        else:
                            avg_time_per_file = (avg_time_per_file * 0.7) + (time_per_batch * 0.3)
                        
                        # 남은 시간 계산
                        remaining_files = total_files - processed_files
                        remaining_seconds = remaining_files * avg_time_per_file
                        remaining_minutes = int(remaining_seconds / 60)
                        
                        # 진행률 표시 업데이트
                        progress = (processed_files / total_files) * 100
                        sys.stdout.write("\033[K")  # 현재 줄 지우기
                        sys.stdout.write(f"\r진행률: {progress:.1f}% ({processed_files}/{total_files}) - "
                                       f"예상 남은 시간: {remaining_minutes}분")
                        sys.stdout.flush()
                        
                        # 업데이트 관련 변수 초기화
                        last_update_time = current_time
                        files_since_update = 0
                
            except Exception as e:
                error_msg = f"\n파일 '{filename}' 프로그래밍 중 오류 발생:\n"
                error_msg += f"주소: 0x{address:08X}\n"
                error_msg += f"페이지: {page_no} (블록 {block_no})\n"
                error_msg += f"오류: {str(e)}"
                
                # 오류를 파일에 즉시 기록
                with open(error_log_filename, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.write(error_msg + "\n")
                
                failed_files.append({
                    'file': filename,
                    'error': str(e)
                })
                print(f"\n{error_msg}")
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        print(f"\n\n=== 프로그래밍 완료 (소요 시간: {duration}) ===")
        
        if not failed_files:
            print("결과: 모든 파일이 성공적으로 프로그래밍됨")
            return True
        else:
            print(f"결과: {len(failed_files)}개 파일에서 문제 발생")
            print(f"자세한 오류 내역은 {error_log_filename} 파일을 참고하세요.")
            return False
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    program_nand() 