import os
import sys
from datetime import datetime
from nand_driver import MT29F8G08ADADA
import time

# --- 새로운 상수 정의 ---
FULL_PAGE_SIZE = MT29F8G08ADADA.PAGE_SIZE + MT29F8G08ADADA.SPARE_SIZE # 2112 바이트
#PAGE_SIZE = MT29F8G08ADADA.PAGE_SIZE

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ValueError(f"잘못된 파일명 형식: {hex_str}")

def calculate_page_number(address: int) -> int:
    """주소를 페이지 번호로 변환"""
    page_no = address // FULL_PAGE_SIZE # 주소 계산의 기준을 전체 페이지 크기로 변경
    if page_no >= 8192 * 64:
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
    TOTAL_BLOCKS = 8192
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
    배치로 페이지들을 검증합니다. (ECC 영역 제외)
    ECC 영역: 808h-80Fh, 818h-81Fh, 828h-82Fh, 838h-83Fh
    """
    # ECC 영역 정의 (16진수 주소를 10진수로 변환)
    ECC_RANGES = [
        (0x808, 0x80F),  # 808h-80Fh
        (0x818, 0x81F),  # 818h-81Fh  
        (0x828, 0x82F),  # 828h-82Fh
        (0x838, 0x83F),  # 838h-83Fh
    ]
    
    def is_ecc_offset(offset):
        """주어진 오프셋이 ECC 영역인지 확인"""
        for start, end in ECC_RANGES:
            if start <= offset <= end:
                return True
        return False
    
    results = {'success': [], 'failed': []}
    for page_info in page_data_list:
        page_no = page_info['page_no']
        original_data = page_info['data']
        
        for retry in range(max_retries):
            try:
                # 페이지 전체를 읽어옵니다.
                read_data = nand.read_page(page_no, len(original_data))
                
                # ECC 영역을 제외한 데이터 비교
                mismatches = []
                compare_len = min(len(original_data), len(read_data))
                ecc_skipped_count = 0
                
                for i in range(compare_len):
                    # ECC 영역은 건너뛰기
                    if is_ecc_offset(i):
                        ecc_skipped_count += 1
                        continue
                        
                    written_byte = original_data[i]
                    read_byte = read_data[i]
                    if written_byte != read_byte:
                        mismatches.append(
                            f"  - 오프셋 0x{i:04X}: 쓰기=0x{written_byte:02X}, 읽기=0x{read_byte:02X}"
                        )
                        if len(mismatches) >= 16:
                            mismatches.append("  - ... (불일치 다수)")
                            break
                
                # 불일치가 있으면 오류 발생
                if mismatches:
                    error_details = "\n".join(mismatches)
                    len_info = f"데이터 길이: 쓰기={len(original_data)}, 읽기={len(read_data)}"
                    ecc_info = f"ECC 영역 제외됨: {ecc_skipped_count}바이트"
                    raise ValueError(f"데이터 검증 실패:\n{len_info}\n{ecc_info}\n불일치 내역:\n{error_details}")
                
                results['success'].append(page_info)
                # 성공 메시지 제거 - 더 이상 출력하지 않음
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
        nand = MT29F8G08ADADA()
        # ECC 비활성화 및 상태 검증
        print("\n내부 ECC 엔진 설정을 확인합니다...")
        ecc_disabled = nand.disable_internal_ecc()
        if not ecc_disabled:
            print("경고: ECC 비활성화에 실패했습니다. 프로그래밍을 계속하지만 예상치 못한 동작이 발생할 수 있습니다.")
        nand.check_ecc_status()

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
        
        # BATCH_SIZE 제거 - 이제 파일을 하나씩 처리
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

        # 파일을 하나씩 처리
        for file_index, filename in enumerate(files):
            # 진행률을 같은 줄에 출력 (줄바꿈 없이)
            sys.stdout.write(f"\r파일 {file_index + 1}/{total_files}: {filename} 처리 중...")
            sys.stdout.flush()
            
            try:
                filepath = os.path.join(splits_dir, filename)
                
                # 파일 존재 여부 확인
                if not os.path.exists(filepath):
                    print(f"\n오류: 파일이 존재하지 않습니다: {filename}")
                    continue
                    
                if os.path.getsize(filepath) == 0:
                    print(f"\n경고: 파일이 비어있어 건너뜁니다: {filename}")
                    continue

                with open(filepath, 'rb') as f:
                    file_data = f.read()

                # 파일 크기 검증 (2112바이트 고정)
                if len(file_data) != FULL_PAGE_SIZE:
                    print(f"\n경고: 파일 크기가 예상과 다릅니다 ({len(file_data)}바이트, 예상: {FULL_PAGE_SIZE}바이트): {filename}")

                start_address = hex_to_int(filename.split('.')[0])
                page_no = start_address // FULL_PAGE_SIZE

                total_pages_to_process += 1
                
                # 페이지 쓰기
                write_success = False
                try:
                    if program_page_only(nand, page_no, file_data, MAX_RETRIES):
                        write_success = True
                except Exception as e:
                    failed_files_info.append({'file': filename, 'reason': str(e)})
                    print(f"\n    쓰기 실패: Page {page_no} - {e}")

                # 검증 단계
                if write_success:
                    page_info = {
                        'filename': filename,
                        'page_no': page_no,
                        'data': file_data
                    }
                    verification_results = verify_pages_batch(nand, [page_info], MAX_RETRIES)
                    
                    if verification_results['success']:
                        successful_pages_count += 1
                        # 성공 시에는 진행률만 업데이트 (줄바꿈 없음)
                    else:
                        failed_info = verification_results['failed'][0]
                        failed_files_info.append({'file': filename, 'reason': failed_info['error']})
                        print(f"\n    검증 실패: Page {page_no} - {failed_info['error']}")
                        
            except Exception as e:
                failed_files_info.append({'file': filename, 'reason': f"파일 처리 중 오류: {e}"})
                print(f"\n  파일 처리 실패: {filename} - {e}")
        
        # 모든 파일 처리 완료 후 줄바꿈
        print("\n")
        
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