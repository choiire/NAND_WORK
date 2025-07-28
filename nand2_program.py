import os
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP
import time

# --- 새로운 상수 정의 ---
FULL_PAGE_SIZE = MT29F4G08ABADAWP.PAGE_SIZE + MT29F4G08ABADAWP.SPARE_SIZE # 2112 바이트

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ValueError(f"잘못된 파일명 형식: {hex_str}")

def calculate_page_number(address: int) -> int:
    """주소를 페이지 번호로 변환"""
    page_no = address // FULL_PAGE_SIZE # 주소 계산의 기준을 전체 페이지 크기로 변경
    if page_no >= 256 * 1024:
        raise ValueError(f"유효하지 않은 페이지 번호: {page_no}")
    return page_no

def validate_directory(dirpath: str) -> None:
    """디렉토리 유효성 검사"""
    if not os.path.exists(dirpath) or not os.path.isdir(dirpath):
        raise NotADirectoryError(f"유효한 디렉토리가 아님: {dirpath}")

def program_page_only(nand, page_no: int, write_data: bytes, max_retries: int = 5) -> bool:
    """페이지 쓰기 수행 (Bad Block 로직 제거)"""
    for retry in range(max_retries):
        try:
            # 드라이버의 write_page가 내부적으로 대기 및 상태 확인 수행
            nand.write_full_page(page_no, write_data)
            return True
        except Exception as e:
            if retry == max_retries - 1:
                # 최종 실패 시 예외 발생 (Bad Block으로 마킹하지 않음)
                raise RuntimeError(f"페이지 {page_no} 쓰기 최종 실패: {str(e)}")
            else:
                print(f"    쓰기 재시도 {retry + 1}/{max_retries}: {str(e)}")
                time.sleep(1) # 1초 대기
    return False

def verify_pages_batch(nand, page_data_list: list, max_retries: int = 5) -> dict:
    """
    배치로 페이지들을 검증합니다.
    데이터 불일치 시, 상세한 디버깅 정보를 포함하여 오류를 발생시킵니다.
    """
    results = {'success': [], 'failed': []}
    for page_info in page_data_list:
        page_no = page_info['page_no']
        original_data = page_info['data']
        
        for retry in range(max_retries):
            try:
                read_data = nand.read_page(page_no, len(original_data))
                
                if read_data != original_data:
                    # --- 변경된 부분: 상세 불일치 정보 생성 ---
                    mismatches = []
                    # 데이터가 짧게 읽혔을 경우를 대비해 짧은 길이를 기준으로 비교
                    compare_len = min(len(original_data), len(read_data))
                    
                    for i in range(compare_len):
                        written_byte = original_data[i]
                        read_byte = read_data[i]
                        if written_byte != read_byte:
                            mismatches.append(
                                f"  - 오프셋 0x{i:04X}: 쓰기=0x{written_byte:02X}, 읽기=0x{read_byte:02X}"
                            )
                            if len(mismatches) >= 16: # 최대 16개까지만 표시
                                mismatches.append("  - ... (불일치 다수)")
                                break
                    
                    error_details = "\n".join(mismatches)
                    
                    # 전체 데이터 길이도 확인
                    len_info = f"데이터 길이: 쓰기={len(original_data)}, 읽기={len(read_data)}"
                    
                    # 최종 에러 메시지 생성
                    raise ValueError(f"데이터 검증 실패:\n{len_info}\n불일치 내역:\n{error_details}")
                
                # 검증 성공
                results['success'].append(page_info)
                break # 성공 시 재시도 중단
                
            except Exception as e:
                if retry == max_retries - 1:
                    page_info['error'] = str(e)
                    results['failed'].append(page_info)
                else:
                    print(f"    검증 재시도 {retry + 1}/{max_retries} (페이지 {page_no}): {str(e)}")
                    time.sleep(1)
                    
    return results

def program_nand():
    """NAND 플래시 프로그래밍 (메모리 최적화 및 최종 수정)"""
    try:
        print("NAND 플래시 드라이버 초기화 중...")
        nand = MT29F4G08ABADAWP()
        
        splits_dir = "output_splits"
        validate_directory(splits_dir)
        
        files = [f for f in os.listdir(splits_dir) if f.endswith('.bin')]
        if not files:
            raise ValueError(f"프로그래밍할 파일이 없음: {splits_dir}")
        files.sort()
        
        total_files = len(files)
        failed_files_info = []
        
        BATCH_SIZE = 10
        MAX_RETRIES = 5 # 쓰기와 검증 모두에 사용할 재시도 횟수
        
        start_datetime = datetime.now()
        error_log_filename = f"program_errors_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        
        print(f"\n{'='*60}")
        print(f" NAND 플래시 프로그래밍 시작 (Bad Block 없음 가정)")
        print(f"{'='*60}")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H%M:%S')}")
        print(f"총 파일 수: {total_files}개")
        print(f"오류 로그: {error_log_filename}")
        print("=" * 60)
        
        total_pages_to_process = 0
        successful_pages_count = 0

        for i in range(0, total_files, BATCH_SIZE):
            batch_files = files[i : i + BATCH_SIZE]
            current_batch_num = (i // BATCH_SIZE) + 1
            total_batches = (total_files + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n--- 파일 배치 {current_batch_num}/{total_batches} 처리 중 ({len(batch_files)}개 파일) ---")

            batch_pages_to_write = []
            for filename in batch_files:
                try:
                    filepath = os.path.join(splits_dir, filename)
                    if os.path.getsize(filepath) == 0:
                        print(f"경고: 파일이 비어있어 건너뜁니다: {filename}")
                        continue

                    with open(filepath, 'rb') as f:
                        file_data = f.read()

                    start_address = hex_to_int(filename.split('.')[0])
                    start_page_no = start_address // FULL_PAGE_SIZE

                    for page_offset, chunk_start in enumerate(range(0, len(file_data), FULL_PAGE_SIZE)):
                        chunk_data = file_data[chunk_start : chunk_start + FULL_PAGE_SIZE]
                        current_page_no = start_page_no + page_offset
                        
                        batch_pages_to_write.append({
                            'filename': filename,
                            'page_no': current_page_no,
                            'data': chunk_data,
                        })
                except Exception as e:
                    failed_files_info.append({'file': filename, 'reason': f"파일 준비 중 오류: {e}"})

            total_pages_to_process += len(batch_pages_to_write)
            
            written_pages_for_verify = []
            print("  [1단계] 쓰기 작업 진행...")
            for page_info in batch_pages_to_write:
                try:
                    if program_page_only(nand, page_info['page_no'], page_info['data'], MAX_RETRIES):
                        written_pages_for_verify.append(page_info)
                        print(f"    쓰기 완료: Page {page_info['page_no']} (from {page_info['filename']})")
                except Exception as e:
                    failed_files_info.append({'file': page_info['filename'], 'reason': str(e)})
                    print(f"    쓰기 실패: Page {page_info['page_no']} - {e}")

            if written_pages_for_verify:
                print(f"  [2단계] 검증 작업 진행 ({len(written_pages_for_verify)}개 페이지)...")
                # --- 개선 제안 반영: MAX_RETRIES 상수 전달 ---
                verification_results = verify_pages_batch(nand, written_pages_for_verify, MAX_RETRIES)
                
                successful_pages_count += len(verification_results['success'])

                for failed_info in verification_results['failed']:
                    failed_files_info.append({'file': failed_info['filename'], 'reason': failed_info['error']})
                    print(f"    검증 실패: Page {failed_info['page_no']} (from {failed_info['filename']})")
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        
        failed_pages_count = len(failed_files_info)

        print(f"\n\n{'.='*60}")
        print(f".=== NAND 플래시 프로그래밍 완료 ===")
        print(f"{'.='*60}")
        print(f"완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요 시간: {duration}")
        print(f"\n총 처리 시도 페이지 수: {total_pages_to_process}")
        print(f"성공: {successful_pages_count}")
        print(f"실패: {failed_pages_count}")
        
        if failed_files_info:
            print(f"\n실패 내역은 {error_log_filename} 파일을 확인하세요.")
            with open(error_log_filename, 'w', encoding='utf-8') as f:
                for info in failed_files_info:
                    f.write(f"File: {info['file']}, Reason: {info['reason']}\n")
        
        print(".=" * 60)
        
        return len(failed_files_info) == 0
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False
    finally:
        if 'nand' in locals() and nand:
            print("\nGPIO 리소스를 정리합니다.")
            del nand


if __name__ == "__main__":
    success = program_nand()
    sys.exit(0 if success else 1)