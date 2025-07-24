import os
import sys
import hashlib
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def calculate_block_hash(data):
    """데이터의 SHA-256 해시값 계산"""
    return hashlib.sha256(data).hexdigest()

def verify_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # input.bin 파일 열기
    with open('input.bin', 'rb') as f:
        input_data = f.read()
    
    # 전체 크기 (528MB = 528 * 1024 * 1024 바이트)
    total_size = len(input_data)
    total_blocks = total_size // (2048 * 64)  # 블록 크기 = 페이지 크기(2KB) * 페이지 수(64)
    
    start_datetime = datetime.now()
    print(f"\n=== 검증 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {total_blocks}개 블록 검증 예정")
    
    errors = []
    verified_blocks = 0
    
    for block_no in range(total_blocks):
        # 블록의 첫 페이지 번호 계산
        start_page = block_no * 64
        
        try:
            # 1. input.bin에서 해당 블록의 데이터 추출
            block_offset = block_no * 2048 * 64
            expected_block = input_data[block_offset:block_offset + (2048 * 64)]
            expected_hash = calculate_block_hash(expected_block)
            
            # 2. NAND에서 블록 데이터 읽기
            actual_block = bytearray()
            for page_offset in range(64):
                page_no = start_page + page_offset
                actual_block.extend(nand.read_page(page_no))
            
            actual_hash = calculate_block_hash(actual_block)
            
            # 3. 해시값 비교
            if actual_hash != expected_hash:
                # 해시가 다른 경우, 어떤 페이지에서 차이가 있는지 확인
                errors.append({
                    'block': block_no,
                    'start_page': start_page,
                    'address': f"0x{(start_page * 0x800):08X}",
                    'expected_hash': expected_hash,
                    'actual_hash': actual_hash
                })
                
                # 페이지별로 차이점 상세 확인
                for page_offset in range(64):
                    page_no = start_page + page_offset
                    page_addr = page_no * 0x800
                    expected_page = expected_block[page_offset*2048:(page_offset+1)*2048]
                    actual_page = actual_block[page_offset*2048:(page_offset+1)*2048]
                    
                    if expected_page != actual_page:
                        # 첫 10개의 다른 바이트 위치 찾기
                        mismatch_positions = []
                        for i in range(len(expected_page)):
                            if expected_page[i] != actual_page[i]:
                                mismatch_positions.append({
                                    'offset': page_addr + i,
                                    'expected': expected_page[i],
                                    'actual': actual_page[i]
                                })
                                if len(mismatch_positions) >= 10:
                                    break
                        
                        errors[-1].setdefault('page_errors', []).append({
                            'page': page_no,
                            'address': f"0x{page_addr:08X}",
                            'mismatches': mismatch_positions
                        })
            
            verified_blocks += 1
            sys.stdout.write(f"\r검증 중: {verified_blocks}/{total_blocks} 블록, 주소: 0x{(start_page * 0x800):08X}")
            sys.stdout.flush()
                
        except Exception as e:
            print(f"\n오류 발생 - 블록: {block_no}")
            print(f"오류 내용: {str(e)}")
            return False
    
    end_datetime = datetime.now()
    
    # 결과 출력
    if not errors:
        print(f"\n\n=== 검증 완료 (완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"결과: 모든 데이터 일치")
        return True
    else:
        print(f"\n\n=== 검증 완료 (완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"결과: {len(errors)}개 블록에서 오류 발견")
        
        # 처음 5개의 오류 블록만 상세 출력
        for error in errors[:5]:
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

if __name__ == "__main__":
    verify_nand() 