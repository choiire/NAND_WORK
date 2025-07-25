# 오류 블록 테스트
# 블록 삭제 후 데이터 쓰기 후 검증

import os
import sys
from nand_driver import MT29F4G08ABADAWP

def test_error_block():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # 페이지 1(0x00000800)이 속한 블록의 첫 페이지 번호 계산
    # 한 블록은 64페이지, 페이지 1은 두 번째 페이지이므로 블록의 시작 페이지는 0
    block_start_page = 0
    
    print(f"\n=== 오류 블록 테스트 시작 (블록 시작 페이지: {block_start_page}) ===")
    
    try:
        # 1. 블록 삭제
        print("\n1. 블록 삭제 시작")
        nand.erase_block(block_start_page)
        print("블록 삭제 완료")
        
        # 삭제 확인
        print("\n2. 블록 삭제 확인")
        for page_offset in range(64):
            page_no = block_start_page + page_offset
            data = nand.read_page(page_no)
            
            # 모든 바이트가 0xFF인지 확인
            if not all(b == 0xFF for b in data):
                print(f"경고: 페이지 {page_no}가 완전히 지워지지 않았습니다!")
                non_ff = [i for i, b in enumerate(data) if b != 0xFF][:5]
                for i in non_ff:
                    print(f"  오프셋 0x{i:04X}: 0x{data[i]:02X} (예상: 0xFF)")
        
        # 3. 데이터 쓰기
        print("\n3. 데이터 쓰기 시작")
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):
                page_no = block_start_page + page_offset
                page_addr = page_no * 0x800
                
                # 파일 포인터를 해당 페이지의 위치로 이동
                f.seek(page_addr)
                page_data = f.read(2048)
                
                sys.stdout.write(f"\r페이지 쓰기 중: {page_offset + 1}/64 (주소: 0x{page_addr:08X})")
                sys.stdout.flush()
                
                nand.write_page(page_no, page_data)
        print("\n데이터 쓰기 완료")
        
        # 4. 데이터 검증
        print("\n4. 데이터 검증 시작")
        errors = []
        
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):
                page_no = block_start_page + page_offset
                page_addr = page_no * 0x800
                
                # 파일 포인터를 해당 페이지의 위치로 이동
                f.seek(page_addr)
                expected_data = f.read(2048)
                actual_data = nand.read_page(page_no)
                
                sys.stdout.write(f"\r페이지 검증 중: {page_offset + 1}/64 (주소: 0x{page_addr:08X})")
                sys.stdout.flush()
                
                if actual_data != expected_data:
                    # 불일치하는 바이트 위치 찾기
                    mismatch_positions = []
                    for i in range(len(actual_data)):
                        if actual_data[i] != expected_data[i]:
                            mismatch_positions.append({
                                'offset': page_addr + i,
                                'expected': expected_data[i],
                                'actual': actual_data[i]
                            })
                    
                    if mismatch_positions:
                        errors.append({
                            'page': page_no,
                            'address': f"0x{page_addr:08X}",
                            'mismatches': mismatch_positions[:10]
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
    test_error_block() 