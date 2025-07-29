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
import os
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

def format_hex_output_with_offset(data: bytes, offset: int = 0, bytes_per_line: int = 16) -> str:
    """바이트 데이터를 지정된 오프셋부터 시작하는 16진수 형태로 포맷팅합니다."""
    lines = []
    
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        
        # 주소 표시 (지정된 오프셋부터 시작)
        addr = f"{offset + i:08X}"
        
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
    FULL_PAGE_SIZE = 2112  # 메인 영역 2048 + 스페어 영역 64
    
    print(f"블록 {block_no} 삭제 검증 중...")
    
    try:
        # 첫 페이지와 마지막 페이지만 빠르게 확인
        first_page = block_no * PAGES_PER_BLOCK
        last_page = first_page + PAGES_PER_BLOCK - 1
        
        # 첫 페이지 확인 (전체 페이지 포함 스페어 영역)
        first_data = nand.read_page(first_page, FULL_PAGE_SIZE)
        if not all(b == 0xFF for b in first_data):
            print(f"❌ 첫 페이지 삭제 실패 - 0xFF가 아닌 데이터 발견")
            return False
        
        # 마지막 페이지 확인 (전체 페이지 포함 스페어 영역)
        last_data = nand.read_page(last_page, FULL_PAGE_SIZE)
        if not all(b == 0xFF for b in last_data):
            print(f"❌ 마지막 페이지 삭제 실패 - 0xFF가 아닌 데이터 발견")
            return False
        
        print(f"✅ 블록 {block_no} 삭제 검증 완료")
        return True
        
    except Exception as e:
        print(f"❌ 블록 {block_no} 검증 중 오류: {str(e)}")
        return False

def check_ecc_status_with_message(nand: MT29F4G08ABADAWP, step_name: str):
    """ECC 상태를 확인하고 단계별 메시지와 함께 출력합니다."""
    print(f"\n🔍 {step_name} - ECC 상태 확인:")
    nand.check_ecc_status()

def load_bin_file(file_path: str) -> bytes:
    """bin 파일을 읽어서 바이트 데이터로 반환합니다."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        print(f"✅ 파일 로드 완료: {file_path}")
        print(f"📊 파일 크기: {len(data)} 바이트")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        raise Exception(f"파일 읽기 오류: {str(e)}")

def compare_data(original: bytes, read_back: bytes) -> dict:
    """원본 데이터와 읽어온 데이터를 비교합니다."""
    result = {
        'identical': True,
        'differences': [],
        'original_size': len(original),
        'read_size': len(read_back)
    }
    
    if len(original) != len(read_back):
        result['identical'] = False
        result['size_mismatch'] = True
        return result
    
    differences = []
    for i, (orig, read) in enumerate(zip(original, read_back)):
        if orig != read:
            differences.append({
                'offset': i,
                'original': orig,
                'read_back': read
            })
            result['identical'] = False
    
    result['differences'] = differences[:10]  # 최대 10개만 저장
    result['total_differences'] = len(differences)
    
    return result

def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("NAND 블록 초기화, 파일 쓰기 및 데이터 검증 프로그램")
    print("=" * 80)
    
    # NAND 드라이버 초기화 및 설정
    print("\n🔧 NAND 드라이버 초기화 중...")
    try:
        # Bad Block 스캔을 건너뛰고 빠르게 초기화
        nand = MT29F4G08ABADAWP(skip_bad_block_scan=True)
        print("✅ NAND 드라이버 기본 초기화 완료")
        
        # 파워온 시퀀스 재실행 (안정성 확보)
        print("\n⚡ NAND 칩 파워온 시퀀스 실행 중...")
        nand.power_on_sequence()
        print("✅ 파워온 시퀀스 완료")
        
        # 내부 ECC 상태 확인
        print("\n🔍 현재 ECC 상태 확인 중...")
        nand.check_ecc_status()
        
        # 내부 ECC 비활성화
        print("\n🔧 내부 ECC 비활성화 중...")
        ecc_disable_success = nand.disable_internal_ecc()
        if ecc_disable_success:
            print("✅ 내부 ECC 비활성화 완료")
        else:
            print("⚠️  내부 ECC 비활성화에 실패했지만 계속 진행합니다...")
        
        # ECC 비활성화 후 상태 재확인
        print("\n🔍 ECC 비활성화 후 상태 재확인...")
        nand.check_ecc_status()
        
        print("✅ NAND 칩 초기화 및 설정 완료")
        
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
        
        # 블록 삭제 후 ECC 상태 확인
        check_ecc_status_with_message(nand, "블록 삭제 후")
        
        # 00000000.bin 파일 로드 및 쓰기
        bin_file_path = os.path.join("output_splits", "00000000.bin")
        print(f"\n📂 파일 로드 중: {bin_file_path}")
        
        try:
            original_data = load_bin_file(bin_file_path)
            
            # 데이터 크기 확인 및 조정 (전체 페이지 크기 2112바이트 기준)
            if len(original_data) > 2112:
                print(f"⚠️  파일 크기가 2112바이트를 초과합니다. 처음 2112바이트만 사용합니다.")
                write_data = original_data[:2112]
            elif len(original_data) < 2112:
                print(f"📝 파일 크기가 2112바이트보다 작습니다. 0xFF로 패딩합니다.")
                write_data = original_data + b'\xFF' * (2112 - len(original_data))
            else:
                write_data = original_data
            
            print(f"📊 쓰기 데이터 정보:")
            print(f"   - 전체 크기: {len(write_data)} 바이트")
            print(f"   - 메인 영역: {len(write_data[:2048])} 바이트")
            print(f"   - 스페어 영역: {len(write_data[2048:])} 바이트")
            
            # NAND에 전체 페이지 데이터 쓰기 (메인 + 스페어)
            print(f"\n✍️  블록 {block_no}의 첫 페이지에 전체 데이터 쓰기 중...")
            start_time = time.time()
            nand.write_full_page(first_page, write_data)
            write_time = time.time() - start_time
            print(f"✅ 전체 페이지 데이터 쓰기 완료 (소요 시간: {write_time:.3f}초)")
            
            # 데이터 쓰기 후 ECC 상태 확인
            check_ecc_status_with_message(nand, "데이터 쓰기 후")
            
        except Exception as e:
            print(f"❌ 파일 로드 또는 쓰기 실패: {str(e)}")
            print("📖 삭제된 상태의 페이지를 읽어서 표시합니다...")
            original_data = None
            write_data = None
        
        # 첫 페이지 데이터 읽기
        print(f"\n📖 블록 {block_no}의 첫 페이지 (페이지 {first_page}) 데이터 읽기 중...")
        
        start_time = time.time()
        # 전체 페이지 크기 (2112 바이트 = 메인 2048 + 스페어 64) 읽기
        page_data = nand.read_page(first_page, 2112)
        read_time = time.time() - start_time
        
        print(f"✅ 페이지 데이터 읽기 완료 (소요 시간: {read_time:.3f}초)")
        print(f"📊 읽은 데이터 크기: {len(page_data)} 바이트 (메인 영역: 2048, 스페어 영역: 64)")
        
        # 데이터 읽기 후 ECC 상태 확인
        check_ecc_status_with_message(nand, "데이터 읽기 후")
        
        # 데이터 검증 (원본 파일과 비교) - 전체 페이지 비교
        if original_data is not None and write_data is not None:
            print(f"\n🔍 전체 페이지 데이터 검증 중...")
            comparison = compare_data(write_data, page_data)
            
            if comparison['identical']:
                print("✅ 데이터 검증 성공: 쓴 데이터와 읽은 데이터가 완전히 일치합니다!")
                print("   - 메인 영역 (2048 바이트): 일치")
                print("   - 스페어 영역 (64 바이트): 일치")
            else:
                print(f"❌ 데이터 검증 실패: {comparison['total_differences']}개의 차이점 발견")
                if comparison.get('size_mismatch'):
                    print(f"   크기 불일치: 원본 {comparison['original_size']}, 읽음 {comparison['read_size']}")
                else:
                    # 메인 영역과 스페어 영역별로 차이점 분석
                    main_diffs = [d for d in comparison['differences'] if d['offset'] < 2048]
                    spare_diffs = [d for d in comparison['differences'] if d['offset'] >= 2048]
                    
                    print(f"   - 메인 영역 차이점: {len([d for d in comparison['differences'] if d['offset'] < 2048])}개")
                    print(f"   - 스페어 영역 차이점: {len([d for d in comparison['differences'] if d['offset'] >= 2048])}개")
                    print("\n   첫 10개 차이점:")
                    for diff in comparison['differences'][:10]:
                        area = "메인" if diff['offset'] < 2048 else "스페어"
                        print(f"     오프셋 0x{diff['offset']:04X} ({area}): 원본=0x{diff['original']:02X}, 읽음=0x{diff['read_back']:02X}")
                    if comparison['total_differences'] > 10:
                        print(f"     ... 및 {comparison['total_differences'] - 10}개 더")
        
        # 16진수 출력 (메인과 스페어 영역 통합)
        print(f"\n" + "=" * 80)
        print(f"블록 {block_no}, 페이지 {first_page} 데이터 (16진수 출력) - 전체 2112 바이트")
        print("=" * 80)
        print("주소     : 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  |ASCII 문자|")
        print("-" * 80)
        
        # 전체 데이터를 통합해서 표시
        hex_output_full = format_hex_output(page_data)
        print(hex_output_full)
        
        # 영역 구분선 표시
        print(f"\n{'='*80}")
        print("📋 영역 구분 정보:")
        print(f"🔵 메인 영역: 0x000000 - 0x0007FF (2048 바이트)")
        print(f"🟡 스페어 영역: 0x000800 - 0x00083F (64 바이트)")
        print("="*80)
        
        # 데이터 통계
        print("\n" + "=" * 80)
        print("📈 데이터 통계")
        print("=" * 80)
        
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
        
        # 프로그램 종료 전 최종 ECC 상태 확인
        check_ecc_status_with_message(nand, "프로그램 종료 전 최종")
        
        print("\n✅ 프로그램 실행 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        # 오류 발생 시에도 ECC 상태 확인
        try:
            check_ecc_status_with_message(nand, "오류 발생 시")
        except:
            pass
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