import os
import time
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

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

def verify_nand():
    # NAND 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # input.bin 파일 열기
    with open('input.bin', 'rb') as f:
        input_data = f.read()
    
    # 전체 크기 (528MB = 528 * 1024 * 1024 바이트)
    total_size = len(input_data)
    pages_to_verify = total_size // 2048  # 2KB 단위로 나누기
    
    start_datetime = datetime.now()
    print(f"\n=== 검증 시작 (시작 시간: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"총 {pages_to_verify}개 페이지 검증 예정")
    start_time = time.time()
    
    errors = []
    verified_pages = 0
    
    for page_no in range(pages_to_verify):
        # 입력 파일에서의 오프셋 계산
        offset = page_no * 2048
        expected_data = input_data[offset:offset + 2048]
        
        try:
            # NAND에서 페이지 읽기
            actual_data = nand.read_page(page_no)
            
            # 데이터 비교
            if actual_data != expected_data:
                # 불일치하는 바이트 위치 찾기
                mismatch_positions = []
                for i in range(len(actual_data)):
                    if actual_data[i] != expected_data[i]:
                        mismatch_positions.append({
                            'offset': offset + i,
                            'expected': expected_data[i],
                            'actual': actual_data[i]
                        })
                
                if mismatch_positions:
                    errors.append({
                        'page': page_no,
                        'address': f"0x{(page_no * 0x800):08X}",
                        'mismatches': mismatch_positions[:10]  # 처음 10개의 오류만 저장
                    })
            
            verified_pages += 1
            
            # 1000페이지마다 진행상황 출력
            if verified_pages % 1000 == 0:
                elapsed_time = time.time() - start_time
                pages_per_sec = verified_pages / elapsed_time
                remaining_pages = pages_to_verify - verified_pages
                estimated_remaining = remaining_pages / pages_per_sec
                
                print(f"\n검증 중: {verified_pages}/{pages_to_verify} 페이지")
                print(f"현재 주소: 0x{(page_no * 0x800):08X}")
                print(f"예상 남은 시간: {format_time(int(estimated_remaining))}")
                
        except Exception as e:
            print(f"오류 발생 - 페이지: {page_no}")
            print(f"오류 내용: {str(e)}")
            return False
    
    total_time = time.time() - start_time
    end_datetime = datetime.now()
    
    # 결과 출력
    if not errors:
        print(f"\n=== 검증 완료 (완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"결과: 모든 데이터 일치")
        print(f"총 소요시간: {format_time(int(total_time))}")
        return True
    else:
        print(f"\n=== 검증 완료 (완료 시간: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}) ===")
        print(f"결과: {len(errors)}개 페이지에서 오류 발견")
        print(f"총 소요시간: {format_time(int(total_time))}")
        # 처음 5개의 오류만 상세 출력
        for error in errors[:5]:
            print(f"\n페이지 {error['page']} (주소: {error['address']}):")
            for mismatch in error['mismatches']:
                print(f"  오프셋 0x{mismatch['offset']:08X}: "
                      f"예상값 0x{mismatch['expected']:02X}, "
                      f"실제값 0x{mismatch['actual']:02X}")
        if len(errors) > 5:
            print(f"\n... 외 {len(errors)-5}개 페이지에서 오류 발생")
        return False

if __name__ == "__main__":
    verify_nand() 