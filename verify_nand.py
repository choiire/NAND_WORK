import os
import sys
import hashlib
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP
import time

def calculate_block_hash(data):
    """데이터의 SHA-256 해시값 계산"""
    return hashlib.sha256(data).hexdigest()

def validate_input_file(filepath: str) -> int:
    """입력 파일 유효성 검사"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"파일을 찾을 수 없음: {filepath}")
        
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValueError("입력 파일이 비어있습니다")
        
    if file_size % (2048 * 64) != 0:
        raise ValueError("입력 파일 크기가 블록 크기와 맞지 않습니다")
        
    if file_size > 512 * 1024 * 1024:  # 512MB
        raise ValueError("입력 파일이 너무 큽니다 (최대 512MB)")
        
    return file_size

def analyze_page_error(page_no, expected_page, actual_page):
    """페이지 오류 상세 분석"""
    page_addr = page_no * 0x800
    mismatch_positions = []
    
    try:
        for i in range(len(expected_page)):
            if expected_page[i] != actual_page[i]:
                mismatch_positions.append({
                    'offset': page_addr + i,
                    'expected': expected_page[i],
                    'actual': actual_page[i]
                })
                if len(mismatch_positions) >= 10:  # 첫 10개 오류만 수집
                    break
    except Exception as e:
        raise RuntimeError(f"페이지 오류 분석 실패 (페이지 {page_no}): {str(e)}")
    
    return {
        'page': page_no,
        'address': f"0x{page_addr:08X}",
        'mismatches': mismatch_positions
    }

def analyze_block_error(block_no, expected_block, actual_block):
    """블록 오류 분석"""
    try:
        error_info = {
            'block': block_no,
            'start_page': block_no * 64,
            'address': f"0x{(block_no * 64 * 0x800):08X}",
            'expected_hash': calculate_block_hash(expected_block),
            'actual_hash': calculate_block_hash(actual_block)
        }
        
        # 페이지별 오류 분석
        for page_offset in range(64):
            page_start = page_offset * 2048
            page_end = page_start + 2048
            
            expected_page = expected_block[page_start:page_end]
            actual_page = actual_block[page_start:page_end]
            
            if expected_page != actual_page:
                page_error = analyze_page_error(
                    block_no * 64 + page_offset,
                    expected_page,
                    actual_page
                )
                error_info.setdefault('page_errors', []).append(page_error)
        
        return error_info
    except Exception as e:
        raise RuntimeError(f"블록 오류 분석 실패 (블록 {block_no}): {str(e)}")

def verify_nand():
    try:
        nand = MT29F4G08ABADAWP()
        
        # 입력 파일 검증
        input_file = 'input.bin'
        file_size = validate_input_file(input_file)
        total_blocks = file_size // (2048 * 64)
        
        start_datetime = datetime.now()
        print(f"\n=== 검증 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {total_blocks}개 블록 검증 예정")
        
        errors = []
        verified_blocks = 0
        MAX_ERRORS = 100  # 최대 오류 수 제한
        CHUNK_SIZE = 10   # 한 번에 처리할 블록 수
        
        with open(input_file, 'rb') as f:
            for chunk_start in range(0, total_blocks, CHUNK_SIZE):
                chunk_end = min(chunk_start + CHUNK_SIZE, total_blocks)
                chunk_blocks = chunk_end - chunk_start
                
                try:
                    for block_offset in range(chunk_blocks):
                        block_no = chunk_start + block_offset
                        
                        # Bad Block 체크
                        if nand.is_bad_block(block_no):
                            print(f"\n블록 {block_no}은 Bad Block으로 표시되어 있어 건너뜁니다.")
                            continue
                        
                        # input.bin에서 해당 블록의 데이터 추출
                        block_offset_bytes = block_no * 2048 * 64
                        f.seek(block_offset_bytes)
                        expected_block = f.read(2048 * 64)
                        
                        # NAND에서 블록 데이터 읽기
                        actual_block = bytearray()
                        start_page = block_no * 64
                        
                        try:
                            for page_offset in range(64):
                                page_no = start_page + page_offset
                                
                                # 타임아웃 설정
                                timeout_start = time.time()
                                while True:
                                    try:
                                        page_data = nand.read_page(page_no)
                                        actual_block.extend(page_data)
                                        break
                                    except Exception as e:
                                        if time.time() - timeout_start > 5:  # 5초 타임아웃
                                            raise TimeoutError(f"페이지 {page_no} 읽기 타임아웃")
                                        time.sleep(0.1)  # 0.1초 대기 후 재시도
                        
                        except Exception as e:
                            print(f"\n블록 {block_no} 읽기 중 오류 발생: {str(e)}")
                            nand.mark_bad_block(block_no)
                            errors.append({
                                'block': block_no,
                                'error': str(e)
                            })
                            if len(errors) >= MAX_ERRORS:
                                break
                            continue
                        
                        # 블록 데이터 비교 (ECC 디코딩 이후)
                        try:
                            if expected_block != actual_block:
                                error_info = analyze_block_error(
                                    block_no,
                                    expected_block,
                                    actual_block
                                )
                                errors.append(error_info)
                                
                                if len(errors) >= MAX_ERRORS:
                                    print(f"\n최대 오류 수({MAX_ERRORS})에 도달하여 검증 중단")
                                    break
                        except Exception as e:
                            print(f"\n블록 {block_no} 비교 중 오류 발생: {str(e)}")
                            errors.append({
                                'block': block_no,
                                'error': str(e)
                            })
                            if len(errors) >= MAX_ERRORS:
                                break
                        
                        verified_blocks += 1
                        if verified_blocks % 10 == 0:  # 10블록마다 진행상황 출력
                            sys.stdout.write(f"\r검증 중: {verified_blocks}/{total_blocks} 블록")
                            sys.stdout.flush()
                            
                except Exception as e:
                    print(f"\n청크 처리 중 오류 발생 (블록 {chunk_start}-{chunk_end-1}): {str(e)}")
                    continue
                
                if len(errors) >= MAX_ERRORS:
                    break
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        
        # 결과 출력
        print(f"\n\n=== 검증 완료 (소요 시간: {duration}) ===")
        
        if not errors:
            print("결과: 모든 데이터 일치")
            return True
        else:
            print(f"결과: {len(errors)}개 블록에서 오류 발견")
            
            # 처음 5개의 오류 블록만 상세 출력
            for error in errors[:5]:
                if 'error' in error:
                    print(f"\n블록 {error['block']}: {error['error']}")
                else:
                    print(f"\n블록 {error['block']} (시작 주소: {error['address']}):")
                    print(f"예상 해시값: {error['expected_hash']}")
                    print(f"실제 해시값: {error['actual_hash']}")
                    
                    if 'page_errors' in error:
                        print("페이지별 오류 상세:")
                        for page_error in error['page_errors']:
                            print(f"\n  페이지 {page_error['page']} (주소: {page_error['address']}):")
                            for mismatch in page_error['mismatches']:
                                print(f"    오프셋 0x{mismatch['offset']:08X}: "
                                      f"예상값 0x{mismatch['expected']:02X}, "
                                      f"실제값 0x{mismatch['actual']:02X}")
            
            if len(errors) > 5:
                print(f"\n... 외 {len(errors)-5}개 블록에서 오류 발생")
            return False
            
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    verify_nand() 