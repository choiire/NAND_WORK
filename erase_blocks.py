import sys
import time
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def verify_block(nand, block_no: int, pages_to_check: list = None) -> dict:
    """단일 블록 검증
    
    Args:
        nand: NAND 드라이버 인스턴스
        block_no: 검증할 블록 번호
        pages_to_check: 검사할 페이지 번호 리스트 (None이면 첫 페이지만 검사)
    
    Returns:
        검증 결과 딕셔너리
    """
    PAGES_PER_BLOCK = 64
    block_start_page = block_no * PAGES_PER_BLOCK
    MAX_RETRIES = 5  # 페이지 읽기 최대 재시도 횟수
    TIMEOUT_SECONDS = 5  # 각 시도당 최대 대기 시간
    
    # 공장 출하 시 Bad Block 마킹 확인
    first_page = block_start_page
    last_page = block_start_page + PAGES_PER_BLOCK - 1
    
    try:
        first_byte = nand.read_page(first_page, 1)[0]
        last_byte = nand.read_page(last_page, 1)[0]
        
        if first_byte != 0xFF or last_byte != 0xFF:
            return {
                'success': False,
                'error': f"공장 출하 시 Bad Block 마킹 발견 (첫 페이지: 0x{first_byte:02X}, 마지막 페이지: 0x{last_byte:02X})"
            }
    except Exception as e:
        return {
            'success': False,
            'error': f"Bad Block 마킹 확인 중 오류 발생: {str(e)}"
        }
    
    if pages_to_check is None:
        pages_to_check = [block_start_page]  # 첫 페이지만 검사
    
    errors = []
    
    for page_offset in pages_to_check:
        page_no = block_start_page + (page_offset % PAGES_PER_BLOCK)
        
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
            continue
        
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

def scan_bad_blocks_after_erase(nand):
    """삭제 후 Bad Block 스캔"""
    TOTAL_BLOCKS = 4096
    PAGES_PER_BLOCK = 64
    
    print("\n=== 삭제 후 Bad Block 스캔 시작 ===")
    new_bad_blocks = []
    MAX_RETRIES = 3
    
    for block in range(TOTAL_BLOCKS):
        # 진행 상황 표시 (100블록마다)
        if block % 100 == 0:
            sys.stdout.write(f"\rBad Block 스캔 진행: {block}/{TOTAL_BLOCKS} 블록")
            sys.stdout.flush()
        
        page = block * PAGES_PER_BLOCK
        
        try:
            # 첫 페이지와 마지막 페이지의 첫 바이트 확인
            for retry in range(MAX_RETRIES):
                try:
                    first_page_data = nand.read_page(page, 1)
                    first_byte = first_page_data[0] if first_page_data else 0x00
                    
                    last_page_data = nand.read_page(page + PAGES_PER_BLOCK - 1, 1)
                    last_byte = last_page_data[0] if last_page_data else 0x00
                    break
                except Exception as e:
                    if retry == MAX_RETRIES - 1:
                        print(f"\n블록 {block} 읽기 실패: {str(e)}")
                        first_byte = 0x00
                        last_byte = 0x00
                    else:
                        time.sleep(0.01)
            
            # 첫 바이트가 0xFF가 아니면 Bad Block
            if first_byte != 0xFF or last_byte != 0xFF:
                nand.mark_bad_block(block)
                new_bad_blocks.append({
                    'block': block,
                    'first_byte': first_byte,
                    'last_byte': last_byte
                })
                print(f"\nBad Block 발견: 블록 {block} (첫 페이지: 0x{first_byte:02X}, 마지막 페이지: 0x{last_byte:02X})")
                
        except Exception as e:
            print(f"\n블록 {block} 스캔 중 오류: {str(e)}")
            # 안전을 위해 스캔에 실패한 블록은 Bad Block으로 표시
            nand.mark_bad_block(block)
            new_bad_blocks.append({
                'block': block,
                'error': str(e)
            })
    
    print(f"\n\nBad Block 스캔 완료.")
    print(f"새로 발견된 Bad Block: {len(new_bad_blocks)}개")
    if new_bad_blocks:
        print("Bad Block 목록:")
        for bad_block in new_bad_blocks[:10]:  # 최대 10개만 표시
            if 'error' in bad_block:
                print(f"  블록 {bad_block['block']}: 오류 - {bad_block['error']}")
            else:
                print(f"  블록 {bad_block['block']}: 첫 페이지=0x{bad_block['first_byte']:02X}, 마지막 페이지=0x{bad_block['last_byte']:02X}")
        if len(new_bad_blocks) > 10:
            print(f"  ... 및 {len(new_bad_blocks) - 10}개 더")
    
    return new_bad_blocks

def erase_and_verify_blocks():
    """1단계: 전체 블록 삭제, 2단계: Bad Block 스캔"""
    TOTAL_BLOCKS = 4096  # 4Gb = 4096 blocks
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    MAX_RETRIES = 5  # 블록 삭제 최대 재시도 횟수
    CHUNK_SIZE = 10  # 한 번에 처리할 블록 수
    
    try:
        # NAND 초기화 (Bad Block 스캔 비활성화 필요)
        print("NAND 플래시 드라이버 초기화 중 (Bad Block 스캔 스킵)...")
        nand = MT29F4G08ABADAWP()
        
        # 기존 Bad Block 정보 초기화
        nand.bad_blocks = set()
        
        start_datetime = datetime.now()
        print(f"\n=== 1단계: 전체 블록 삭제 시작 ===")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 {TOTAL_BLOCKS}개 블록 삭제 예정")
        print("=" * 50)
        
        erase_errors = []
        processed_blocks = 0
        skipped_blocks = 0
        
        # 1단계: 모든 블록 삭제
        for chunk_start in range(0, TOTAL_BLOCKS, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, TOTAL_BLOCKS)
            chunk_blocks = chunk_end - chunk_start
            
            for block_offset in range(chunk_blocks):
                block = chunk_start + block_offset
                page_no = block * PAGES_PER_BLOCK
                
                # 블록 삭제 (최대 5번 재시도)
                erase_success = False
                for retry in range(MAX_RETRIES):
                    try:
                        nand.erase_block(page_no)
                        erase_success = True
                        break
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n블록 {block} 삭제 실패 (최대 재시도 횟수 초과): {str(e)}")
                            erase_errors.append({
                                'block': block,
                                'error': f"삭제 실패: {str(e)}"
                            })
                        else:
                            print(f"\n블록 {block} 삭제 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.1)
                
                if erase_success:
                    processed_blocks += 1
                else:
                    skipped_blocks += 1
                
                # 진행률 표시 (10블록마다)
                if (processed_blocks + skipped_blocks) % 10 == 0:
                    progress = ((processed_blocks + skipped_blocks) / TOTAL_BLOCKS) * 100
                    sys.stdout.write(f"\r삭제 진행: {progress:.1f}% ({processed_blocks + skipped_blocks}/{TOTAL_BLOCKS})")
                    sys.stdout.flush()
        
        erase_end_time = datetime.now()
        erase_duration = erase_end_time - start_datetime
        
        print(f"\n\n1단계 완료:")
        print(f"  삭제 성공: {processed_blocks}개 블록")
        print(f"  삭제 실패: {skipped_blocks}개 블록") 
        print(f"  소요 시간: {erase_duration}")
        
        # 2단계: Bad Block 스캔
        print(f"\n=== 2단계: Bad Block 스캔 시작 ===")
        scan_start_time = datetime.now()
        
        new_bad_blocks = scan_bad_blocks_after_erase(nand)
        
        scan_end_time = datetime.now()
        scan_duration = scan_end_time - scan_start_time
        total_duration = scan_end_time - start_datetime
        
        # 최종 결과 출력
        print(f"\n\n{'='*60}")
        print(f"=== 전체 작업 완료 ===")
        print(f"{'='*60}")
        print(f"완료 시간: {scan_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 소요 시간: {total_duration}")
        print(f"1단계 (삭제) 시간: {erase_duration}")
        print(f"2단계 (스캔) 시간: {scan_duration}")
        print()
        print(f"총 블록 수: {TOTAL_BLOCKS}")
        print(f"삭제 성공: {processed_blocks}")
        print(f"삭제 실패: {len(erase_errors)}")
        print(f"Bad Block 발견: {len(new_bad_blocks)}")
        print(f"전체 성공률: {(processed_blocks/TOTAL_BLOCKS)*100:.2f}%")
        
        # 오류 로그 저장
        if erase_errors or new_bad_blocks:
            log_filename = f"erase_scan_log_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(f"=== NAND 블록 삭제 및 Bad Block 스캔 로그 ===\n")
                f.write(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"종료 시간: {scan_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"총 소요 시간: {total_duration}\n")
                f.write(f"삭제 오류 블록 수: {len(erase_errors)}\n")
                f.write(f"Bad Block 수: {len(new_bad_blocks)}\n\n")
                
                if erase_errors:
                    f.write("=== 삭제 실패 블록 ===\n")
                    for error in erase_errors:
                        f.write(f"블록 {error['block']}: {error['error']}\n")
                    f.write("\n")
                
                if new_bad_blocks:
                    f.write("=== Bad Block 목록 ===\n")
                    for bad_block in new_bad_blocks:
                        if 'error' in bad_block:
                            f.write(f"블록 {bad_block['block']}: 스캔 오류 - {bad_block['error']}\n")
                        else:
                            f.write(f"블록 {bad_block['block']}: 첫 페이지=0x{bad_block['first_byte']:02X}, "
                                  f"마지막 페이지=0x{bad_block['last_byte']:02X}\n")
            
            print(f"\n상세 로그가 {log_filename} 파일에 저장되었습니다.")
        
        print("=" * 60)
        
        # 성공 기준: 삭제 실패가 적고 전체적으로 안정적
        success_rate = (processed_blocks / TOTAL_BLOCKS) * 100
        return success_rate >= 95.0  # 95% 이상 성공 시 성공으로 간주
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    success = erase_and_verify_blocks()
    sys.exit(0 if success else 1) 