import os
import sys
import struct
import csv
import shutil
import argparse

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def align_to(size, alignment=16):
    return (size + alignment - 1) & ~(alignment - 1)

def build_sttv1(strings, encoding='cp949', fixed_offsets=False, original_stt_path=None):
    """
    Builds a STTV1.00 string table binary from a list of string dictionaries.
    If fixed_offsets is True and original_stt_path is provided, reads the original binary file
    to get the exact original byte length of each string to prevent structural shifts.
    """
    magic = b"STTV1.00"
    num_strings = len(strings)
    table_offset = 16 # Immediately after the main header
    
    # 1. Parse original lengths from binary file if fixed_offsets is enabled
    original_lengths = {}
    if fixed_offsets and original_stt_path and os.path.exists(original_stt_path):
        try:
            with open(original_stt_path, "rb") as orig_f:
                orig_magic = orig_f.read(8)
                if orig_magic == b"STTV1.00":
                    orig_num = struct.unpack("<I", orig_f.read(4))[0]
                    orig_tbl_off = struct.unpack("<I", orig_f.read(4))[0]
                    orig_f.seek(orig_tbl_off)
                    for idx in range(orig_num):
                        offset, length = struct.unpack("<II", orig_f.read(8))
                        # The total space allocated is length + 1 (including null terminator)
                        original_lengths[idx] = length + 1
        except Exception as e:
            print(f"  Warning: Failed to parse original binary lengths from {original_stt_path}: {e}")

    # 2. Encode strings to bytes and calculate offsets
    encoded_strings = []
    for s in strings:
        txt = s["translated"] if s["translated"] else s["original"]
        idx = s["index"]
        
        if fixed_offsets and idx in original_lengths:
            orig_bytes_len = original_lengths[idx]
            
            # Encode Korean translation (without null terminator first)
            enc_korean = txt.encode(encoding, errors='replace')
            
            # Truncate if it exceeds space, otherwise pad with nulls to match original size
            if len(enc_korean) >= orig_bytes_len:
                enc = enc_korean[:orig_bytes_len - 1] + b'\x00'
            else:
                enc = enc_korean.ljust(orig_bytes_len, b'\x00')
        else:
            # Standard mode: encode with single null terminator
            enc = txt.encode(encoding, errors='replace') + b'\x00'
            
        encoded_strings.append(enc)
        
    # 3. Build index table
    index_table_data = bytearray()
    current_offset = table_offset + (num_strings * 8)
    
    for enc in encoded_strings:
        length = len(enc) - 1 # Length excluding null terminator
        index_table_data.extend(struct.pack("<II", current_offset, length))
        current_offset += len(enc)
        
    # 4. Concatenate all pieces
    header = struct.pack("<8sII", magic, num_strings, table_offset)
    string_data = b"".join(encoded_strings)
    
    return header + index_table_data + string_data

def pack_res(unpacked_dir, output_res_path):
    """
    Packs a directory back into a RESC archive file, preserving 16-byte alignment.
    """
    if not os.path.exists(unpacked_dir):
        print(f"Error: Directory {unpacked_dir} does not exist.")
        return False
        
    # Gather all files in the folder (excluding subdirectories)
    files = [f for f in os.listdir(unpacked_dir) if os.path.isfile(os.path.join(unpacked_dir, f))]
    num_files = len(files)
    
    # Pre-build file entry table to calculate initial offsets
    entries = []
    # RESC Header: Magic (4 bytes) + num_files (4 bytes) = 8 bytes
    header_size = 8
    entry_table_size = num_files * 16
    
    # First file offset starts after the header and entry table, aligned to 16 bytes
    first_file_offset = align_to(header_size + entry_table_size, 16)
    
    current_offset = first_file_offset
    entry_table_data = bytearray()
    file_data_blocks = bytearray()
    
    # Add padding to reach the first file offset
    header_padding_len = first_file_offset - (header_size + entry_table_size)
    
    for file in files:
        file_path = os.path.join(unpacked_dir, file)
        with open(file_path, "rb") as f:
            data = f.read()
            
        size = len(data)
        
        # Prepare file name in reverse 8-byte layout (little-endian uint64)
        name_bytes = file.encode('ascii', errors='ignore')
        # Pad with nulls to 8 bytes
        name_padded = name_bytes.ljust(8, b'\x00')
        # Reverse the bytes
        name_reversed = name_padded[::-1]
        
        # Add entry record
        entry_table_data.extend(name_reversed)
        entry_table_data.extend(struct.pack("<II", size, current_offset))
        
        # Append data block
        file_data_blocks.extend(data)
        
        # Add alignment padding to next file offset
        aligned_offset = align_to(current_offset + size, 16)
        padding_needed = aligned_offset - (current_offset + size)
        file_data_blocks.extend(b'\x00' * padding_needed)
        
        current_offset = aligned_offset
        
    # Build complete RESC file
    magic = b"RESC"
    header = struct.pack("<4sI", magic, num_files)
    
    with open(output_res_path, "wb") as out_f:
        out_f.write(header)
        out_f.write(entry_table_data)
        out_f.write(b'\x00' * header_padding_len)
        out_f.write(file_data_blocks)
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Repack translated CSV files and recreate RES archives.")
    parser.add_argument("--encoding", default="cp949", help="Text encoding to use (e.g. cp949, utf-8)")
    parser.add_argument("--fixed-offsets", action="store_true", help="Keep text sizes and offsets identical to original files")
    args = parser.parse_args()
    
    encoding = args.encoding
    fixed_offsets = args.fixed_offsets
    
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    game_root = os.path.dirname(workspace_dir)
    
    game_resource_root = os.path.join(game_root, "PSP_GAME", "USRDIR", "Resource")
    unpacked_root = os.path.join(game_root, "unpacked_resources")
    repacked_output = os.path.join(game_root, "repacked_output", "PSP_GAME", "USRDIR", "Resource")
    
    total_csv_path = os.path.join(workspace_dir, "total_translation.csv")
    
    if not os.path.exists(total_csv_path):
        print(f"Error: Unified CSV file not found: {total_csv_path}")
        sys.exit(1)
        
    print(f"Loading translations from: {total_csv_path}")
    print(f"Target text encoding: {encoding}")
    print(f"Fixed offsets mode: {fixed_offsets}")
    
    # 1. Parse unified CSV
    translation_data = {}
    with open(total_csv_path, "r", encoding="utf-8-sig") as csv_f:
        reader = csv.DictReader(csv_f)
        for row in reader:
            file_path = row["File Path"]
            string_idx = int(row["Index"])
            offset = int(row["Offset"])
            original = row["Original"].replace('\r\n', '\n')
            translated = row["Translated"].replace('\r\n', '\n')
            
            if file_path not in translation_data:
                translation_data[file_path] = []
                
            translation_data[file_path].append({
                "index": string_idx,
                "offset": offset,
                "original": original,
                "translated": translated
            })
            
    # 2. Recompile string tables (STTV1.00 files)
    print("\nRecompiling string tables...")
    original_resource_root = os.path.join(game_root, "Original", "PSP_GAME", "USRDIR", "Resource")
    
    for rel_path, strings in translation_data.items():
        # Sort by index just in case
        strings.sort(key=lambda x: x["index"])
        
        # Path to the unpacked file inside our temp extracted resources
        unpacked_file_path = os.path.join(unpacked_root, rel_path)
        
        # Path to the original binary file inside our Original backup
        original_stt_path = os.path.join(original_resource_root, rel_path)
        
        # Build new binary data with fixed_offsets option and original binary length parser
        stt_bin = build_sttv1(strings, encoding=encoding, fixed_offsets=fixed_offsets, original_stt_path=original_stt_path)
        
        # Backup the old unpacked file (optional) and write the new one
        os.makedirs(os.path.dirname(unpacked_file_path), exist_ok=True)
        with open(unpacked_file_path, "wb") as f_out:
            f_out.write(stt_bin)
            
        print(f"  Rebuilt string table: {rel_path} ({len(strings)} strings)")
        
    # 3. Pack directories back into RES files
    print("\nRe-packing resource directories into RES files...")
    
    # Build a whitelist of archives that actually contain modified text
    repack_whitelist = set(['global', 'tbldata'])
    for rel_path in translation_data.keys():
        parts = rel_path.replace('\\', '/').split('/')
        if len(parts) > 0:
            repack_whitelist.add(parts[0].lower())
            
    print(f"Archives containing text modifications to repack: {list(repack_whitelist)}")
    
    # We will traverse original USRDIR\Resource structure and rebuild RES files
    for root, dirs, files in os.walk(game_resource_root):
        for file in files:
            if file.lower().endswith(".res"):
                res_path = os.path.join(root, file)
                rel_path = os.path.relpath(res_path, game_resource_root)
                rel_dir = os.path.dirname(rel_path)
                
                archive_name = os.path.splitext(file)[0]
                archive_key = archive_name.lower()
                
                # Check if we have an unpacked folder for this archive
                unpacked_archive_dir = os.path.join(unpacked_root, rel_dir, f"{archive_name}_extracted")
                
                target_res_path = os.path.join(repacked_output, rel_path)
                os.makedirs(os.path.dirname(target_res_path), exist_ok=True)
                
                # ONLY repack if it is in our whitelist (contains modified text)
                if archive_key in repack_whitelist and os.path.exists(unpacked_archive_dir):
                    success = pack_res(unpacked_archive_dir, target_res_path)
                    if success:
                        print(f"  Re-packed archive: {rel_path}")
                    else:
                        print(f"  Failed to pack: {rel_path}")
                else:
                    # Otherwise, copy the original clean RES file as-is (guarantees 100% graphics/sound stability)
                    # Try copying from Original folder first, fallback to current if not found
                    orig_fallback_path = os.path.join(original_resource_root, rel_path)
                    source_to_copy = orig_fallback_path if os.path.exists(orig_fallback_path) else res_path
                    shutil.copy2(source_to_copy, target_res_path)
                    
    print("\n=== Repacking Process Completed ===")
    print(f"All repacked files successfully built and saved to:")
    print(f"  {repacked_output}")
    print("\nTo test, copy the contents of the 'repacked_output/PSP_GAME' folder into your original PSP_GAME directory.")
 
if __name__ == "__main__":
    main()
