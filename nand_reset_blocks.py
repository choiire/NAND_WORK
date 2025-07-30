import sys
import time
from datetime import datetime
from nand_driver import MT29F4G08ADADA

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

def verify_block_initialization(nand, block_no: int, verification_level: str = "quick") -> dict:
    """블록 초기화 상태를 다양한 수준으로 검증 (블록 0는 ECC 활성화)
    
    Args:
        nand: NAND 드라이버 인스턴스
        block_no: 검증할 블록 번호
        verification_level: 검증 수준
            - "quick": 첫/마지막 페이지의 첫 바이트만 확인 (기존 방식)
            - "sample": 여러 페이지의 여러 위치 샘플링
            - "full": 전체 블록의 모든 데이터 확인 (느림)
    
    Returns:
        검증 결과 딕셔너리
    """
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    block_start_page = block_no * PAGES_PER_BLOCK
    
    # 블록 0 검증 시에만 ECC 활성화
    is_block_0 = (block_no == 0)
    ecc_changed = False
    
    # ECC 상태 설정
    if is_block_0:
        print(f"\n  [INFO] 블록 0 검증을 위해 ECC 활성화 중...")
        if nand.enable_internal_ecc():
            ecc_changed = True
            print(f"  [INFO] ECC 활성화 완료")
        else:
            print(f"  [WARNING] ECC 활성화 실패, 계속 진행...")
    else:
        # 블록 1 이상에서는 ECC 비활성화 확인
        print(f"\n  [INFO] 블록 {block_no} 검증을 위해 ECC 비활성화 중...")
        if nand.disable_internal_ecc():
            ecc_changed = True
            print(f"  [INFO] ECC 비활성화 완료")
        else:
            print(f"  [WARNING] ECC 비활성화 실패, 계속 진행...")
    
    try:
        if verification_level == "quick":
            # 기존 방식: 첫/마지막 페이지의 첫 바이트만
            first_page_data = nand.read_page(block_start_page, 1)
            first_byte = first_page_data[0] if first_page_data else 0x00
            
            last_page_data = nand.read_page(block_start_page + PAGES_PER_BLOCK - 1, 1)
            last_byte = last_page_data[0] if last_page_data else 0x00
            
            if first_byte != 0xFF or last_byte != 0xFF:
                result = {
                    'success': False,
                    'level': 'quick',
                    'error': f'첫 바이트: 0x{first_byte:02X}, 마지막 바이트: 0x{last_byte:02X}',
                    'coverage': '2 bytes / 131072 bytes (0.0015%)'
                }
                # ECC 상태 복원 후 반환
                if ecc_changed and is_block_0:
                    print(f"  [INFO] 블록 0 검증 완료, ECC 비활성화 중...")
                    nand.disable_internal_ecc()
                return result
                
        elif verification_level == "sample":
            # 샘플링 방식: 여러 페이지의 여러 위치 확인
            sample_pages = [0, 15, 31, 47, 63]  # 5개 페이지
            sample_offsets = [0, 512, 1024, 1536, 2047]  # 각 페이지당 5개 위치
            
            errors = []
            total_checked = 0
            
            for page_offset in sample_pages:
                page_no = block_start_page + page_offset
                page_data = nand.read_page(page_no, PAGE_SIZE)
                
                for offset in sample_offsets:
                    if offset < len(page_data):
                        byte_value = page_data[offset]
                        total_checked += 1
                        
                        if byte_value != 0xFF:
                            errors.append({
                                'page': page_no,
                                'offset': offset,
                                'value': byte_value
                            })
            
            if errors:
                result = {
                    'success': False,
                    'level': 'sample',
                    'errors': errors[:5],  # 최대 5개 오류만 반환
                    'total_errors': len(errors),
                    'coverage': f'{total_checked} bytes / 131072 bytes ({(total_checked/131072)*100:.2f}%)'
                }
                # ECC 상태 복원 후 반환
                if ecc_changed and is_block_0:
                    print(f"  [INFO] 블록 0 검증 완료, ECC 비활성화 중...")
                    nand.disable_internal_ecc()
                return result
                
        elif verification_level == "full":
            # 전체 확인: 모든 페이지의 모든 바이트 확인
            errors = []
            total_checked = 0
            
            for page_offset in range(PAGES_PER_BLOCK):
                page_no = block_start_page + page_offset
                page_data = nand.read_page(page_no, PAGE_SIZE)
                
                for offset, byte_value in enumerate(page_data):
                    total_checked += 1
                    
                    if byte_value != 0xFF:
                        errors.append({
                            'page': page_no,
                            'offset': offset,
                            'value': byte_value
                        })
                        
                        # 너무 많은 오류가 발견되면 조기 종료
                        if len(errors) >= 100:
                            result = {
                                'success': False,
                                'level': 'full',
                                'errors': errors[:10],  # 처음 10개만 반환
                                'total_errors': f'{len(errors)}+ (조기 종료)',
                                'coverage': f'{total_checked} bytes / 131072 bytes (조기 종료)'
                            }
                            # ECC 상태 복원 후 반환
                            if ecc_changed and is_block_0:
                                print(f"  [INFO] 블록 0 검증 완료, ECC 비활성화 중...")
                                nand.disable_internal_ecc()
                            return result
            
            if errors:
                result = {
                    'success': False,
                    'level': 'full',
                    'errors': errors[:10],  # 최대 10개 오류만 반환
                    'total_errors': len(errors),
                    'coverage': f'{total_checked} bytes / 131072 bytes (100%)'
                }
                # ECC 상태 복원 후 반환
                if ecc_changed and is_block_0:
                    print(f"  [INFO] 블록 0 검증 완료, ECC 비활성화 중...")
                    nand.disable_internal_ecc()
                return result
        
        # 성공한 경우
        coverage_info = {
            "quick": "2 bytes / 131072 bytes (0.0015%)",
            "sample": f"25 bytes / 131072 bytes (0.019%)",
            "full": "131072 bytes / 131072 bytes (100%)"
        }
        
        result = {
            'success': True,
            'level': verification_level,
            'coverage': coverage_info[verification_level]
        }
        
        # ECC 상태 복원 후 반환
        if ecc_changed and is_block_0:
            print(f"  [INFO] 블록 0 검증 완료, ECC 비활성화 중...")
            nand.disable_internal_ecc()
        return result
        
    except Exception as e:
        # 예외 발생 시에도 ECC 상태 복원
        if ecc_changed and is_block_0:
            print(f"  [INFO] 블록 0 검증 중 예외 발생, ECC 비활성화 중...")
            nand.disable_internal_ecc()
        return {
            'success': False,
            'level': verification_level,
            'error': f'검증 중 오류: {str(e)}'
        }

def get_two_plane_pairs(total_blocks: int) -> list:
    """전체 블록에서 Two-plane 삭제 가능한 블록 쌍을 생성합니다.
    
    Two-plane 조건:
    - 두 블록은 서로 다른 플레인에 위치해야 함 (BA[6] 비트가 달라야 함)
    - 두 블록의 페이지 오프셋은 동일해야 함 (일반적으로 첫 페이지 사용)
    
    Args:
        total_blocks: 전체 블록 수
        
    Returns:
        [(block1, block2), ...] 형태의 블록 쌍 리스트와 남은 단일 블록 리스트
    """
    pairs = []
    remaining_blocks = []
    
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
    if len(plane0_blocks) > min_plane_size:
        remaining_blocks.extend(plane0_blocks[min_plane_size:])
    if len(plane1_blocks) > min_plane_size:
        remaining_blocks.extend(plane1_blocks[min_plane_size:])
    
    return pairs, remaining_blocks

def get_two_plane_pairs_from_list(block_list: list) -> (list, list):
    """주어진 블록 리스트에서 Two-plane 동작이 가능한 블록 쌍을 생성합니다."""
    pairs = []
    
    # 플레인별로 블록을 분류
    plane0_blocks = sorted([b for b in block_list if (b >> 6) & 1 == 0])
    plane1_blocks = sorted([b for b in block_list if (b >> 6) & 1 == 1])
    
    # 각 플레인에서 동일한 인덱스의 블록들을 쌍으로 만들기
    min_len = min(len(plane0_blocks), len(plane1_blocks))
    for i in range(min_len):
        pairs.append((plane0_blocks[i], plane1_blocks[i]))
        
    # 남은 블록들은 단일 블록으로 처리
    remaining_blocks = plane0_blocks[min_len:] + plane1_blocks[min_len:]
    
    return pairs, remaining_blocks

def scan_bad_blocks_after_erase(nand: MT29F4G08ADADA):
    """삭제 후 Bad Block 스캔 (블록 0는 ECC 활성화)"""
    TOTAL_BLOCKS = 4096
    PAGES_PER_BLOCK = 64
    
    print("\n.=== 삭제 후 Bad Block 스캔 시작 ===")
    new_bad_blocks = []
    MAX_RETRIES = 3
    
    # ECC 상태 추적 변수
    current_ecc_enabled = False
    
    for block in range(TOTAL_BLOCKS):
        # 진행 상황 표시 (100블록마다)
        if block % 100 == 0:
            sys.stdout.write(f"\rBad Block 스캔 진행: {block}/{TOTAL_BLOCKS} 블록")
            sys.stdout.flush()
        
        page = block * PAGES_PER_BLOCK
        
        # 블록 0 스캔 시 ECC 활성화, 그 외에는 비활성화
        if block == 0 and not current_ecc_enabled:
            print(f"\n  [INFO] 블록 0 스캔을 위해 ECC 활성화 중...")
            if nand.enable_internal_ecc():
                current_ecc_enabled = True
                print(f"  [INFO] ECC 활성화 완료")
        elif block == 1 and current_ecc_enabled:
            print(f"\n  [INFO] 블록 1 이상 스캔을 위해 ECC 비활성화 중...")
            if nand.disable_internal_ecc():
                current_ecc_enabled = False
                print(f"  [INFO] ECC 비활성화 완료")
        
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

def erase_and_verify_blocks_two_plane(nand: MT29F4G08ADADA, verification_level: str = "quick"):
    """Two-plane 기능을 사용한 모든 블록 강제 삭제 및 검증 (최종 수정본)"""
    TOTAL_BLOCKS = 4096
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    MAX_RETRIES = 5
    
    verification_info = {
        "quick": "빠른 검증 (각 블록당 2바이트만 확인)",
        "sample": "샘플링 검증 (각 블록당 25바이트 확인)",
        "full": "전체 검증 (Two-plane 읽기 적용, 100% 커버리지)"
    }
    
    try:
        print("NAND 플래시 드라이버 초기화 중...")
        nand.bad_blocks = set()
        
        # 초기 ECC 비활성화
        print("초기 상태 설정을 위해 ECC 비활성화 중...")
        nand.disable_internal_ecc()
        
        start_datetime = datetime.now()
        print(f"\n.=== Two-Plane 기능을 사용한 모든 블록 강제 삭제 및 검증 시작 ===")
        print(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # --- 1단계: 블록 삭제 ---
        successful_blocks_erase = []
        failed_blocks_erase = []
        
        block_pairs, remaining_blocks = get_two_plane_pairs(TOTAL_BLOCKS)
        
        # 1-1: Two-plane으로 블록 쌍 삭제
        for pair_idx, (block1, block2) in enumerate(block_pairs):
            sys.stdout.write(f"\rTwo-plane 삭제 진행: {(pair_idx + 1) / len(block_pairs) * 100:.1f}%")
            sys.stdout.flush()
            page1, page2 = block1 * PAGES_PER_BLOCK, block2 * PAGES_PER_BLOCK
            try:
                nand.erase_block_two_plane(page1, page2)
                successful_blocks_erase.extend([block1, block2])
            except Exception:
                for b, p in [(block1, page1), (block2, page2)]:
                    try:
                        nand.erase_block(p)
                        successful_blocks_erase.append(b)
                    except Exception as e:
                        failed_blocks_erase.append(b)
                        print(f"\n블록 {b} 단일 삭제 실패: {e}")

        # 1-2: 남은 단일 블록 삭제
        for block in remaining_blocks:
            try:
                nand.erase_block(block * PAGES_PER_BLOCK)
                successful_blocks_erase.append(block)
            except Exception as e:
                failed_blocks_erase.append(block)
                print(f"\n단일 블록 {block} 삭제 실패: {e}")

        erase_end_time = datetime.now()
        print("\n\n1단계 (삭제) 완료. 소요 시간:", erase_end_time - start_datetime)

        # --- 2단계: 검증 ---
        print(f"\n.=== 2단계: 삭제 결과 기반 Bad Block 판단 및 검증 시작 ===")
        print(f"검증 방식: {verification_info[verification_level]}")
        scan_start_time = datetime.now()

        for block in failed_blocks_erase: nand.mark_bad_block(block)
        
        data_corruption_blocks = []
        
        # [수정] Full 검증 시 Two-plane 읽기 적용
        if verification_level == "full":
            verify_pairs, verify_singles = get_two_plane_pairs_from_list(successful_blocks_erase)
            
            # ECC 상태 추적 변수
            current_ecc_enabled = False
            
            for i, (block1, block2) in enumerate(verify_pairs):
                sys.stdout.write(f"\rTwo-plane 검증 진행: {(i + 1) / len(verify_pairs) * 100:.1f}%")
                sys.stdout.flush()
                
                # 블록 0 포함 여부 확인 및 ECC 상태 관리
                has_block_0 = (block1 == 0 or block2 == 0)
                
                if has_block_0 and not current_ecc_enabled:
                    print(f"\n  [INFO] 블록 0 포함 Two-plane 검증을 위해 ECC 활성화 중...")
                    if nand.enable_internal_ecc():
                        current_ecc_enabled = True
                        print(f"  [INFO] ECC 활성화 완료")
                elif not has_block_0 and current_ecc_enabled:
                    print(f"\n  [INFO] 블록 0 이외 Two-plane 검증을 위해 ECC 비활성화 중...")
                    if nand.disable_internal_ecc():
                        current_ecc_enabled = False
                        print(f"  [INFO] ECC 비활성화 완료")
                
                for page_offset in range(PAGES_PER_BLOCK):
                    page1 = block1 * PAGES_PER_BLOCK + page_offset
                    page2 = block2 * PAGES_PER_BLOCK + page_offset
                    d1, d2 = nand.read_page_two_plane(page1, page2, PAGE_SIZE)
                    if not all(b == 0xFF for b in d1):
                        data_corruption_blocks.append(block1)
                        break
                    if not all(b == 0xFF for b in d2):
                        data_corruption_blocks.append(block2)
                        break
            
            # Two-plane 검증 완료 후 ECC 비활성화
            if current_ecc_enabled:
                print(f"\n  [INFO] Two-plane 검증 완료, ECC 비활성화 중...")
                nand.disable_internal_ecc()
            
            for block in verify_singles:
                res = verify_block_initialization(nand, block, "full")
                if not res['success']: data_corruption_blocks.append(block)
        else:
            for i, block in enumerate(successful_blocks_erase):
                sys.stdout.write(f"\r단일 블록 검증 진행: {(i + 1) / len(successful_blocks_erase) * 100:.1f}%")
                sys.stdout.flush()
                res = verify_block_initialization(nand, block, verification_level)
                if not res['success']: data_corruption_blocks.append(block)
        
        for block in data_corruption_blocks:
            nand.mark_bad_block(block)
            print(f"\n데이터 손상 블록 발견: 블록 {block}")
        
        print("\n초기화 검증 완료.")
        
        # --- 최종 결과 출력 및 로그 저장 (기존 로직 유지) ---
        scan_end_time = datetime.now()
        scan_duration = scan_end_time - scan_start_time
        total_duration = scan_end_time - start_datetime
        
        total_bad_blocks = len(nand.bad_blocks)
        good_blocks = TOTAL_BLOCKS - total_bad_blocks
        
        print(f"\n\n{'='*80}")
        print(f"=== Two-Plane 블록 초기화 및 검증 완료 ===")
        print(f"{'='*80}")
        print(f"완료 시간: {scan_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"총 소요 시간: {total_duration}")
        print(f"  - 1단계 (삭제) 시간: {erase_end_time - start_datetime}")
        print(f"  - 2단계 (검증) 시간: {scan_duration}")
        print(f"\n검증 수준: {verification_info[verification_level]}")
        print(f"총 블록 수: {TOTAL_BLOCKS}")
        print(f"정상 블록: {good_blocks} ({(good_blocks/TOTAL_BLOCKS)*100:.2f}%)")
        print(f"Bad Block: {total_bad_blocks} ({(total_bad_blocks/TOTAL_BLOCKS)*100:.2f}%)")
        print(f"  - 하드웨어 Bad Block: {len(failed_blocks_erase)}개 (삭제 실패)")
        print(f"  - 데이터 손상 Block: {len(set(data_corruption_blocks))}개 (초기화 실패)") # 중복 제거
        
        log_filename = f"erase_log_{verification_level}_{start_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        with open(log_filename, 'w', encoding='utf-8') as f:
            f.write(f"=== NAND 전체 블록 삭제 및 Bad Block 검증 로그 ===\n")
            f.write(f"시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"종료 시간: {scan_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"총 소요 시간: {total_duration}\n")
            f.write(f"검증 수준: {verification_level}\n")
            f.write(f"총 Bad Block: {total_bad_blocks}개\n")
            f.write("=== Bad Block 목록 ===\n")
            for block in sorted(list(nand.bad_blocks)):
                reason = "삭제 실패" if block in failed_blocks_erase else "초기화 실패"
                f.write(f"  블록 {block}: {reason}\n")
        
        print(f"\n상세 로그가 {log_filename} 파일에 저장되었습니다.")
        print("=" * 80)
        
        bad_block_rate = (total_bad_blocks / TOTAL_BLOCKS) * 100
        return bad_block_rate < 5.0

    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

# 기존 erase_and_verify_blocks 함수는 호환성을 위해 유지
def erase_and_verify_blocks(verification_level: str = "quick"):
    """기존 단일 블록 처리 방식 (호환성 유지)"""
    return erase_and_verify_blocks_two_plane(verification_level)

if __name__ == "__main__":
    # 사용자에게 검증 수준 선택 안내
    print("NAND 블록 초기화 및 검증 프로그램 (Two-Plane 기능 지원)")
    print("=" * 60)

    # [수정] 프로그램 시작 시 드라이버를 한 번만 초기화합니다.
    try:
        print("NAND 드라이버 초기화 중 (공장 Bad Block 스캔)...")
        # 시작할 때 공장 Bad Block을 스캔하는 것이 안전합니다.
        nand_chip = MT29F4G08ADADA(skip_bad_block_scan=False) 
    except Exception as e:
        print(f"드라이버 초기화 실패: {e}")
        sys.exit(1)

    print("=" * 60)
    print("1. 빠른 검증 (Two-Plane, 첫/마지막 페이지 첫 바이트만)")
    print("2. 샘플링 검증 (Two-Plane, 여러 페이지/위치 샘플링)")
    print("3. 전체 검증 (Two-Plane, 모든 바이트 확인, 매우 느림)")
    print("4. 현재 상태에서 Bad Block 스캔 (삭제 안 함)")
    print("5. 종료")
    
    while True:
        choice = input("\n작업을 선택하세요 (1-5): ")
        
        # [수정] 모든 호출에 생성된 nand_chip 객체를 전달합니다.
        if choice in ["1", "2", "3"]:
            level_map = {"1": "quick", "2": "sample", "3": "full"}
            print("\n경고: 모든 블록을 강제로 삭제하고 다시 검증합니다. 기존 Bad Block 정보는 초기화됩니다.")
            confirm = input("계속하시겠습니까? (y/n): ")
            if confirm.lower() == 'y':
                success = erase_and_verify_blocks_two_plane(nand_chip, verification_level=level_map[choice])
                sys.exit(0 if success else 1)
        elif choice == "4":
            # [수정] scan_bad_blocks_after_erase 함수에도 nand_chip 객체를 전달해야 합니다.
            scan_bad_blocks_after_erase(nand_chip)
        elif choice == "5":
            print("프로그램을 종료합니다.")
            sys.exit(0)
        else:
            print("잘못된 선택입니다. 다시 시도하세요.")