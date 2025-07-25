# 첫 번째 블록 테스트   
# 블록 삭제 후 데이터 쓰기 후 검증

import os
import sys
from nand_driver import MT29F4G08ABADAWP

def test_first_block():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    print("\n=== 첫 번째 블록 테스트 시작 ===")
    
    # 첫 번째 블록의 첫 페이지 번호 (64페이지/블록)
    first_block_page = 0
    
    try:
        # 1. 블록 삭제
        print("\n1. 블록 삭제 시작")
        nand.erase_block(first_block_page)
        print("블록 삭제 완료")
        
        # 2. 데이터 쓰기 - 첫 번째 블록의 64페이지에 데이터 쓰기
        print("\n2. 데이터 쓰기 시작")
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):  # 한 블록은 64페이지
                page_no = first_block_page + page_offset
                page_data = f.read(2048)  # 한 페이지 크기만큼 읽기
                
                sys.stdout.write(f"\r페이지 쓰기 중: {page_offset + 1}/64")
                sys.stdout.flush()
                
                nand.write_page(page_no, page_data)
        print("\n데이터 쓰기 완료")
        
        # 3. 데이터 검증
        print("\n3. 데이터 검증 시작")
        errors = []
        
        # input.bin 파일의 처음부터 다시 읽기
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):
                page_no = first_block_page + page_offset
                expected_data = f.read(2048)
                actual_data = nand.read_page(page_no)
                
                sys.stdout.write(f"\r페이지 검증 중: {page_offset + 1}/64")
                sys.stdout.flush()
                
                if actual_data != expected_data:
                    # 불일치하는 바이트 위치 찾기
                    mismatch_positions = []
                    for i in range(len(actual_data)):
                        if actual_data[i] != expected_data[i]:
                            mismatch_positions.append({
                                'offset': page_no * 2048 + i,
                                'expected': expected_data[i],
                                'actual': actual_data[i]
                            })
                    
                    if mismatch_positions:
                        errors.append({
                            'page': page_no,
                            'address': f"0x{(page_no * 0x800):08X}",
                            'mismatches': mismatch_positions[:10]  # 처음 10개의 오류만 저장
                        })
        
        print("\n검증 완료")
        
        # 결과 출력
        if not errors:
            print("\n결과: 모든 데이터 일치")
            return True
        else:
            print(f"\n결과: {len(errors)}개 페이지에서 오류 발견")
            for error in errors:
                print(f"\n페이지 {error['page']} (주소: {error['address']}):")
                for mismatch in error['mismatches']:
                    print(f"  오프셋 0x{mismatch['offset']:08X}: "
                          f"예상값 0x{mismatch['expected']:02X}, "
                          f"실제값 0x{mismatch['actual']:02X}")
            return False
            
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    test_first_block() 