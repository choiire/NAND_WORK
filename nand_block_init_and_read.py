#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NAND 블록 초기화 및 첫 번째 블록의 첫 페이지 데이터 읽기 프로그램

이 프로그램은:
1. NAND 드라이버를 초기화합니다
2. 첫 번째 블록을 삭제(초기화)합니다
3. 첫 번째 블록의 첫 페이지 데이터를 읽어서 16진수로 출력합니다
"""

import sys
import time
from datetime import datetime
from nand_driver import MT29F4G08ABADAWP

def format_hex_output(data: bytes, bytes_per_line: int = 16) -> str:
    """바이트 데이터를 보기 좋은 16진수 형태로 포맷팅합니다."""
    lines = []
    
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        
        # 주소 표시 (오프셋)
        addr = f"{i:08X}"
        
        # 16진수 바이트들
        hex_bytes = " ".join(f"{b:02X}" for b in chunk)
        
        # ASCII 문자 (출력 가능한 문자만)
        ascii_chars = ""
        for b in chunk:
            if 32 <= b <= 126:  # 출력 가능한 ASCII 문자
                ascii_chars += chr(b)
            else:
                ascii_chars += "."
        
        # 라인 포맷: 주소 | 16진수 바이트들 | ASCII 문자들
        line = f"{addr}  {hex_bytes:<47} |{ascii_chars}|"
        lines.append(line)
    
    return "\n".join(lines)

def verify_block_erased(nand: MT29F4G08ABADAWP, block_no: int) -> bool:
    """블록이 제대로 삭제되었는지 확인합니다 (모든 바이트가 0xFF인지 확인)."""
    PAGES_PER_BLOCK = 64
    PAGE_SIZE = 2048
    
    print(f"블록 {block_no} 삭제 검증 중...")
    
    try:
        # 첫 페이지와 마지막 페이지만 빠르게 확인
        first_page = block_no * PAGES_PER_BLOCK
        last_page = first_page + PAGES_PER_BLOCK - 1
        
        # 첫 페이지 확인
        first_data = nand.read_page(first_page, PAGE_SIZE)
        if not all(b == 0xFF for b in first_data):
            print(f"❌ 첫 페이지 삭제 실패 - 0xFF가 아닌 데이터 발견")
            return False
        
        # 마지막 페이지 확인
        last_data = nand.read_page(last_page, PAGE_SIZE)
        if not all(b == 0xFF for b in last_data):
            print(f"❌ 마지막 페이지 삭제 실패 - 0xFF가 아닌 데이터 발견")
            return False
        
        print(f"✅ 블록 {block_no} 삭제 검증 완료")
        return True
        
    except Exception as e:
        print(f"❌ 블록 {block_no} 검증 중 오류: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print("=" * 70)
    print("NAND 블록 초기화 및 첫 페이지 데이터 읽기 프로그램")
    print("=" * 70)
    
    # NAND 드라이버 초기화
    print("\n🔧 NAND 드라이버 초기화 중...")
    try:
        # Bad Block 스캔을 건너뛰고 빠르게 초기화
        nand = MT29F4G08ABADAWP(skip_bad_block_scan=True)
        print("✅ NAND 드라이버 초기화 완료")
    except Exception as e:
        print(f"❌ NAND 드라이버 초기화 실패: {str(e)}")
        sys.exit(1)
    
    try:
        # 블록 0번 초기화 (삭제)
        print("\n🗑️  블록 0 초기화 중...")
        block_no = 0
        first_page = block_no * 64  # 첫 번째 블록의 첫 페이지 (페이지 0)
        
        start_time = time.time()
        nand.erase_block(first_page)
        erase_time = time.time() - start_time
        
        print(f"✅ 블록 {block_no} 삭제 완료 (소요 시간: {erase_time:.3f}초)")
        
        # 삭제 검증
        if not verify_block_erased(nand, block_no):
            print("⚠️  블록 삭제 검증에 실패했지만 계속 진행합니다...")
        
        # 첫 페이지 데이터 읽기
        print(f"\n📖 블록 {block_no}의 첫 페이지 (페이지 {first_page}) 데이터 읽기 중...")
        
        start_time = time.time()
        # 전체 페이지 크기 (2048 바이트) 읽기
        page_data = nand.read_page(first_page, 2048)
        read_time = time.time() - start_time
        
        print(f"✅ 페이지 데이터 읽기 완료 (소요 시간: {read_time:.3f}초)")
        print(f"📊 읽은 데이터 크기: {len(page_data)} 바이트")
        
        # 16진수 출력
        print(f"\n" + "=" * 70)
        print(f"블록 {block_no}, 페이지 {first_page} 데이터 (16진수 출력)")
        print("=" * 70)
        print("주소     : 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  |ASCII 문자|")
        print("-" * 70)
        
        hex_output = format_hex_output(page_data)
        print(hex_output)
        
        # 데이터 통계
        print("\n" + "=" * 70)
        print("📈 데이터 통계")
        print("=" * 70)
        
        # 바이트 값별 개수 계산
        byte_counts = {}
        for byte_val in page_data:
            byte_counts[byte_val] = byte_counts.get(byte_val, 0) + 1
        
        # 0xFF의 개수 확인 (삭제된 상태라면 모두 0xFF여야 함)
        ff_count = byte_counts.get(0xFF, 0)
        total_bytes = len(page_data)
        
        print(f"총 바이트 수: {total_bytes}")
        print(f"0xFF 바이트 수: {ff_count} ({(ff_count/total_bytes)*100:.1f}%)")
        
        if ff_count == total_bytes:
            print("✅ 모든 바이트가 0xFF입니다 (정상적으로 삭제된 상태)")
        else:
            print(f"⚠️  {total_bytes - ff_count}개 바이트가 0xFF가 아닙니다")
            
            # 0xFF가 아닌 바이트들의 값과 개수 표시 (상위 10개만)
            non_ff_counts = {k: v for k, v in byte_counts.items() if k != 0xFF}
            if non_ff_counts:
                print("\n0xFF가 아닌 바이트 값들:")
                sorted_counts = sorted(non_ff_counts.items(), key=lambda x: x[1], reverse=True)
                for byte_val, count in sorted_counts[:10]:
                    print(f"  0x{byte_val:02X}: {count}개")
                if len(sorted_counts) > 10:
                    print(f"  ... 및 {len(sorted_counts) - 10}개 더")
        
        print("\n✅ 프로그램 실행 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        sys.exit(1)
    
    finally:
        # 안전한 종료
        try:
            print("\n🔧 NAND 드라이버 정리 중...")
            del nand
            print("✅ 정리 완료")
        except:
            pass

if __name__ == "__main__":
    main() 