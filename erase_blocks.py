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

def erase_and_verify_blocks():
    """전체 블록을 삭제하고 FF로 초기화되었는지 검증 (2-Plane 최적화 적용)"""
    TOTAL_BLOCKS = 4096  # 4Gb = 4096 blocks
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    MAX_RETRIES = 5  # 블록 삭제 최대 재시도 횟수

    try:
        nand = MT29F4G08ABADAWP()

        start_datetime = datetime.now()
        print(f"\n=== 전체 블록 삭제 시작 (2-Plane Erase 최적화 적용, 시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {TOTAL_BLOCKS}개 블록 삭제 예정")

        errors = []
        processed_blocks = 0

        # 블록을 2개씩 묶어 처리
        for block_even in range(0, TOTAL_BLOCKS, 2):
            block_odd = block_even + 1
            blocks_to_process_individually = []
            blocks_to_verify = []

            # 마지막 블록 처리 (총 블록 수가 홀수일 경우)
            if block_odd >= TOTAL_BLOCKS:
                if not nand.is_bad_block(block_even):
                    blocks_to_process_individually.append(block_even)
                else:
                    print(f"\n블록 {block_even}은 Bad Block으로 표시되어 있어 건너뜁니다.")
            else:
                is_even_bad = nand.is_bad_block(block_even)
                is_odd_bad = nand.is_bad_block(block_odd)

                # 두 블록 모두 Good Block -> 2-Plane Erase
                if not is_even_bad and not is_odd_bad:
                    erase_success = False
                    for retry in range(MAX_RETRIES):
                        try:
                            nand.erase_two_blocks(block_even, block_odd)
                            erase_success = True
                            break
                        except Exception as e:
                            if retry == MAX_RETRIES - 1:
                                print(f"\n2-Plane 블록 삭제 실패 ({block_even}, {block_odd}): {str(e)}")
                                # 드라이버가 이미 Bad Block으로 마킹하므로 여기서는 오류만 기록
                                errors.append({'block': block_even, 'error': f"2-Plane Erase 실패: {str(e)}"})
                                errors.append({'block': block_odd, 'error': f"2-Plane Erase 실패: {str(e)}"})
                            else:
                                print(f"\n2-Plane 블록 삭제 실패 ({block_even}, {block_odd}), 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                                time.sleep(0.1)
                    if erase_success:
                        blocks_to_verify.extend([block_even, block_odd])
                # 하나라도 Bad Block -> 단일 Erase
                else:
                    if not is_even_bad:
                        blocks_to_process_individually.append(block_even)
                    else:
                        print(f"\n블록 {block_even}은 Bad Block으로 표시되어 있어 건너뜁니다.")

                    if not is_odd_bad:
                        blocks_to_process_individually.append(block_odd)
                    else:
                        print(f"\n블록 {block_odd}은 Bad Block으로 표시되어 있어 건너뜁니다.")

            # 단일 블록 처리
            for block in blocks_to_process_individually:
                erase_success = False
                for retry in range(MAX_RETRIES):
                    try:
                        nand.erase_block(block)
                        erase_success = True
                        break
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n블록 {block} 삭제 실패 (최대 재시도 횟수 초과): {str(e)}")
                            # 드라이버가 이미 Bad Block으로 마킹하므로 여기서는 오류만 기록
                            errors.append({'block': block, 'error': f"삭제 실패: {str(e)}"})
                        else:
                            print(f"\n블록 {block} 삭제 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.1)
                if erase_success:
                    blocks_to_verify.append(block)

            # 검증
            for block in blocks_to_verify:
                verify_result = verify_block(nand, block)
                if not verify_result['success']:
                    error_info = {'block': block, 'errors': verify_result.get('errors', [])}
                    if 'error' in verify_result:
                        error_info['error'] = verify_result['error']
                    errors.append(error_info)
                    nand.mark_bad_block(block) # 드라이버를 통해 Bad Block 마킹
                    print(f"\n블록 {block} 검증 실패. Bad Block으로 마킹합니다.")

            processed_blocks += 2 if block_odd < TOTAL_BLOCKS else 1
            if processed_blocks % 10 < 2:
                sys.stdout.write(f"\r작업 중: {processed_blocks}/{TOTAL_BLOCKS} 블록")
                sys.stdout.flush()

        # 3. 결과 출력
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

if __name__ == "__main__":
    erase_and_verify_blocks() 