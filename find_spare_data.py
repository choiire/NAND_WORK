#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NAND Flash Spare Area Data Finder

output_splits 폴더의 파일들에서 스페어 영역(Spare Area)에 
0xFF가 아닌 데이터가 포함된 파일을 찾는 도구입니다.

NAND 구조:
- 전체 페이지 크기: 2112 바이트
- 메인 영역: 0~2047 바이트 (2048 바이트)  
- 스페어 영역: 2048~2111 바이트 (64 바이트)
"""

import os
import sys
from pathlib import Path

# NAND 플래시 상수
PAGE_SIZE = 2048  # 메인 데이터 영역 크기
SPARE_SIZE = 64   # 스페어 영역 크기  
TOTAL_PAGE_SIZE = PAGE_SIZE + SPARE_SIZE  # 전체 페이지 크기: 2112 바이트

# 스페어 영역 시작 오프셋
SPARE_OFFSET = PAGE_SIZE

def analyze_spare_area(file_path):
    """
    파일의 스페어 영역을 분석하여 0xFF가 아닌 데이터가 있는지 확인합니다.
    
    Args:
        file_path (str): 분석할 파일 경로
    
    Returns:
        tuple: (has_non_ff_data, spare_data, non_ff_positions)
            - has_non_ff_data: 0xFF가 아닌 데이터가 있는지 여부
            - spare_data: 스페어 영역 전체 데이터 (64바이트)
            - non_ff_positions: 0xFF가 아닌 바이트의 위치 리스트
    """
    try:
        with open(file_path, 'rb') as f:
            # 파일 크기 확인
            f.seek(0, 2)  # 파일 끝으로 이동
            file_size = f.tell()
            
            if file_size < TOTAL_PAGE_SIZE:
                print(f"경고: {file_path} - 파일 크기가 예상보다 작습니다 ({file_size} < {TOTAL_PAGE_SIZE})")
                return False, b'', []
            
            # 스페어 영역으로 이동하여 데이터 읽기
            f.seek(SPARE_OFFSET)
            spare_data = f.read(SPARE_SIZE)
            
            if len(spare_data) < SPARE_SIZE:
                print(f"경고: {file_path} - 스페어 영역 데이터가 부족합니다 ({len(spare_data)} < {SPARE_SIZE})")
                return False, spare_data, []
            
            # 0xFF가 아닌 바이트 위치 찾기
            non_ff_positions = []
            for i, byte in enumerate(spare_data):
                if byte != 0xFF:
                    non_ff_positions.append(i)
            
            has_non_ff_data = len(non_ff_positions) > 0
            
            return has_non_ff_data, spare_data, non_ff_positions
            
    except Exception as e:
        print(f"오류: {file_path} 분석 중 문제 발생 - {e}")
        return False, b'', []

def format_hex_data(data, positions=None, bytes_per_line=16):
    """
    바이너리 데이터를 16진수 형태로 포맷팅합니다.
    
    Args:
        data (bytes): 포맷팅할 바이너리 데이터
        positions (list): 강조할 위치들 (0xFF가 아닌 바이트 위치)
        bytes_per_line (int): 한 줄에 표시할 바이트 수
    
    Returns:
        str: 포맷팅된 16진수 문자열
    """
    if not data:
        return "데이터 없음"
    
    result = []
    for i in range(0, len(data), bytes_per_line):
        # 주소 표시
        addr = f"{i:04X}: "
        
        # 16진수 데이터
        hex_bytes = []
        ascii_chars = []
        
        for j in range(bytes_per_line):
            if i + j < len(data):
                byte = data[i + j]
                
                # 0xFF가 아닌 바이트는 강조 표시
                if positions and (i + j) in positions:
                    hex_bytes.append(f"[{byte:02X}]")
                else:
                    hex_bytes.append(f"{byte:02X}")
                
                # ASCII 문자 (출력 가능한 문자만)
                if 32 <= byte <= 126:
                    ascii_chars.append(chr(byte))
                else:
                    ascii_chars.append('.')
            else:
                hex_bytes.append("  ")
                ascii_chars.append(" ")
        
        # 16진수 부분 (8바이트씩 공백으로 구분)
        hex_part1 = " ".join(hex_bytes[:8])
        hex_part2 = " ".join(hex_bytes[8:])
        hex_line = f"{hex_part1}  {hex_part2}"
        
        # ASCII 부분
        ascii_line = "".join(ascii_chars)
        
        result.append(f"{addr}{hex_line:<48} |{ascii_line}|")
    
    return "\n".join(result)

def find_files_with_spare_data(directory="output_splits"):
    """
    지정된 디렉토리에서 스페어 영역에 0xFF가 아닌 데이터가 있는 파일들을 찾습니다.
    
    Args:
        directory (str): 검색할 디렉토리 경로
    
    Returns:
        list: 조건에 맞는 파일들의 정보 리스트
    """
    if not os.path.exists(directory):
        print(f"오류: 디렉토리 '{directory}'를 찾을 수 없습니다.")
        return []
    
    bin_files = list(Path(directory).glob("*.bin"))
    if not bin_files:
        print(f"'{directory}' 디렉토리에 .bin 파일이 없습니다.")
        return []
    
    print(f"'{directory}' 디렉토리에서 {len(bin_files)}개의 .bin 파일을 검사합니다...")
    print("=" * 80)
    
    files_with_spare_data = []
    
    for file_path in sorted(bin_files):
        has_non_ff, spare_data, non_ff_positions = analyze_spare_area(file_path)
        
        if has_non_ff:
            files_with_spare_data.append({
                'file_path': file_path,
                'spare_data': spare_data,
                'non_ff_positions': non_ff_positions,
                'non_ff_count': len(non_ff_positions)
            })
    
    return files_with_spare_data

def print_detailed_results(files_with_spare_data):
    """
    상세한 분석 결과를 출력합니다.
    
    Args:
        files_with_spare_data (list): 스페어 데이터가 있는 파일들의 정보
    """
    if not files_with_spare_data:
        print("스페어 영역에 0xFF가 아닌 데이터가 있는 파일을 찾지 못했습니다.")
        return
    
    print(f"\n스페어 영역에 0xFF가 아닌 데이터가 있는 파일: {len(files_with_spare_data)}개")
    print("=" * 80)
    
    for i, file_info in enumerate(files_with_spare_data, 1):
        file_path = file_info['file_path']
        spare_data = file_info['spare_data']
        non_ff_positions = file_info['non_ff_positions']
        non_ff_count = file_info['non_ff_count']
        
        print(f"\n[{i}] 파일: {file_path.name}")
        print(f"    - 0xFF가 아닌 바이트 수: {non_ff_count}개")
        print(f"    - 위치: {non_ff_positions}")
        
        # 스페어 영역 전체 데이터 출력
        print(f"    - 스페어 영역 데이터 (64바이트):")
        hex_output = format_hex_data(spare_data, non_ff_positions)
        for line in hex_output.split('\n'):
            print(f"      {line}")
        
        print("-" * 80)

def print_summary_results(files_with_spare_data):
    """
    요약 결과를 출력합니다.
    
    Args:
        files_with_spare_data (list): 스페어 데이터가 있는 파일들의 정보
    """
    if not files_with_spare_data:
        print("✓ 모든 파일의 스페어 영역이 0xFF로 채워져 있습니다.")
        return
    
    print(f"\n📋 요약 결과")
    print("=" * 50)
    print(f"스페어 영역에 데이터가 있는 파일: {len(files_with_spare_data)}개")
    
    # 파일명만 간단히 나열
    for file_info in files_with_spare_data:
        file_name = file_info['file_path'].name
        non_ff_count = file_info['non_ff_count']
        print(f"  • {file_name} ({non_ff_count}개 바이트)")

def main():
    """메인 함수"""
    print("NAND Flash Spare Area Data Finder")
    print("=" * 50)
    print(f"페이지 크기: {TOTAL_PAGE_SIZE} 바이트 (메인 {PAGE_SIZE} + 스페어 {SPARE_SIZE})")
    print(f"스페어 영역 오프셋: {SPARE_OFFSET} (0x{SPARE_OFFSET:04X})")
    print()
    
    # 명령행 인자로 디렉토리 지정 가능
    directory = sys.argv[1] if len(sys.argv) > 1 else "output_splits"
    
    # 스페어 데이터가 있는 파일들 찾기
    files_with_spare_data = find_files_with_spare_data(directory)
    
    # 사용자에게 출력 방식 선택 제공
    if files_with_spare_data:
        print(f"\n{len(files_with_spare_data)}개의 파일에서 스페어 영역에 데이터를 발견했습니다.")
        print("\n출력 방식을 선택하세요:")
        print("  1. 요약 결과만 보기")
        print("  2. 상세 결과 보기 (16진수 덤프 포함)")
        
        try:
            choice = input("\n선택 (1 또는 2, 기본값: 1): ").strip()
            if choice == '2':
                print_detailed_results(files_with_spare_data)
            else:
                print_summary_results(files_with_spare_data)
        except KeyboardInterrupt:
            print("\n\n프로그램이 중단되었습니다.")
        except Exception:
            print_summary_results(files_with_spare_data)
    else:
        print_summary_results(files_with_spare_data)

if __name__ == "__main__":
    main() 