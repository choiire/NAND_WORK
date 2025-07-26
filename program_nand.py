import os
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ValueError(f"잘못된 파일명 형식: {hex_str}")

def validate_block_number(block_no: int) -> bool:
    """블록 번호 유효성 검사"""
    return 0 <= block_no < 4096  # 4Gb = 4096 blocks

def calculate_block_number(address: int) -> int:
    """주소를 블록 번호로 변환"""
    # 블록 크기 = 페이지 크기(0x800 = 2KB) * 페이지 수(64)
    block_no = address // (0x800 * 64)
    if not validate_block_number(block_no):
        raise ValueError(f"주소 0x{address:08X}에서 계산된 블록 번호({block_no})가 유효하지 않습니다")
    return block_no

def erase_used_blocks(nand, used_blocks):
    """사용할 블록만 선택적으로 삭제"""
    start_datetime = datetime.now()
    print(f"\n=== 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {len(used_blocks)}개 블록 삭제 예정")
    
    for i, block in enumerate(sorted(used_blocks)):
        if not validate_block_number(block):
            raise ValueError(f"유효하지 않은 블록 번호: {block}")
        nand.erase_block(block * 64)  # 블록의 첫 페이지 번호로 변환
        if (i + 1) % 10 == 0:  # 10블록마다 진행상황 출력
            sys.stdout.write(f"\r블록 삭제 중: {i + 1}/{len(used_blocks)} 블록")
            sys.stdout.flush()
    
    print("\n블록 삭제 완료")

def program_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # output_splits 디렉토리 경로
    splits_dir = "output_splits"
    
    # 파일 목록 가져오기 및 정렬
    files = [f for f in os.listdir(splits_dir) if f.endswith('.bin')]
    files.sort()
    
    # 사용할 블록 계산
    used_blocks = set()
    for filename in files:
        address = hex_to_int(filename.split('.')[0])
        block_no = calculate_block_number(address)
        used_blocks.add(block_no)
    
    # 필요한 블록만 삭제
    erase_used_blocks(nand, used_blocks)
    
    total_files = len(files)
    processed_files = 0
    
    start_datetime = datetime.now()
    print(f"\n=== 프로그래밍 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {total_files}개 파일 프로그래밍 예정")
    
    try:
        for filename in files:
            address = hex_to_int(filename.split('.')[0])
            page_no = address // 0x800
            
            with open(os.path.join(splits_dir, filename), 'rb') as f:
                data = f.read()
            
            # 페이지 프로그래밍
            nand.write_page(page_no, data)
            
            processed_files += 1
            sys.stdout.write(f"\r작업 중: {processed_files}/{total_files} - {filename}")
            sys.stdout.flush()
            
        end_datetime = datetime.now()
        print(f"\n\n프로그래밍 완료 (완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')})")
        return True
        
    except Exception as e:
        print(f"\n오류 발생 - 마지막 처리 파일: {filename if 'filename' in locals() else 'Unknown'}")
        print(f"오류 내용: {str(e)}")
        return False

if __name__ == "__main__":
    program_nand() 