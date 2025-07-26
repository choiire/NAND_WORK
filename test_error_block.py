# 오류 블록 테스트
# 블록 삭제 후 데이터 쓰기 후 검증

import os
import sys
import time
from nand_driver import MT29F4G08ABADAWP

def test_block(block_no: int, nand: MT29F4G08ABADAWP):
    """특정 블록 테스트"""
    block_start_page = block_no * 64
    
    print(f"\n=== 블록 {block_no} 테스트 시작 (시작 페이지: {block_start_page}) ===")
    
    try:
        # Bad Block 체크
        if nand.is_bad_block(block_no):
            print(f"블록 {block_no}은 이미 Bad Block으로 표시되어 있습니다.")
            return False
            
        # 1. 블록 삭제
        print("\n1. 블록 삭제 시작")
        MAX_RETRIES = 3
        erase_success = False
        
        for retry in range(MAX_RETRIES):
            try:
                nand.erase_block(block_start_page)
                erase_success = True
                break
            except Exception as e:
                if retry == MAX_RETRIES - 1:
                    print(f"블록 삭제 실패 (최대 재시도 횟수 초과): {str(e)}")
                    nand.mark_bad_block(block_no)
                    return False
                else:
                    print(f"블록 삭제 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                    time.sleep(0.1)
        
        if erase_success:
            print("블록 삭제 완료")
        
        # 2. 블록 삭제 확인
        print("\n2. 블록 삭제 확인")
        for page_offset in range(64):
            page_no = block_start_page + page_offset
            
            # 타임아웃 설정
            timeout_start = time.time()
            while True:
                try:
                    data = nand.read_page(page_no)
                    break
                except Exception as e:
                    if time.time() - timeout_start > 5:  # 5초 타임아웃
                        print(f"페이지 {page_no} 읽기 타임아웃")
                        return False
                    time.sleep(0.1)
            
            # 모든 바이트가 0xFF인지 확인
            if not all(b == 0xFF for b in data):
                print(f"경고: 페이지 {page_no}가 완전히 지워지지 않았습니다!")
                non_ff = [i for i, b in enumerate(data) if b != 0xFF][:5]
                for i in non_ff:
                    print(f"  오프셋 0x{i:04X}: 0x{data[i]:02X} (예상: 0xFF)")
                nand.mark_bad_block(block_no)
                return False
        
        # 3. 데이터 쓰기
        print("\n3. 데이터 쓰기 시작")
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):
                page_no = block_start_page + page_offset
                page_addr = page_no * 0x800
                
                # 파일 포인터를 해당 페이지의 위치로 이동
                f.seek(page_addr)
                page_data = f.read(2048)
                
                sys.stdout.write(f"\r페이지 쓰기 중: {page_offset + 1}/64 (주소: 0x{page_addr:08X})")
                sys.stdout.flush()
                
                # 최대 3번 재시도
                write_success = False
                for retry in range(MAX_RETRIES):
                    try:
                        nand.write_page(page_no, page_data)
                        write_success = True
                        break
                    except Exception as e:
                        if retry == MAX_RETRIES - 1:
                            print(f"\n페이지 {page_no} 쓰기 실패 (최대 재시도 횟수 초과): {str(e)}")
                            nand.mark_bad_block(block_no)
                            return False
                        else:
                            print(f"\n페이지 {page_no} 쓰기 실패, 재시도 중... ({retry + 1}/{MAX_RETRIES})")
                            time.sleep(0.1)
                
                if not write_success:
                    return False
                    
        print("\n데이터 쓰기 완료")
        
        # 4. 데이터 검증
        print("\n4. 데이터 검증 시작")
        errors = []
        
        with open('input.bin', 'rb') as f:
            for page_offset in range(64):
                page_no = block_start_page + page_offset
                page_addr = page_no * 0x800
                
                # 파일 포인터를 해당 페이지의 위치로 이동
                f.seek(page_addr)
                expected_data = f.read(2048)
                
                # 타임아웃 설정
                timeout_start = time.time()
                while True:
                    try:
                        actual_data = nand.read_page(page_no)
                        break
                    except Exception as e:
                        if time.time() - timeout_start > 5:  # 5초 타임아웃
                            print(f"\n페이지 {page_no} 읽기 타임아웃")
                            return False
                        time.sleep(0.1)
                
                sys.stdout.write(f"\r페이지 검증 중: {page_offset + 1}/64 (주소: 0x{page_addr:08X})")
                sys.stdout.flush()
                
                if actual_data != expected_data:
                    # 불일치하는 바이트 위치 찾기
                    mismatch_positions = []
                    for i in range(len(actual_data)):
                        if actual_data[i] != expected_data[i]:
                            mismatch_positions.append({
                                'offset': page_addr + i,
                                'expected': expected_data[i],
                                'actual': actual_data[i]
                            })
                    
                    if mismatch_positions:
                        errors.append({
                            'page': page_no,
                            'address': f"0x{page_addr:08X}",
                            'mismatches': mismatch_positions[:10]
                        })
        
        print("\n검증 완료")
        
        # 결과 출력
        if not errors:
            print("\n결과: 모든 데이터 일치")
            return True
        else:
            print(f"\n결과: {len(errors)}개 페이지에서 오류 발견")
            for error in errors:
                print(f"\n페이지 {error['page']} (주소: {error['address']}):")
                for mismatch in error['mismatches']:
                    print(f"  오프셋 0x{mismatch['offset']:08X}: "
                          f"예상값 0x{mismatch['expected']:02X}, "
                          f"실제값 0x{mismatch['actual']:02X}")
            nand.mark_bad_block(block_no)
            return False
            
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        nand.mark_bad_block(block_no)
        return False

def test_error_blocks():
    """여러 블록 테스트"""
    try:
        nand = MT29F4G08ABADAWP()
        
        # 테스트할 블록 목록
        test_blocks = [0, 1, 2, 3, 4]  # 처음 5개 블록 테스트
        results = {}
        
        for block_no in test_blocks:
            print(f"\n{'='*80}")
            print(f"블록 {block_no} 테스트 시작")
            result = test_block(block_no, nand)
            results[block_no] = result
            print(f"블록 {block_no} 테스트 {'성공' if result else '실패'}")
        
        # 최종 결과 출력
        print("\n=== 테스트 결과 요약 ===")
        success_count = sum(1 for r in results.values() if r)
        fail_count = len(results) - success_count
        
        print(f"총 테스트 블록 수: {len(results)}")
        print(f"성공: {success_count}")
        print(f"실패: {fail_count}")
        
        if fail_count > 0:
            print("\n실패한 블록:")
            for block_no, result in results.items():
                if not result:
                    print(f"- 블록 {block_no}")
        
        return fail_count == 0
        
    except Exception as e:
        print(f"\n치명적 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    test_error_blocks() 