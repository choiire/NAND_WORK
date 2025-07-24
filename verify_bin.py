import os
import hashlib

ORIGINAL_FILE = "input.BIN"
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

def verify_files():
    """원본 파일과 병합된 파일의 크기와 해시를 비교하여 검증합니다."""
    print("파일 검증을 시작합니다...")

    # 원본 파일 정보
    print(f"'{ORIGINAL_FILE}' 파일 정보 분석 중...")
    original_size, original_hash = get_file_info(ORIGINAL_FILE)
    if original_size is None:
        return

    # 병합된 파일 정보
    print(f"'{MERGED_FILE}' 파일 정보 분석 중...")
    merged_size, merged_hash = get_file_info(MERGED_FILE)
    if merged_size is None:
        return

    print("-" * 40)
    print(f"| {'파일':<20} | {'크기 (바이트)':>15} |")
    print(f"| {'-'*20} | {'-'*15} |")
    print(f"| {ORIGINAL_FILE:<20} | {original_size:>15,} |")
    print(f"| {MERGED_FILE:<20} | {merged_size:>15,} |")
    print("-" * 40)
    print(f"원본 해시: {original_hash}")
    print(f"병합 해시: {merged_hash}")
    print("-" * 40)

    # 검증
    size_match = (original_size == merged_size)
    hash_match = (original_hash == merged_hash)

    if size_match and hash_match:
        print("✅ 검증 성공: 파일 크기와 해시가 모두 일치합니다.")
    else:
        print("❌ 검증 실패:")
        if not size_match:
            print("  - 파일 크기가 일치하지 않습니다.")
        if not hash_match:
            print("  - 파일 해시가 일치하지 않습니다.")

if __name__ == "__main__":
    verify_files()
