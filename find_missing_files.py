import os

def find_missing_files(directory):
    """
    Finds missing files in a sequence with a fixed step and calculates their
    corresponding block and page numbers based on NAND flash memory specs.

    Args:
        directory (str): The path to the directory containing the files.
    """
    # --- NAND Flash Memory Specifications for MT29F4G08ABADAWP ---
    PAGE_SIZE_BYTES = 2112  # 2048 data + 64 spare bytes (0x840)
    PAGES_PER_BLOCK = 64
    # ----------------------------------------------------------

    print(f"Checking for missing files in: {directory}")
    print(f"Assuming a constant file address step of 0x{PAGE_SIZE_BYTES:X} bytes.")

    try:
        # Get all .bin files and extract addresses as integers
        files = [f for f in os.listdir(directory) if f.endswith('.bin')]
        addresses = sorted([int(f.replace('.bin', ''), 16) for f in files])
    except FileNotFoundError:
        print(f"Error: Directory not found at {directory}")
        return
    except ValueError as e:
        print(f"Error converting filename to address: {e}")
        return

    if not addresses:
        print("No .bin files found in the directory.")
        return

    start_address = addresses[0]
    end_address = addresses[-1]
    
    print(f"Address range from {start_address:08X} to {end_address:08X}")

    # Create a set of existing addresses for fast lookups
    existing_addresses = set(addresses)
    missing_files_found = False

    # Iterate through the expected address range
    current_address = start_address
    while current_address <= end_address:
        if current_address not in existing_addresses:
            if not missing_files_found:
                print("\n--- Found Missing Files ---")
                missing_files_found = True
            
            # Calculate block and page number
            page_address = current_address // PAGE_SIZE_BYTES
            block_number = page_address // PAGES_PER_BLOCK
            page_in_block = page_address % PAGES_PER_BLOCK

            print(f"Missing File: {current_address:08X}.bin -> Block: {block_number}, Page: {page_in_block}")

        current_address += PAGE_SIZE_BYTES

    if not missing_files_found:
        print("\nNo missing files found in the sequence.")
    else:
        print("\n--- End of Missing File List ---")

if __name__ == "__main__":
    target_directory = r"c:\Users\147gk\Documents\nand reader\output_splits"
    find_missing_files(target_directory)
