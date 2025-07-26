import os
import sys
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str: str) -> int:
    """16진수 문자열을 정수로 변환"""
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ValueError(f"잘못된 파일명 형식: {hex_str}")

def validate_block_number(block_no: int) -> bool:
    """블록 번호 유효성 검사"""
    return 0 <= block_no < 4096  # 4Gb = 4096 blocks

def validate_file_size(filepath: str) -> int:
    """파일 크기 유효성 검사"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"파일을 찾을 수 없음: {filepath}")
        
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValueError(f"파일이 비어있음: {filepath}")
        
    # ECC 오버헤드를 고려한 최대 크기 계산
    max_size = 2048 + 64 + ((2048 // 256) * 32)  # 데이터 + 스페어 + ECC
    if file_size > max_size:
        raise ValueError(f"파일 크기가 너무 큼: {filepath} ({file_size} bytes)")
        
    return file_size

def calculate_block_number(address: int) -> int:
    """주소를 블록 번호로 변환"""
    # NAND 플래시 전체 크기로 마스킹 (4Gb = 512MB = 0x20000000)
    NAND_SIZE_MASK = 0x1FFFFFFF
    masked_address = address & NAND_SIZE_MASK
    
    # 블록 크기 = 페이지 크기(0x800 = 2KB) * 페이지 수(64)
    block_no = masked_address // (0x800 * 64)
    if not validate_block_number(block_no):
        raise ValueError(
            f"주소 0x{address:08X}(마스킹 후: 0x{masked_address:08X})에서 "
            f"계산된 블록 번호({block_no})가 유효하지 않습니다"
        )
    return block_no

def calculate_page_number(address: int) -> int:
    """주소를 페이지 번호로 변환"""
    # NAND 플래시 전체 크기로 마스킹
    NAND_SIZE_MASK = 0x1FFFFFFF
    masked_address = address & NAND_SIZE_MASK
    
    # 페이지 번호 계산 (2KB = 0x800 단위)
    page_no = masked_address // 0x800
    if page_no >= 256 * 1024:  # 4Gb = 256K 페이지
        raise ValueError(f"유효하지 않은 페이지 번호: {page_no}")
    return page_no

def validate_directory(dirpath: str) -> None:
    """디렉토리 유효성 검사"""
    if not os.path.exists(dirpath):
        raise NotADirectoryError(f"디렉토리를 찾을 수 없음: {dirpath}")
    if not os.path.isdir(dirpath):
        raise NotADirectoryError(f"유효한 디렉토리가 아님: {dirpath}")

def erase_all_blocks(nand):
    """전체 블록 삭제"""
    TOTAL_BLOCKS = 4096  # 4Gb = 4096 blocks
    MAX_RETRIES = 3
    
    start_datetime = datetime.now()
    print(f"\n=== 전체 블록 삭제 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {TOTAL_BLOCKS}개 블록 삭제 예정")
    
    failed_blocks = []
    
    try:
        for block in range(TOTAL_BLOCKS):
            if nand.is_bad_block(block):
                print(f"\n블록 {block}은 Bad Block으로 표시되어 있어 건너뜁니다.")
                continue
                
            # 각 블록의 첫 페이지 번호 계산 (블록당 64페이지)
            page_no = block * 64
            
            # 최대 3번 재시도
            for retry in range(MAX_RETRIES):
                try:
                    nand.erase_block(page_no)
                    break
                except Exception as e:
                    if retry == MAX_RETRIES - 1:
                        print(f"\n블록 {block} 삭제 실패 (최대 재시도 횟수 초과)")
                        failed_blocks.append(block)
                        nand.mark_bad_block(block)
                    else:
                        print(f"\n블록 {block} 삭제 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
            
            if (block + 1) % 10 == 0:  # 10블록마다 진행상황 출력
                sys.stdout.write(f"\r블록 삭제 중: {block + 1}/{TOTAL_BLOCKS} 블록")
                sys.stdout.flush()
        
        if failed_blocks:
            print(f"\n삭제 실패한 블록들: {failed_blocks}")
        print("\n전체 블록 삭제 완료")
        
    except Exception as e:
        print(f"\n블록 삭제 중 오류 발생: {str(e)}")
        raise

def program_nand():
    try:
        # NAND 드라이버 초기화
        nand = MT29F4G08ABADAWP()
        
        # output_splits 디렉토리 검증
        splits_dir = "output_splits"
        validate_directory(splits_dir)
        
        # 파일 목록 가져오기 및 정렬
        files = [f for f in os.listdir(splits_dir) if f.endswith('.bin')]
        if not files:
            raise ValueError(f"프로그래밍할 파일이 없음: {splits_dir}")
        files.sort()
        
        # 전체 블록 삭제
        erase_all_blocks(nand)
        
        total_files = len(files)
        processed_files = 0
        failed_files = []
        MAX_RETRIES = 3
        
        start_datetime = datetime.now()
        print(f"\n=== 프로그래밍 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"총 {total_files}개 파일 프로그래밍 예정")
        
        for filename in files:
            try:
                # 파일 검증
                filepath = os.path.join(splits_dir, filename)
                validate_file_size(filepath)
                
                # 주소 계산
                address = hex_to_int(filename.split('.')[0])
                page_no = calculate_page_number(address)
                block_no = page_no // 64
                
                # Bad Block 체크 및 대체 블록 찾기
                if nand.is_bad_block(block_no):
                    new_block = nand.find_good_block(block_no + 1)
                    print(f"\n블록 {block_no}이 Bad Block입니다. 대체 블록 {new_block}을 사용합니다.")
                    page_no = new_block * 64 + (page_no % 64)
                
                # 데이터 읽기
                with open(filepath, 'rb') as f:
                    data = f.read()
                
                # 최대 3번 재시도
                success = False
                for retry in range(MAX_RETRIES):
                    try:
                        nand.write_page(page_no, data)
                        success = True
                        break
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n파일 '{filename}' 프로그래밍 실패 (최대 재시도 횟수 초과): {str(e)}")
                            failed_files.append(filename)
                            nand.mark_bad_block(block_no)
                        else:
                            print(f"\n파일 '{filename}' 프로그래밍 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                
                if success:
                    processed_files += 1
                    sys.stdout.write(f"\r작업 중: {processed_files}/{total_files} - {filename}")
                    sys.stdout.flush()
                
            except Exception as e:
                print(f"\n파일 '{filename}' 프로그래밍 중 오류 발생: {str(e)}")
                failed_files.append(filename)
        
        end_datetime = datetime.now()
        duration = end_datetime - start_datetime
        print(f"\n\n프로그래밍 완료 (소요 시간: {duration})")
        
        if failed_files:
            print(f"\n프로그래밍 실패한 파일들: {failed_files}")
            return False
        return True
        
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    program_nand() 