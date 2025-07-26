import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def erase_and_verify_blocks():
    """전체 블록을 삭제하고 FF로 초기화되었는지 검증"""
    TOTAL_BLOCKS = 4096  # 4Gb = 4096 blocks
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    
    try:
        nand = MT29F4G08ABADAWP()
        
        # 1. 전체 블록 삭제
        start_datetime = datetime.now()
        print(f"\n=== 전체 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {TOTAL_BLOCKS}개 블록 삭제 예정")
        
        for block in range(TOTAL_BLOCKS):
            page_no = block * PAGES_PER_BLOCK
            nand.erase_block(page_no)
            
            if (block + 1) % 10 == 0:
                sys.stdout.write(f"\r블록 삭제 중: {block + 1}/{TOTAL_BLOCKS} 블록")
                sys.stdout.flush()
        
        print("\n전체 블록 삭제 완료")
        
        # 2. 삭제된 블록 검증
        print("\n=== 블록 검증 시작 ===")
        errors = []
        
        for block in range(TOTAL_BLOCKS):
            # 각 블록의 첫 페이지만 검사 (시간 단축)
            page_no = block * PAGES_PER_BLOCK
            data = nand.read_page(page_no)
            
            # FF 값 검증
            if not all(b == 0xFF for b in data):
                # 오류가 있는 경우 첫 번째 오류 위치와 값 기록
                for offset, value in enumerate(data):
                    if value != 0xFF:
                        errors.append({
                            'block': block,
                            'page': page_no,
                            'offset': offset,
                            'value': value
                        })
                        break  # 첫 번째 오류만 기록
            
            if (block + 1) % 10 == 0:
                sys.stdout.write(f"\r블록 검증 중: {block + 1}/{TOTAL_BLOCKS} 블록")
                sys.stdout.flush()
        
        # 3. 결과 출력
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        print(f"\n\n=== 검증 완료 (소요 시간: {duration}) ===")
        
        if not errors:
            print("결과: 모든 블록이 성공적으로 초기화됨 (FF)")
            return True
        else:
            print(f"결과: {len(errors)}개 블록에서 초기화 오류 발견")
            
            # 처음 5개의 오류만 상세 출력
            for error in errors[:5]:
                print(f"\n블록 {error['block']} (페이지 {error['page']}):")
                print(f"  오프셋 0x{error['offset']:04X}에서 0x{error['value']:02X} 발견 (예상: 0xFF)")
            
            if len(errors) > 5:
                print(f"\n... 외 {len(errors)-5}개 블록에서 오류 발생")
            return False
            
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    erase_and_verify_blocks() 