import os
import time
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    return int(hex_str, 16)

def program_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # output_splits 디렉토리 경로
    splits_dir = "output_splits"
    
    # 파일 목록 가져오기 및 정렬
    files = os.listdir(splits_dir)
    files.sort()  # 주소 순으로 정렬
    
    total_files = len(files)
    processed_files = 0
    
    print(f"총 {total_files}개의 파일을 프로그래밍합니다...")
    
    for filename in files:
        if not filename.endswith('.bin'):
            continue
            
        # 파일 이름에서 주소 추출 (예: 20A00F90.bin -> 0x20A00F90)
        address = hex_to_int(filename.split('.')[0])
        
        # 페이지 번호 계산 (2KB = 0x800 단위로 나누기)
        page_no = address // 0x800
        
        # 파일 읽기
        with open(os.path.join(splits_dir, filename), 'rb') as f:
            data = f.read()
            
        try:
            # 페이지 프로그래밍
            print(f"프로그래밍 중: {filename} (주소: 0x{address:08X}, 페이지: {page_no})")
            nand.write_page(page_no, data)
            
            processed_files += 1
            print(f"진행률: {processed_files}/{total_files} ({processed_files/total_files*100:.1f}%)")
            
        except Exception as e:
            print(f"오류 발생 - 파일: {filename}, 오류: {str(e)}")
            return False
            
        # 과도한 연속 쓰기 방지를 위한 짧은 대기
        time.sleep(0.01)
    
    print("프로그래밍이 완료되었습니다!")
    return True

if __name__ == "__main__":
    program_nand() 