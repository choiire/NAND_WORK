import os
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP
import time

# --- 새로운 상수 정의 ---
FULL_PAGE_SIZE = MT29F4G08ABADAWP.PAGE_SIZE + MT29F4G08ABADAWP.SPARE_SIZE # 2112 바이트
PAGE_SIZE = MT29F4G08ABADAWP.PAGE_SIZE

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

def get_two_plane_pairs(total_blocks: int) -> tuple:
    """전체 블록에서 Two-plane 삭제 가능한 블록 쌍을 생성합니다."""
    pairs = []
    
    # 플레인별로 블록을 분류 (BA[6] 비트 기준)
    plane0_blocks = []  # BA[6] = 0
    plane1_blocks = []  # BA[6] = 1
    
    for block in range(total_blocks):
        if (block >> 6) & 1 == 0:  # BA[6] = 0
            plane0_blocks.append(block)
        else:  # BA[6] = 1
            plane1_blocks.append(block)
    
    # 각 플레인에서 동일한 인덱스의 블록들을 쌍으로 만들기
    min_plane_size = min(len(plane0_blocks), len(plane1_blocks))
    
    for i in range(min_plane_size):
        pairs.append((plane0_blocks[i], plane1_blocks[i]))
    
    # 남은 블록들은 단일 블록으로 처리
    remaining_blocks = []
    if len(plane0_blocks) > min_plane_size:
        remaining_blocks.extend(plane0_blocks[min_plane_size:])
    if len(plane1_blocks) > min_plane_size:
        remaining_blocks.extend(plane1_blocks[min_plane_size:])
    
    return pairs, remaining_blocks

def erase_all_blocks_fast(nand):
    """검증 없이 모든 블록을 빠르게 초기화합니다 (Two-plane 기능 사용)"""
    TOTAL_BLOCKS = 4096
    PAGES_PER_BLOCK = 64
    
    try:
        start_datetime = datetime.now()
        print(f".=== 전체 블록 빠른 초기화 시작 (검증 없음) ===")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 블록 수: {TOTAL_BLOCKS}개")
        print("주의: 이 과정은 모든 데이터를 삭제하며 검증하지 않습니다.")
        
        # Bad Block 테이블 초기화
        nand.bad_blocks = set()
        
        successful_blocks_erase = []
        failed_blocks_erase = []
        
        block_pairs, remaining_blocks = get_two_plane_pairs(TOTAL_BLOCKS)
        
        # 1. Two-plane으로 블록 쌍 삭제
        print("Two-plane 블록 삭제 진행 중...")
        for pair_idx, (block1, block2) in enumerate(block_pairs):
            # 진행률 표시
            if pair_idx % 100 == 0:
                progress = (pair_idx + 1) / len(block_pairs) * 100
                sys.stdout.write(f"\rTwo-plane 삭제 진행: {progress:.1f}% ({pair_idx+1}/{len(block_pairs)} 쌍)")
                sys.stdout.flush()
            
            page1, page2 = block1 * PAGES_PER_BLOCK, block2 * PAGES_PER_BLOCK
            try:
                nand.erase_block_two_plane(page1, page2)
                successful_blocks_erase.extend([block1, block2])
            except Exception:
                # Two-plane 실패 시 개별 삭제 시도
                for b, p in [(block1, page1), (block2, page2)]:
                    try:
                        nand.erase_block(p)
                        successful_blocks_erase.append(b)
                    except Exception:
                        failed_blocks_erase.append(b)
        
        print(f"\nTwo-plane 삭제 완료: {len(block_pairs)} 쌍 처리")
        
        # 2. 남은 단일 블록 삭제
        if remaining_blocks:
            print(f"남은 단일 블록 삭제 중... ({len(remaining_blocks)}개)")
            for i, block in enumerate(remaining_blocks):
                if i % 50 == 0:
                    progress = (i + 1) / len(remaining_blocks) * 100
                    sys.stdout.write(f"\r단일 블록 삭제 진행: {progress:.1f}%")
                    sys.stdout.flush()
                
                try:
                    nand.erase_block(block * PAGES_PER_BLOCK)
                    successful_blocks_erase.append(block)
                except Exception:
                    failed_blocks_erase.append(block)
            print(f"\n단일 블록 삭제 완료")
        
        # 실패한 블록들을 Bad Block으로 표시
        for block in failed_blocks_erase:
            nand.mark_bad_block(block)
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        
        print(f".=== 전체 블록 빠른 초기화 완료 ===")
        print(f"완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요 시간: {duration}")
        print(f"성공적으로 삭제된 블록: {len(successful_blocks_erase)}개")
        print(f"삭제 실패 블록 (Bad Block): {len(failed_blocks_erase)}개")
        if failed_blocks_erase:
            print(f"Bad Block 목록: {sorted(failed_blocks_erase)[:10]}")
            if len(failed_blocks_erase) > 10:
                print(f"... 및 {len(failed_blocks_erase) - 10}개 더")
        
        return len(failed_blocks_erase) == 0
        
    except Exception as e:
        print(f"\n전체 블록 초기화 중 오류 발생: {str(e)}")
        return False

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
    배치로 페이지들을 검증합니다. (수정: Main 데이터 영역만 비교)
    """
    results = {'success': [], 'failed': []}
    for page_info in page_data_list:
        page_no = page_info['page_no']
        original_data = page_info['data']
        
        for retry in range(max_retries):
            try:
                read_data = nand.read_page(page_no, len(original_data))
                
                # 핵심 수정: 전체 데이터 대신 Main 영역(앞 2048 바이트)만 비교
                original_main_data = original_data[:PAGE_SIZE]
                read_main_data = read_data[:PAGE_SIZE]

                if read_main_data != original_main_data:
                    mismatches = []
                    compare_len = min(len(original_main_data), len(read_main_data))
                    
                    for i in range(compare_len):
                        written_byte = original_main_data[i]
                        read_byte = read_main_data[i]
                        if written_byte != read_byte:
                            mismatches.append(
                                f"  - 오프셋 0x{i:04X}: 쓰기=0x{written_byte:02X}, 읽기=0x{read_byte:02X}"
                            )
                            if len(mismatches) >= 16:
                                mismatches.append("  - ... (불일치 다수)")
                                break
                    
                    error_details = "\n".join(mismatches)
                    len_info = f"데이터 길이: 쓰기={len(original_main_data)}, 읽기={len(read_main_data)}"
                    raise ValueError(f"데이터 검증 실패:\n{len_info}\n불일치 내역:\n{error_details}")
                
                results['success'].append(page_info)
                break
                
            except Exception as e:
                if retry == max_retries - 1:
                    page_info['error'] = str(e)
                    results['failed'].append(page_info)
                else:
                    print(f"    검증 재시도 {retry + 1}/{max_retries} (페이지 {page_no}): {str(e)}")
                    time.sleep(1)
                    
    return results

def program_nand(initialize_blocks: bool = False):
    """NAND 플래시 프로그래밍 (메모리 최적화 및 최종 수정)"""
    try:
        print("NAND 플래시 드라이버 초기화 중...")
        nand = MT29F4G08ABADAWP()
        
        # 전체 블록 초기화 옵션
        if initialize_blocks:
            print("\n전체 블록 초기화를 시작합니다...")
            init_success = erase_all_blocks_fast(nand)
            if not init_success:
                print("경고: 일부 블록 초기화에 실패했지만 프로그래밍을 계속합니다.")
            else:
                print("전체 블록 초기화가 성공적으로 완료되었습니다.")
        
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
        
        print(f"\n{'.='*60}")
        print(f" NAND 플래시 프로그래밍 시작 (Bad Block 없음 가정)")
        print(f"{'.='*60}")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H%M:%S')}")
        print(f"총 파일 수: {total_files}개")
        print(f"오류 로그: {error_log_filename}")
        print(".=" * 60)
        
        total_pages_to_process = 0
        successful_pages_count = 0

        for i in range(0, total_files, BATCH_SIZE):
            batch_files = files[i : i + BATCH_SIZE]
            current_batch_num = (i // BATCH_SIZE) + 1
            total_batches = (total_files + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n.--- 파일 배치 {current_batch_num}/{total_batches} 처리 중 ({len(batch_files)}개 파일) ---")

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
                        
                         # --- ✨ 변경된 부분 시작 ✨ ---
                        # 항상 2112바이트 크기의 버퍼를 생성하고 0xFF로 초기화
                        full_page_buffer = bytearray([0xFF] * FULL_PAGE_SIZE)
                        
                        # 파일 데이터(chunk_data)를 버퍼의 앞부분에 복사
                        full_page_buffer[:len(chunk_data)] = chunk_data
                        # --- ✨ 변경된 부분 끝 ✨ ---
                        
                        batch_pages_to_write.append({
                            'filename': filename,
                            'page_no': current_page_no,
                            'data': bytes(full_page_buffer), # <--- 항상 2112바이트 버퍼를 전달
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

        print(f".=== NAND 플래시 프로그래밍 완료 ===")
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
                
        return len(failed_files_info) == 0
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False
    finally:
        if 'nand' in locals() and nand:
            print("\nGPIO 리소스를 정리합니다.")
            del nand


if __name__ == "__main__":
    success = program_nand(initialize_blocks=True)
    sys.exit(0 if success else 1)