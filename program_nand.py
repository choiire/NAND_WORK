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

def program_page_only(nand, page_no: int, write_data: bytes, max_retries: int = 3) -> bool:
    """데이터시트 PROGRAM PAGE 사양에 따른 페이지 쓰기만 수행 (검증 없음)"""
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
            
            # 성공
            return True
            
        except Exception as e:
            if retry == max_retries - 1:
                # 최종 실패 시 Bad Block으로 표시
                nand.mark_bad_block(block_no)
                raise RuntimeError(f"페이지 {page_no} 쓰기 최종 실패 (블록 {block_no}를 Bad Block으로 표시): {str(e)}")
            else:
                print(f"    쓰기 재시도 {retry + 1}/{max_retries}: {str(e)}")
                time.sleep(0.01 * (retry + 1))  # 점진적 지연
    
    return False

def verify_pages_batch(nand, page_data_list: list, max_retries: int = 3) -> dict:
    """배치로 페이지들을 검증"""
    results = {
        'success': [],
        'failed': []
    }
    
    for page_info in page_data_list:
        page_no = page_info['page_no']
        original_data = page_info['data']
        filename = page_info['filename']
        
        for retry in range(max_retries):
            try:
                # Read-back 검증
                time.sleep(0.0001)  # 100µs 대기
                read_data = nand.read_page(page_no, len(original_data))
                
                # 데이터 무결성 검증
                if len(read_data) != len(original_data):
                    raise ValueError(f"읽기 데이터 길이 불일치: {len(read_data)} != {len(original_data)}")
                
                # 바이트별 비교
                mismatches = []
                for i, (w, r) in enumerate(zip(original_data, read_data)):
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
                        f"      오프셋 0x{m['offset']:04X}: 쓰기=0x{m['written']:02X}, 읽기=0x{m['read']:02X}"
                        for m in mismatches
                    ])
                    raise ValueError(f"데이터 검증 실패 ({len(mismatches)}개 불일치):\n{error_details}")
                
                # 검증 성공
                results['success'].append(page_info)
                break
                
            except Exception as e:
                if retry == max_retries - 1:
                    # 최종 검증 실패
                    page_info['error'] = str(e)
                    results['failed'].append(page_info)
                    
                    # Bad Block으로 표시
                    block_no = page_no // 64
                    nand.mark_bad_block(block_no)
                else:
                    print(f"    검증 재시도 {retry + 1}/{max_retries} (파일: {filename}): {str(e)}")
                    time.sleep(0.01 * (retry + 1))
    
    return results

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
        BATCH_SIZE = 10  # 배치 크기
        MAX_RETRIES = 3
        
        start_datetime = datetime.now()
        error_log_filename = f"program_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        
        print(f"\n=== NAND 플래시 배치 프로그래밍 시작 ===")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 파일 수: {total_files}개")
        print(f"배치 크기: {BATCH_SIZE}개 파일")
        print(f"Bad Block 수: {len(nand.bad_blocks)}개")
        print(f"오류 로그: {error_log_filename}")
        print("=" * 60)
        
        # 배치 단위로 처리
        for batch_start in range(0, total_files, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_files)
            batch_files = files[batch_start:batch_end]
            current_batch = (batch_start // BATCH_SIZE) + 1
            total_batches = (total_files + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n--- 배치 {current_batch}/{total_batches} 처리 중 ({len(batch_files)}개 파일) ---")
            
            # 1단계: 배치 내 모든 파일 쓰기
            batch_data = []
            write_failed = []
            
            print("  [1단계] 쓰기 작업 진행...")
            for filename in batch_files:
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
                        print(f"    Bad Block 스킵: {filename} (블록 {block_no})")
                        continue
                    
                    # 데이터 읽기
                    with open(filepath, 'rb') as f:
                        write_data = f.read()
                    
                    # 쓰기 작업 수행
                    try:
                        success = program_page_only(nand, page_no, write_data, MAX_RETRIES)
                        if success:
                            batch_data.append({
                                'filename': filename,
                                'page_no': page_no,
                                'data': write_data,
                                'address': address,
                                'block': block_no,
                                'file_size': file_size
                            })
                            print(f"    쓰기 완료: {filename}")
                        else:
                            raise RuntimeError("쓰기 실패")
                            
                    except Exception as e:
                        error_info = {
                            'file': filename,
                            'address': address,
                            'page': page_no,
                            'block': block_no,
                            'error': str(e),
                            'stage': 'write'
                        }
                        write_failed.append(error_info)
                        print(f"    쓰기 실패: {filename} - {str(e)}")
                        
                except Exception as e:
                    error_info = {
                        'file': filename,
                        'error': str(e),
                        'stage': 'preparation'
                    }
                    write_failed.append(error_info)
                    print(f"    파일 처리 실패: {filename} - {str(e)}")
            
            # 2단계: 배치 내 성공한 파일들 일괄 검증
            if batch_data:
                print(f"  [2단계] 검증 작업 진행 ({len(batch_data)}개 파일)...")
                
                verification_results = verify_pages_batch(nand, batch_data, MAX_RETRIES)
                
                # 검증 성공 파일 처리
                for success_info in verification_results['success']:
                    processed_files += 1
                    print(f"    검증 성공: {success_info['filename']}")
                
                # 검증 실패 파일 처리
                for failed_info in verification_results['failed']:
                    error_info = {
                        'file': failed_info['filename'],
                        'address': failed_info['address'],
                        'page': failed_info['page_no'],
                        'block': failed_info['block'],
                        'error': failed_info['error'],
                        'stage': 'verification'
                    }
                    failed_files.append(error_info)
                    print(f"    검증 실패: {failed_info['filename']}")
            
            # 쓰기 단계에서 실패한 파일들도 실패 목록에 추가
            failed_files.extend(write_failed)
            
            # 배치 결과 요약
            batch_success = len(verification_results['success']) if batch_data else 0
            batch_write_fail = len(write_failed)
            batch_verify_fail = len(verification_results['failed']) if batch_data else 0
            batch_skip = len([s for s in skipped_bad_blocks if s['file'] in batch_files])
            
            print(f"  배치 {current_batch} 결과: 성공 {batch_success}, 쓰기실패 {batch_write_fail}, 검증실패 {batch_verify_fail}, 스킵 {batch_skip}")
            
            # 진행률 표시
            progress = (batch_end / total_files) * 100
            print(f"  전체 진행률: {progress:.1f}% ({batch_end}/{total_files})")
            
            # 오류 로그 기록
            if write_failed or (batch_data and verification_results['failed']):
                with open(error_log_filename, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== 배치 {current_batch} 오류 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
                    for error in write_failed + (verification_results['failed'] if batch_data else []):
                        f.write(f"파일: {error.get('file', 'Unknown')}\n")
                        f.write(f"단계: {error.get('stage', 'Unknown')}\n")
                        f.write(f"오류: {error.get('error', 'Unknown')}\n\n")
        
        # 최종 결과 출력
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        
        print(f"\n\n{'='*60}")
        print(f"=== NAND 플래시 배치 프로그래밍 완료 ===")
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
            write_failures = [f for f in failed_files if f.get('stage') == 'write']
            verify_failures = [f for f in failed_files if f.get('stage') == 'verification']
            prep_failures = [f for f in failed_files if f.get('stage') == 'preparation']
            
            if write_failures:
                print(f"  쓰기 실패 ({len(write_failures)}개):")
                for fail in write_failures[:3]:
                    print(f"    {fail['file']}: {fail.get('error', 'Unknown')}")
                if len(write_failures) > 3:
                    print(f"    ... 및 {len(write_failures) - 3}개 더")
            
            if verify_failures:
                print(f"  검증 실패 ({len(verify_failures)}개):")
                for fail in verify_failures[:3]:
                    print(f"    {fail['file']}: {fail.get('error', 'Unknown')}")
                if len(verify_failures) > 3:
                    print(f"    ... 및 {len(verify_failures) - 3}개 더")
            
            if prep_failures:
                print(f"  준비 실패 ({len(prep_failures)}개):")
                for fail in prep_failures[:3]:
                    print(f"    {fail['file']}: {fail.get('error', 'Unknown')}")
                if len(prep_failures) > 3:
                    print(f"    ... 및 {len(prep_failures) - 3}개 더")
            
            print(f"\n자세한 오류 내역: {error_log_filename}")
        
        print("=" * 60)
        
        return len(failed_files) == 0
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    success = program_nand()
    sys.exit(0 if success else 1) 