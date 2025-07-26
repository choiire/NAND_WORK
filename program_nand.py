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
    """파일 크기 유효성 검사 - 데이터시트 사양 준수"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"파일을 찾을 수 없음: {filepath}")
        
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValueError(f"파일이 비어있음: {filepath}")
        
    # 데이터시트 사양: 2048 bytes (main area) + 64 bytes (spare area)
    max_main_size = 2048  # 메인 영역 최대 크기
    max_total_size = 2048 + 64  # 메인 + 스페어 영역
    
    if file_size > max_total_size:
        raise ValueError(f"파일 크기가 너무 큼: {filepath} ({file_size} bytes > {max_total_size} bytes)")
        
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

def program_page_with_verification(nand, page_no: int, write_data: bytes, max_retries: int = 3) -> bool:
    """데이터시트 PROGRAM PAGE 사양에 따른 안전한 페이지 프로그래밍 (삭제 없음)"""
    block_no = page_no // 64
    
    # Bad Block 체크
    if nand.is_bad_block(block_no):
        raise RuntimeError(f"Bad Block에 쓰기 시도: 블록 {block_no}")
    
    for retry in range(max_retries):
        try:
            # 1. 페이지 쓰기 (데이터시트 PROGRAM PAGE 80h-10h 시퀀스)
            nand.write_page(page_no, write_data)
            
            # 2. tPROG 완전 대기 (데이터시트: 최대 600µs)
            time.sleep(0.001)  # 1ms 대기 (안전 마진 포함)
            
            # 3. 상태 확인 (Status Register)
            if not nand.check_operation_status():
                raise RuntimeError("페이지 쓰기 상태 확인 실패")
            
            # 4. Read-back 검증
            time.sleep(0.0001)  # 100µs 추가 대기
            read_data = nand.read_page(page_no, len(write_data))
            
            # 5. 데이터 무결성 검증
            if len(read_data) != len(write_data):
                raise ValueError(f"읽기 데이터 길이 불일치: {len(read_data)} != {len(write_data)}")
            
            # 6. 바이트별 비교
            mismatches = []
            for i, (w, r) in enumerate(zip(write_data, read_data)):
                if w != r:
                    mismatches.append({
                        'offset': i,
                        'written': w,
                        'read': r
                    })
                    if len(mismatches) >= 10:  # 최대 10개 불일치 기록
                        break
            
            if mismatches:
                error_details = "\n".join([
                    f"    오프셋 0x{m['offset']:04X}: 쓰기=0x{m['written']:02X}, 읽기=0x{m['read']:02X}"
                    for m in mismatches
                ])
                raise ValueError(f"데이터 검증 실패 ({len(mismatches)}개 불일치):\n{error_details}")
            
            # 성공
            return True
            
        except Exception as e:
            if retry == max_retries - 1:
                # 최종 실패 시 Bad Block으로 표시
                nand.mark_bad_block(block_no)
                raise RuntimeError(f"페이지 {page_no} 프로그래밍 최종 실패 (블록 {block_no}를 Bad Block으로 표시): {str(e)}")
            else:
                print(f"    재시도 {retry + 1}/{max_retries}: {str(e)}")
                time.sleep(0.01 * (retry + 1))  # 점진적 지연
    
    return False

def program_nand():
    try:
        # NAND 드라이버 초기화
        print("NAND 플래시 드라이버 초기화 중...")
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
        skipped_bad_blocks = []
        MAX_RETRIES = 3  # 데이터시트 권장사항에 따라 감소
        
        start_datetime = datetime.now()
        error_log_filename = f"program_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        
        print(f"\n=== NAND 플래시 프로그래밍 시작 ===")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 파일 수: {total_files}개")
        print(f"Bad Block 수: {len(nand.bad_blocks)}개")
        print(f"오류 로그: {error_log_filename}")
        print("=" * 50)
        
        # 작업 시간 추적을 위한 변수들
        last_update_time = time.time()
        files_since_update = 0
        avg_time_per_file = None
        
        for file_index, filename in enumerate(files):
            try:
                # 파일 검증
                filepath = os.path.join(splits_dir, filename)
                file_size = validate_file_size(filepath)
                
                # 주소 및 페이지 계산
                address = hex_to_int(filename.split('.')[0])
                page_no = calculate_page_number(address)
                block_no = page_no // 64
                
                # Bad Block 체크 및 스킵
                if nand.is_bad_block(block_no):
                    skipped_bad_blocks.append({
                        'file': filename,
                        'block': block_no,
                        'page': page_no
                    })
                    print(f"Bad Block 스킵: 파일 '{filename}' (블록 {block_no})")
                    continue
                
                # 데이터 읽기
                with open(filepath, 'rb') as f:
                    write_data = f.read()
                
                # 프로그래밍 시도
                try:
                    success = program_page_with_verification(nand, page_no, write_data, MAX_RETRIES)
                    
                    if success:
                        processed_files += 1
                        files_since_update += 1
                        
                        # 진행률 및 예상 시간 업데이트 (1초마다)
                        current_time = time.time()
                        if current_time - last_update_time >= 1.0:
                            # 평균 처리 시간 계산
                            time_per_batch = (current_time - last_update_time) / files_since_update
                            if avg_time_per_file is None:
                                avg_time_per_file = time_per_batch
                            else:
                                avg_time_per_file = (avg_time_per_file * 0.8) + (time_per_batch * 0.2)
                            
                            # 남은 시간 계산
                            remaining_files = total_files - file_index - 1
                            remaining_seconds = remaining_files * avg_time_per_file
                            remaining_minutes = int(remaining_seconds / 60)
                            
                            # 진행률 표시
                            progress = ((file_index + 1) / total_files) * 100
                            sys.stdout.write("\033[K")  # 현재 줄 지우기
                            sys.stdout.write(f"\r진행률: {progress:.1f}% ({file_index + 1}/{total_files}) - "
                                           f"성공: {processed_files}, 실패: {len(failed_files)}, "
                                           f"Bad Block 스킵: {len(skipped_bad_blocks)} - "
                                           f"예상 남은 시간: {remaining_minutes}분")
                            sys.stdout.flush()
                            
                            # 업데이트 변수 초기화
                            last_update_time = current_time
                            files_since_update = 0
                    
                except Exception as e:
                    error_msg = f"파일 '{filename}' 프로그래밍 실패:\n"
                    error_msg += f"  주소: 0x{address:08X}\n"
                    error_msg += f"  페이지: {page_no} (블록 {block_no})\n"
                    error_msg += f"  파일 크기: {file_size} bytes\n"
                    error_msg += f"  오류: {str(e)}"
                    
                    # 오류 로그 기록
                    with open(error_log_filename, 'a', encoding='utf-8') as f:
                        f.write(f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                        f.write(error_msg + "\n")
                    
                    failed_files.append({
                        'file': filename,
                        'address': address,
                        'page': page_no,
                        'block': block_no,
                        'error': str(e)
                    })
                    
                    print(f"\n{error_msg}")
                
            except Exception as e:
                error_msg = f"파일 '{filename}' 처리 중 오류:\n"
                error_msg += f"  오류: {str(e)}"
                
                with open(error_log_filename, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.write(error_msg + "\n")
                
                failed_files.append({
                    'file': filename,
                    'error': str(e)
                })
                
                print(f"\n{error_msg}")
        
        # 최종 결과 출력
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        
        print(f"\n\n{'='*60}")
        print(f"=== NAND 플래시 프로그래밍 완료 ===")
        print(f"{'='*60}")
        print(f"완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요 시간: {duration}")
        print(f"총 파일 수: {total_files}")
        print(f"성공: {processed_files}")
        print(f"실패: {len(failed_files)}")
        print(f"Bad Block 스킵: {len(skipped_bad_blocks)}")
        print(f"성공률: {(processed_files/total_files)*100:.2f}%")
        
        if skipped_bad_blocks:
            print(f"\n[Bad Block 스킵 목록]")
            for skip in skipped_bad_blocks[:10]:  # 최대 10개만 표시
                print(f"  블록 {skip['block']}: {skip['file']}")
            if len(skipped_bad_blocks) > 10:
                print(f"  ... 및 {len(skipped_bad_blocks) - 10}개 더")
        
        if failed_files:
            print(f"\n[실패 파일 목록]")
            for fail in failed_files[:5]:  # 최대 5개만 표시
                print(f"  {fail['file']}: {fail.get('error', 'Unknown error')}")
            if len(failed_files) > 5:
                print(f"  ... 및 {len(failed_files) - 5}개 더")
            print(f"\n자세한 오류 내역: {error_log_filename}")
        
        print("=" * 60)
        
        return len(failed_files) == 0
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    success = program_nand()
    sys.exit(0 if success else 1) 