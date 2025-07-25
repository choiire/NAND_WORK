import os

INPUT_FILE = "input.bin"
OUTPUT_DIR = "output_splits"
ROW_SIZE = 16
ALL_FF_ROW = b'\xff' * ROW_SIZE
MIN_FF_ROWS = 100  # 최소 FF 행 개수

def split_file():
    """
    input.bin 파일을 읽어 0xFF로 채워진 부분이 연속으로 MIN_FF_ROWS개 이상일 때를 기준으로 
    데이터 청크를 분리하고, 각 청크의 시작 주소를 파일 이름으로 하여 별도의 .bin 파일로 저장합니다.
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
            ff_row_count = 0

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

                if is_ff_row:
                    ff_row_count += 1
                    if ff_row_count >= MIN_FF_ROWS and in_data_block:
                        # FF 행이 MIN_FF_ROWS개 이상 연속으로 나타나면 현재 데이터 블록의 끝
                        output_filename = os.path.join(OUTPUT_DIR, f"{chunk_start_address:08X}.bin")
                        with open(output_filename, 'wb') as out_f:
                            out_f.write(chunk_data)
                        print(f"  - 청크 저장: {output_filename} ({len(chunk_data)} 바이트)")
                        in_data_block = False
                        chunk_data = bytearray()
                else:
                    # 유의미한 데이터 행
                    ff_row_count = 0
                    if not in_data_block:
                        # 새 데이터 블록 시작
                        in_data_block = True
                        chunk_start_address = current_address
                        chunk_data = bytearray()
                    chunk_data.extend(row)

                if in_data_block and ff_row_count < MIN_FF_ROWS:
                    # FF 행이지만 아직 MIN_FF_ROWS에 도달하지 않았다면 데이터에 포함
                    chunk_data.extend(row)

                current_address += ROW_SIZE

    except Exception as e:
        print(f"파일 처리 중 오류 발생: {e}")
        return

    print("파일 분할이 완료되었습니다.")

if __name__ == "__main__":
    split_file()
