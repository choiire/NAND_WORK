import os

INPUT_FILE = "input.bin"
OUTPUT_DIR = "output_splits"
PAGE_SIZE = 2112  # 2KB 데이터 + 64바이트 스페어 영역
ALL_FF_PAGE = b'\xff' * PAGE_SIZE

def split_by_pages():
    """
    input.bin 파일을 페이지 단위로 분할하여 각각의 .bin 파일로 저장합니다.
    파일명은 Bin2_merge.py와 호환되도록 {시작주소}.bin 형식으로 생성됩니다.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"오류: 입력 파일 '{INPUT_FILE}'을(를) 찾을 수 없습니다.")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"'{OUTPUT_DIR}' 디렉토리를 생성했습니다.")

    print(f"'{INPUT_FILE}' 파일을 {PAGE_SIZE}바이트 페이지 단위로 분할을 시작합니다...")

    try:
        with open(INPUT_FILE, 'rb') as f:
            page_number = 0
            saved_pages = 0
            current_address = 0
            
            while True:
                page_data = f.read(PAGE_SIZE)
                if not page_data:
                    # 파일의 끝
                    break
                
                # 마지막 페이지가 PAGE_SIZE보다 작을 경우 0x00으로 패딩
                if len(page_data) < PAGE_SIZE:
                    page_data += b'\x00' * (PAGE_SIZE - len(page_data))
                    print(f"  - 마지막 페이지를 {PAGE_SIZE}바이트로 패딩했습니다.")
                
                # 0xFF로만 채워진 페이지인지 확인
                is_ff_page = (page_data == ALL_FF_PAGE)
                
                if not is_ff_page:
                    # 유의미한 데이터가 있는 페이지만 저장
                    output_filename = os.path.join(OUTPUT_DIR, f"{current_address:08X}.bin")
                    
                    with open(output_filename, 'wb') as out_f:
                        out_f.write(page_data)
                    
                    print(f"  - 페이지 {page_number:04d} 저장: {output_filename} ({len(page_data)} 바이트)")
                    saved_pages += 1
                else:
                    print(f"  - 페이지 {page_number:04d} 건너뜀: 주소 {current_address:08X} (0xFF로 가득참)")
                
                page_number += 1
                current_address += PAGE_SIZE

    except Exception as e:
        print(f"파일 처리 중 오류 발생: {e}")
        return

    print(f"페이지 분할이 완료되었습니다.")
    print(f"  - 총 페이지 수: {page_number}개")
    print(f"  - 저장된 페이지: {saved_pages}개")
    print(f"  - 건너뛴 페이지: {page_number - saved_pages}개 (0xFF로 가득참)")

def get_file_info():
    """
    입력 파일의 정보를 표시합니다.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"오류: 입력 파일 '{INPUT_FILE}'을(를) 찾을 수 없습니다.")
        return
    
    file_size = os.path.getsize(INPUT_FILE)
    total_pages = (file_size + PAGE_SIZE - 1) // PAGE_SIZE  # 올림 계산
    
    print(f"파일 정보:")
    print(f"  - 파일 크기: {file_size:,} 바이트")
    print(f"  - 페이지 크기: {PAGE_SIZE:,} 바이트 (데이터 2048 + 스페어 64)")
    print(f"  - 예상 페이지 수: {total_pages}개")
    print(f"  - 출력 디렉토리: {OUTPUT_DIR}")
    print(f"  - 파일명 형식: {{주소}}.bin (예: 00000000.bin, 00000840.bin)")
    print()

if __name__ == "__main__":
    get_file_info()
    split_by_pages() 