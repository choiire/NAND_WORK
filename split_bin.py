import os

INPUT_FILE = "input.BIN"
OUTPUT_DIR = "output_chunks"
ROW_SIZE = 16
ALL_FF_ROW = b'\xff' * ROW_SIZE

def split_file():
    """
    input.bin 파일을 읽어 0xFF로 채워진 부분을 기준으로 데이터 청크를 분리하고,
    각 청크의 시작 주소를 파일 이름으로 하여 별도의 .bin 파일로 저장합니다.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"오류: 입력 파일 '{INPUT_FILE}'을(를) 찾을 수 없습니다.")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"'{OUTPUT_DIR}' 디렉토리를 생성했습니다.")

    print(f"'{INPUT_FILE}' 파일 분할을 시작합니다...")

    try:
        with open(INPUT_FILE, 'rb') as f:
            current_address = 0
            chunk_data = bytearray()
            chunk_start_address = -1
            in_data_block = False

            while True:
                row = f.read(ROW_SIZE)
                if not row:
                    # 파일의 끝
                    if in_data_block and chunk_data:
                        output_filename = os.path.join(OUTPUT_DIR, f"{chunk_start_address:08X}.bin")
                        with open(output_filename, 'wb') as out_f:
                            out_f.write(chunk_data)
                        print(f"  - 청크 저장: {output_filename} ({len(chunk_data)} 바이트)")
                    break

                # 마지막 행이 ROW_SIZE보다 작을 경우 처리
                if len(row) < ROW_SIZE:
                    row += b'\x00' * (ROW_SIZE - len(row))

                is_ff_row = (row == ALL_FF_ROW)

                if not is_ff_row:
                    # 유의미한 데이터 행
                    if not in_data_block:
                        # 새 데이터 블록 시작
                        in_data_block = True
                        chunk_start_address = current_address
                        chunk_data = bytearray()
                    chunk_data.extend(row)
                else:
                    # 0xFF로만 이루어진 행
                    if in_data_block:
                        # 현재 데이터 블록의 끝
                        output_filename = os.path.join(OUTPUT_DIR, f"{chunk_start_address:08X}.bin")
                        with open(output_filename, 'wb') as out_f:
                            out_f.write(chunk_data)
                        print(f"  - 청크 저장: {output_filename} ({len(chunk_data)} 바이트)")
                        in_data_block = False
                        chunk_data = bytearray()

                current_address += ROW_SIZE

    except Exception as e:
        print(f"파일 처리 중 오류 발생: {e}")
        return

    print("파일 분할이 완료되었습니다.")

if __name__ == "__main__":
    split_file()
