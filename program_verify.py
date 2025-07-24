import os
from nand_driver import MT29F4G08ABADAWP

def hex_to_int(hex_str):
    """16진수 문자열을 정수로 변환"""
    return int(hex_str, 16)

def main():
    # NAND 플래시 드라이버 초기화
    nand = MT29F4G08ABADAWP()
    
    # output_splits 폴더의 모든 .bin 파일 읽기
    splits_dir = "output_splits"
    files = sorted([f for f in os.listdir(splits_dir) if f.endswith('.bin')])
    
    # 각 파일에 대해
    for filename in files:
        # 파일 이름에서 바이트 오프셋 추출 (예: 00000840.bin -> 0x840)
        byte_offset = hex_to_int(filename.split('.')[0])
        # 페이지 크기 (2,048 + 64 = 0x840)
        PAGE_SIZE = 0x840
        page_no = byte_offset // PAGE_SIZE  # Row Address
        
        print(f"프로그래밍 페이지 {page_no} (offset 0x{byte_offset:X})...")
        
        # 파일 읽기
        with open(os.path.join(splits_dir, filename), 'rb') as f:
            data = f.read()
            
        # 페이지 프로그래밍
        nand.write_page(page_no, data)
        
        # 검증을 위해 다시 읽기
        read_data = nand.read_page(page_no, len(data))
        
        # 데이터 비교
        if read_data == data:
            print(f"페이지 {page_no} 검증 성공")
        else:
            print(f"페이지 {page_no} 검증 실패!")
            # 실패한 경우 첫 번째 불일치 바이트 출력
            for i, (w, r) in enumerate(zip(data, read_data)):
                if w != r:
                    print(f"  오프셋 {i}: 쓰기 0x{w:02X} != 읽기 0x{r:02X}")
                    break
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n프로그램 중단")
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        # GPIO 정리
        import RPi.GPIO as GPIO
        GPIO.cleanup() 