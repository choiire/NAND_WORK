import os
import hashlib

ORIGINAL_FILE = "input.bin"
MERGED_FILE = "merged_output.bin"

def get_file_info(file_path):
    """파일의 크기와 SHA-256 해시를 반환합니다."""
    if not os.path.exists(file_path):
        print(f"오류: 파일 '{file_path}'을(를) 찾을 수 없습니다.")
        return None, None

    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        file_size = os.path.getsize(file_path)
        return file_size, file_hash
    except Exception as e:
        print(f"'{file_path}' 파일 정보 읽기 중 오류 발생: {e}")
        return None, None

def are_files_identical(file1_path, file2_path, chunk_size=8192):
    """두 파일이 바이트 단위로 동일한지 비교합니다."""
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
                    break
                
                if chunk1 != chunk2:
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

def verify_files():
    """원본 파일과 병합된 파일을 검증합니다."""
    print("\n=== 파일 검증 시작 ===\n")

    # 1. 해시 기반 검증
    print("1. 해시 기반 검증")
    print("-" * 40)
    
    original_size, original_hash = get_file_info(ORIGINAL_FILE)
    if original_size is None:
        return

    merged_size, merged_hash = get_file_info(MERGED_FILE)
    if merged_size is None:
        return

    print(f"| {'파일':<20} | {'크기 (바이트)':>15} |")
    print(f"| {'-'*20} | {'-'*15} |")
    print(f"| {ORIGINAL_FILE:<20} | {original_size:>15,} |")
    print(f"| {MERGED_FILE:<20} | {merged_size:>15,} |")
    print("-" * 40)
    print(f"원본 해시: {original_hash}")
    print(f"병합 해시: {merged_hash}")
    print("-" * 40)

    size_match = (original_size == merged_size)
    hash_match = (original_hash == merged_hash)

    if size_match and hash_match:
        print("✅ 해시 검증 성공: 파일 크기와 해시가 모두 일치합니다.")
    else:
        print("❌ 해시 검증 실패:")
        if not size_match:
            print("  - 파일 크기가 일치하지 않습니다.")
        if not hash_match:
            print("  - 파일 해시가 일치하지 않습니다.")

    # 2. 바이트 단위 검증
    print("\n2. 바이트 단위 검증")
    print("-" * 40)
    are_files_identical(ORIGINAL_FILE, MERGED_FILE)

if __name__ == "__main__":
    verify_files() 