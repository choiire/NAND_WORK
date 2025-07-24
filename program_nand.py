import os
import time
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    return int(hex_str, 16)

def format_time(seconds):
    """초 단위 시간을 시:분:초 형식으로 변환"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours}시간 {minutes}분 {seconds}초"
    elif minutes > 0:
        return f"{minutes}분 {seconds}초"
    else:
        return f"{seconds}초"

def erase_all_blocks(nand, total_blocks=4096):  # 4Gb = 4096 blocks
    """전체 블록 삭제"""
    start_datetime = datetime.now()
    print(f"\n=== 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    start_time = time.time()
    
    for block in range(total_blocks):
        # 각 블록의 첫 페이지 번호 계산 (블록당 64페이지)
        page_no = block * 64
        nand.erase_block(page_no)
        
        if (block + 1) % 100 == 0:  # 100블록마다 진행상황 출력
            elapsed_time = time.time() - start_time
            blocks_per_sec = (block + 1) / elapsed_time
            remaining_blocks = total_blocks - (block + 1)
            estimated_remaining = remaining_blocks / blocks_per_sec
            
            print(f"블록 삭제 중: {block + 1}/{total_blocks} 블록")
            print(f"예상 남은 시간: {format_time(int(estimated_remaining))}")
    
    print("전체 블록 삭제 완료")

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
    start_time = time.time()
    
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
            
            # 진행 상황 및 예상 시간 계산
            elapsed_time = time.time() - start_time
            files_per_sec = processed_files / elapsed_time
            remaining_files = total_files - processed_files
            estimated_remaining = remaining_files / files_per_sec
            
            print(f"\n작업 중: {processed_files}/{total_files} - {filename}")
            print(f"예상 남은 시간: {format_time(int(estimated_remaining))}")
            
        except Exception as e:
            print(f"오류 발생 - 파일: {filename}")
            print(f"오류 내용: {str(e)}")
            return False
            
        # 과도한 연속 쓰기 방지를 위한 짧은 대기
        time.sleep(0.01)
    
    total_time = time.time() - start_time
    print(f"\n프로그래밍 완료 (총 소요시간: {format_time(int(total_time))})")
    return True

if __name__ == "__main__":
    program_nand() 