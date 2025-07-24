import os
from nand_driver import MT29F4G08ABADAWP

def verify_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # input.bin 파일 열기
    with open('input.bin', 'rb') as f:
        input_data = f.read()
    
    # 전체 크기 (528MB = 528 * 1024 * 1024 바이트)
    total_size = len(input_data)
    pages_to_verify = total_size // 2048  # 2KB 단위로 나누기
    
    print(f"총 {pages_to_verify}개의 페이지를 검증합니다...")
    
    errors = []
    verified_pages = 0
    
    for page_no in range(pages_to_verify):
        # 입력 파일에서의 오프셋 계산
        offset = page_no * 2048
        expected_data = input_data[offset:offset + 2048]
        
        try:
            # NAND에서 페이지 읽기
            actual_data = nand.read_page(page_no)
            
            # 데이터 비교
            if actual_data != expected_data:
                # 불일치하는 바이트 위치 찾기
                mismatch_positions = []
                for i in range(len(actual_data)):
                    if actual_data[i] != expected_data[i]:
                        mismatch_positions.append({
                            'offset': offset + i,
                            'expected': expected_data[i],
                            'actual': actual_data[i]
                        })
                
                if mismatch_positions:
                    errors.append({
                        'page': page_no,
                        'address': f"0x{(page_no * 0x800):08X}",
                        'mismatches': mismatch_positions[:10]  # 처음 10개의 오류만 저장
                    })
            
            verified_pages += 1
            if verified_pages % 100 == 0:  # 100페이지마다 진행률 출력
                print(f"진행률: {verified_pages}/{pages_to_verify} ({verified_pages/pages_to_verify*100:.1f}%)")
                
        except Exception as e:
            print(f"오류 발생 - 페이지 {page_no}, 오류: {str(e)}")
            return False
    
    # 결과 출력
    if not errors:
        print("\n검증 완료: 모든 데이터가 일치합니다!")
        return True
    else:
        print(f"\n검증 완료: {len(errors)}개의 페이지에서 오류가 발견되었습니다.")
        for error in errors:
            print(f"\n페이지 {error['page']} (주소: {error['address']}):")
            for mismatch in error['mismatches']:
                print(f"  오프셋 0x{mismatch['offset']:08X}: "
                      f"예상값 0x{mismatch['expected']:02X}, "
                      f"실제값 0x{mismatch['actual']:02X}")
        return False

if __name__ == "__main__":
    verify_nand() 