import os

INPUT_DIR = "output_splits"
OUTPUT_FILE = "merged_output.bin"
ORIGINAL_FILE = "input.bin"
ROW_SIZE = 16
ALL_FF_ROW = b'\xff' * ROW_SIZE

def merge_files():
    """
    output_chunks 디렉토리의 .bin 파일들을 주소 순서대로 읽어
    하나의 파일로 합치고, 빈 공간은 0xFF로 채웁니다.
    원본 파일의 크기와 동일하게 마지막 부분을 0xFF로 채웁니다.
    """
    if not os.path.exists(INPUT_DIR):
        print(f"오류: 입력 디렉토리 '{INPUT_DIR}'을(를) 찾을 수 없습니다.")
        return
    
    if not os.path.exists(ORIGINAL_FILE):
        print(f"오류: 원본 파일 '{ORIGINAL_FILE}'을(를) 찾을 수 없습니다.")
        return

    original_size = os.path.getsize(ORIGINAL_FILE)

    chunk_files = sorted(
        [f for f in os.listdir(INPUT_DIR) if f.endswith('.bin')],
        key=lambda f: int(f.split('.')[0], 16)
    )

    if not chunk_files:
        print(f"'{INPUT_DIR}' 디렉토리에 분할된 파일이 없습니다.")
        return

    print(f"'{OUTPUT_FILE}' 파일 생성을 시작합니다...")

    current_address = 0
    try:
        with open(OUTPUT_FILE, 'wb') as out_f:
            for filename in chunk_files:
                chunk_start_address = int(filename.split('.')[0], 16)

                # 주소에 맞게 0xFF 채우기
                if chunk_start_address > current_address:
                    padding_size = chunk_start_address - current_address
                    print(f"  - {current_address:08X}부터 {padding_size} 바이트 0xFF 채우기")
                    padding_rows = padding_size // ROW_SIZE
                    for _ in range(padding_rows):
                        out_f.write(ALL_FF_ROW)
                
                # 청크 데이터 쓰기
                file_path = os.path.join(INPUT_DIR, filename)
                with open(file_path, 'rb') as in_f:
                    data = in_f.read()
                    out_f.write(data)
                    print(f"  - {filename} 데이터 쓰기 ({len(data)} 바이트)")
                
                current_address = chunk_start_address + len(data)

            # 원본 파일 크기에 맞게 마지막 부분을 0xFF로 채우기
            if current_address < original_size:
                final_padding_size = original_size - current_address
                print(f"  - 파일 끝: {current_address:08X}부터 {final_padding_size} 바이트 0xFF 채우기")
                final_padding_rows = final_padding_size // ROW_SIZE
                for _ in range(final_padding_rows):
                    out_f.write(ALL_FF_ROW)
                # 남은 바이트 처리
                remaining_bytes = final_padding_size % ROW_SIZE
                if remaining_bytes > 0:
                    out_f.write(b'\xff' * remaining_bytes)

    except Exception as e:
        print(f"파일 병합 중 오류 발생: {e}")
        return

    print(f"파일 병합이 완료되었습니다. 최종 파일: '{OUTPUT_FILE}'")

if __name__ == "__main__":
    merge_files()
