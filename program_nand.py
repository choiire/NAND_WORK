import os
import time
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    return int(hex_str, 16)

def erase_all_blocks(nand, total_blocks=4096):  # 4Gb = 4096 blocks
    """전체 블록 삭제"""
    start_datetime = datetime.now()
    print(f"\n=== 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    for block in range(total_blocks):
        # 각 블록의 첫 페이지 번호 계산 (블록당 64페이지)
        page_no = block * 64
        nand.erase_block(page_no)
        
        if (block + 1) % 100 == 0:  # 100블록마다 진행상황 출력
            sys.stdout.write(f"\r블록 삭제 중: {block + 1}/{total_blocks} 블록")
            sys.stdout.flush()
    
    print("\n전체 블록 삭제 완료")

def program_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # 전체 블록 삭제
    erase_all_blocks(nand)
    
    # output_splits 디렉토리 경로
    splits_dir = "output_splits"
    
    # 파일 목록 가져오기 및 정렬
    files = [f for f in os.listdir(splits_dir) if f.endswith('.bin')]
    files.sort()
    
    total_files = len(files)
    processed_files = 0
    
    start_datetime = datetime.now()
    print(f"\n=== 프로그래밍 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {total_files}개 파일 프로그래밍 예정")
    
    for filename in files:
        # 파일 이름에서 주소 추출 (예: 20A00F90.bin -> 0x20A00F90)
        address = hex_to_int(filename.split('.')[0])
        page_no = address // 0x800
        
        # 파일 읽기
        with open(os.path.join(splits_dir, filename), 'rb') as f:
            data = f.read()
            
        try:
            # 페이지 프로그래밍
            nand.write_page(page_no, data)
            
            processed_files += 1
            sys.stdout.write(f"\r작업 중: {processed_files}/{total_files} - {filename}")
            sys.stdout.flush()
            
        except Exception as e:
            print(f"\n오류 발생 - 파일: {filename}")
            print(f"오류 내용: {str(e)}")
            return False
            
        # 과도한 연속 쓰기 방지를 위한 짧은 대기
        time.sleep(0.01)
    
    print("\n\n프로그래밍 완료")
    return True

if __name__ == "__main__":
    program_nand() 