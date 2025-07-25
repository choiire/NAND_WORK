import os

def are_files_identical(file1_path, file2_path, chunk_size=8192):
    """두 파일이 바이트 단위로 동일한지 비교합니다."""

    # 파일 크기 먼저 비교
    try:
        size1 = os.path.getsize(file1_path)
        size2 = os.path.getsize(file2_path)
    except FileNotFoundError as e:
        print(f"오류: 파일을 찾을 수 없습니다. {e}")
        return False

    if size1 != size2:
        print(f"파일 크기가 다릅니다: {file1_path} ({size1} bytes), {file2_path} ({size2} bytes)")
        return False

    print(f"파일 크기가 동일합니다: {size1} bytes")

    try:
        with open(file1_path, 'rb') as f1, open(file2_path, 'rb') as f2:
            position = 0
            while True:
                chunk1 = f1.read(chunk_size)
                chunk2 = f2.read(chunk_size)

                if not chunk1 and not chunk2:
                    # 두 파일 모두 끝에 도달
                    break
                
                if chunk1 != chunk2:
                    # 어느 위치에서 다른지 찾기
                    for i in range(len(chunk1)):
                        if chunk1[i] != chunk2[i]:
                            print(f"파일 내용이 {position + i} 바이트 위치에서 다릅니다.")
                            return False
                    print("파일 내용이 다릅니다.")
                    return False
                
                position += len(chunk1)

        print("파일 내용이 완전히 동일합니다.")
        return True

    except IOError as e:
        print(f"파일을 읽는 중 오류가 발생했습니다: {e}")
        return False

if __name__ == "__main__":
    file_a = "input.bin"
    file_b = "merged_output.bin"

    if not os.path.exists(file_a):
        print(f"오류: '{file_a}' 파일이 현재 디렉토리에 없습니다.")
    elif not os.path.exists(file_b):
        print(f"오류: '{file_b}' 파일이 현재 디렉토리에 없습니다.")
    else:
        are_files_identical(file_a, file_b)
