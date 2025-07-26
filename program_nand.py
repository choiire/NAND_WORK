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

def verify_block(nand, block_no: int) -> dict:
    """단일 블록 검증"""
    PAGES_PER_BLOCK = 64
    block_start_page = block_no * PAGES_PER_BLOCK
    MAX_RETRIES = 5
    TIMEOUT_SECONDS = 5
    
    errors = []
    page_no = block_start_page  # 첫 페이지만 검사
    
    # 페이지 읽기 재시도 로직
    read_success = False
    for retry in range(MAX_RETRIES):
        timeout_start = time.time()
        timeout_occurred = False
        
        while True:
            try:
                data = nand.read_page(page_no)
                read_success = True
                break
            except Exception as e:
                if time.time() - timeout_start > TIMEOUT_SECONDS:
                    timeout_occurred = True
                    break
                time.sleep(0.1)
        
        if read_success:
            break
            
        if timeout_occurred:
            if retry == MAX_RETRIES - 1:
                return {
                    'success': False,
                    'error': f"페이지 {page_no} 읽기 실패 (최대 재시도 횟수 초과): 타임아웃"
                }
            print(f"\n페이지 {page_no} 읽기 타임아웃, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
            time.sleep(0.5)  # 다음 재시도 전 잠시 대기
    
    if not read_success:
        return {
            'success': False,
            'error': "읽기 실패"
        }
    
    # FF 값 검증
    if not all(b == 0xFF for b in data):
        # 오류가 있는 경우 첫 번째 오류 위치와 값 기록
        for offset, value in enumerate(data):
            if value != 0xFF:
                errors.append({
                    'page': page_no,
                    'offset': offset,
                    'value': value
                })
                break  # 첫 번째 오류만 기록
    
    return {
        'success': len(errors) == 0,
        'errors': errors
    }

def erase_all_blocks(nand):
    """전체 블록 삭제 (Bad Block 포함)"""
    TOTAL_BLOCKS = 4096  # 4Gb = 4096 blocks
    PAGES_PER_BLOCK = 64
    MAX_RETRIES = 5  # 블록 삭제 최대 재시도 횟수
    CHUNK_SIZE = 10  # 한 번에 처리할 블록 수
    
    start_datetime = datetime.now()
    print(f"\n=== 전체 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {TOTAL_BLOCKS}개 블록 삭제 예정 (Bad Block 포함)")
    
    errors = []
    processed_blocks = 0
    
    try:
        # 청크 단위로 처리
        for chunk_start in range(0, TOTAL_BLOCKS, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, TOTAL_BLOCKS)
            chunk_blocks = chunk_end - chunk_start
            
            for block_offset in range(chunk_blocks):
                block = chunk_start + block_offset
                page_no = block * PAGES_PER_BLOCK
                
                # 1. 블록 삭제 (최대 5번 재시도)
                erase_success = False
                for retry in range(MAX_RETRIES):
                    try:
                        timeout_start = time.time()
                        timeout_occurred = False
                        
                        while True:
                            try:
                                nand.erase_block(page_no)
                                erase_success = True
                                break
                            except Exception as e:
                                if time.time() - timeout_start > 5:  # 5초 타임아웃
                                    timeout_occurred = True
                                    break
                                time.sleep(0.1)
                        
                        if erase_success:
                            break
                            
                        if timeout_occurred:
                            raise TimeoutError("블록 삭제 타임아웃")
                            
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n블록 {block} 삭제 실패 (최대 재시도 횟수 초과): {str(e)}")
                            errors.append({
                                'block': block,
                                'error': f"삭제 실패: {str(e)}"
                            })
                        else:
                            print(f"\n블록 {block} 삭제 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.5)  # 0.5초 대기 후 재시도
                
                if not erase_success:
                    continue
                
                # 2. 블록 검증
                verify_result = verify_block(nand, block)
                if not verify_result['success']:
                    if 'error' in verify_result:
                        print(f"\n블록 {block} 검증 실패: {verify_result['error']}")
                    else:
                        print(f"\n블록 {block} 검증 실패: 초기화 오류")
                    errors.append({
                        'block': block,
                        'errors': verify_result.get('errors', [])
                    })
                
                processed_blocks += 1
                if processed_blocks % 10 == 0:
                    sys.stdout.write(f"\r작업 중: {processed_blocks}/{TOTAL_BLOCKS} 블록")
                    sys.stdout.flush()
        
        # 결과 출력
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        print(f"\n\n=== 작업 완료 (소요 시간: {duration}) ===")
        
        if not errors:
            print("결과: 모든 블록이 성공적으로 초기화됨 (FF)")
            return True
        else:
            print(f"결과: {len(errors)}개 블록에서 문제 발생")
            
            # 오류 로그 파일 저장
            log_filename = f"erase_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(f"=== NAND 블록 삭제 오류 로그 ===\n")
                f.write(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"종료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"소요 시간: {duration}\n")
                f.write(f"총 오류 블록 수: {len(errors)}\n\n")
                
                for error in errors:
                    f.write(f"\n블록 {error['block']}:\n")
                    if 'error' in error:
                        f.write(f"  {error['error']}\n")
                    else:
                        for page_error in error['errors']:
                            f.write(f"  페이지 {page_error['page']}:\n")
                            f.write(f"    오프셋 0x{page_error['offset']:04X}에서 "
                                  f"0x{page_error['value']:02X} 발견 (예상: 0xFF)\n")
            
            print(f"\n오류 상세 내역이 {log_filename} 파일에 저장되었습니다.")
            
            # 처음 5개의 오류만 화면에 출력
            for error in errors[:5]:
                print(f"\n블록 {error['block']}:")
                if 'error' in error:
                    print(f"  {error['error']}")
                else:
                    for page_error in error['errors']:
                        print(f"  페이지 {page_error['page']}:")
                        print(f"    오프셋 0x{page_error['offset']:04X}에서 "
                              f"0x{page_error['value']:02X} 발견 (예상: 0xFF)")
            
            if len(errors) > 5:
                print(f"\n... 외 {len(errors)-5}개 블록에서 문제 발생")
            return False
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

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
        
        # 전체 블록 삭제
        erase_all_blocks(nand)
        
        total_files = len(files)
        processed_files = 0
        failed_files = []
        MAX_RETRIES = 5
        TIMEOUT_SECONDS = 5
        
        start_datetime = datetime.now()
        print(f"\n=== 프로그래밍 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {total_files}개 파일 프로그래밍 예정")
        
        for filename in files:
            try:
                # 파일 검증
                filepath = os.path.join(splits_dir, filename)
                validate_file_size(filepath)
                
                # 주소 계산
                address = hex_to_int(filename.split('.')[0])
                page_no = calculate_page_number(address)
                block_no = page_no // 64
                
                # 디버깅 정보 출력
                print(f"\n현재 작업: {filename}")
                print(f"주소: 0x{address:08X}")
                print(f"페이지: {page_no} (블록 {block_no})")
                
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
                                    
                                    raise ValueError(
                                        f"데이터 검증 실패:\n" + 
                                        "\n".join([
                                            f"  오프셋 0x{m['offset']:04X}: "
                                            f"쓰기 0x{m['written']:02X} != "
                                            f"읽기 0x{m['read']:02X}"
                                            for m in mismatch_positions
                                        ])
                                    )
                                
                                success = True
                                break
                                
                            except Exception as e:
                                if time.time() - timeout_start > TIMEOUT_SECONDS:
                                    raise TimeoutError("페이지 프로그래밍/검증 타임아웃")
                                time.sleep(0.1)
                        break
                        
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n파일 '{filename}' 프로그래밍/검증 실패 (최대 재시도 횟수 초과): {str(e)}")
                            failed_files.append({
                                'file': filename,
                                'error': str(e)
                            })
                        else:
                            print(f"\n파일 '{filename}' 프로그래밍/검증 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.5)  # 재시도 간격 증가
                
                if success:
                    processed_files += 1
                    sys.stdout.write(f"\r작업 중: {processed_files}/{total_files} - {filename}")
                    sys.stdout.flush()
                
            except Exception as e:
                print(f"\n파일 '{filename}' 프로그래밍 중 오류 발생: {str(e)}")
                failed_files.append({
                    'file': filename,
                    'error': str(e)
                })
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        print(f"\n\n=== 프로그래밍 완료 (소요 시간: {duration}) ===")
        
        if not failed_files:
            print("결과: 모든 파일이 성공적으로 프로그래밍됨")
            return True
        else:
            print(f"결과: {len(failed_files)}개 파일에서 문제 발생")
            
            # 오류 로그 파일 저장
            log_filename = f"program_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(f"=== NAND 프로그래밍 오류 로그 ===\n")
                f.write(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"종료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"소요 시간: {duration}\n")
                f.write(f"총 오류 파일 수: {len(failed_files)}\n\n")
                
                for error in failed_files:
                    f.write(f"\n파일: {error['file']}\n")
                    f.write(f"  {error['error']}\n")
            
            print(f"\n오류 상세 내역이 {log_filename} 파일에 저장되었습니다.")
            
            # 처음 5개의 오류만 화면에 출력
            for error in failed_files[:5]:
                print(f"\n파일: {error['file']}")
                print(f"  {error['error']}")
            
            if len(failed_files) > 5:
                print(f"\n... 외 {len(failed_files)-5}개 파일에서 문제 발생")
            return False
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    program_nand() 