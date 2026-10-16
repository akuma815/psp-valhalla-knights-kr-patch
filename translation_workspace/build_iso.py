import os
import sys
import subprocess
import argparse

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    game_root = os.path.dirname(script_dir)
    default_output = os.path.join(os.path.dirname(game_root), "Valhalla_Knights_Korean.iso")

    parser = argparse.ArgumentParser(description="Rebuild loose PSP folders into a valid PSP ISO file.")
    parser.add_argument("--source", default=game_root, help="Path to folder containing PSP_GAME and UMD_DATA.BIN")
    parser.add_argument("--output", default=default_output, help="Path where the output ISO will be saved")
    parser.add_argument("--volume-label", default="VALHALLA_KNIGHTS", help="Volume label of the ISO")
    args = parser.parse_args()
    
    # 1. Validate inputs
    source_dir = os.path.abspath(args.source)
    output_iso = os.path.abspath(args.output)
    
    psp_game_dir = os.path.join(source_dir, "PSP_GAME")
    umd_data_file = os.path.join(source_dir, "UMD_DATA.BIN")
    
    if not os.path.exists(psp_game_dir) or not os.path.exists(umd_data_file):
        print(f"Error: Target source folder does not contain a valid PSP game structure.")
        print(f"  Expected '{psp_game_dir}' and '{umd_data_file}' to exist.")
        sys.exit(1)
        
    # Prevent creating the output ISO inside the source folder being compiled (avoids infinite loops)
    if output_iso.startswith(source_dir):
        print("Warning: Saving the output ISO inside the source directory can cause packaging loops.")
        # Automatically adjust to parent folder
        parent_dir = os.path.dirname(source_dir)
        output_iso = os.path.join(parent_dir, os.path.basename(args.output))
        print(f"  Adjusting output path to: {output_iso}")
        
    # 2. Locate mkisofs.exe
    mkisofs_paths = [
        os.path.join(game_root, "tool", "mkisofs.exe"),
        r"g:\Downloads\Korean Traslate Project\Games\Valhalla Knights (Korea)\tool\mkisofs.exe",
        "mkisofs.exe"  # Attempt global PATH resolution
    ]
    
    mkisofs_exe = None
    for path in mkisofs_paths:
        # Check if command is executable / exists
        if path == "mkisofs.exe" or os.path.exists(path):
            mkisofs_exe = path
            break
            
    if not mkisofs_exe:
        print("[-] Error: 'mkisofs.exe' not found.")
        print("    Please download 'mkisofs.exe' (a lightweight executable) and place it inside the 'tool' folder:")
        print(f"    Expected location: '{os.path.join(game_root, 'tool', 'mkisofs.exe')}'")
        sys.exit(1)
        
    print("=== Rebuilding PSP ISO File ===")
    print(f"Using Tool: {mkisofs_exe}")
    print(f"Source Dir: {source_dir}")
    print(f"Output ISO: {output_iso}")
    print(f"Volume Label: {args.volume_label}")
    print("Compiling ISO filesystem, please wait...")
    
    # mkisofs command optimized for PlayStation Portable (PSP) hardware support:
    # -iso-level 4: Allows long filenames and files > 4GB
    # -xa: Generates standard CD-ROM XA extensions
    # -A "PSP GAME": Sets Application ID
    # -V: Sets Volume Label
    # -sysid "PLAYSTATION": System ID required by PSP OS boot checks
    cmd = [
        mkisofs_exe,
        "-iso-level", "4",
        "-xa",
        "-A", "PSP GAME",
        "-V", args.volume_label,
        "-sysid", "PLAYSTATION",
        "-o", output_iso,
        source_dir
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("\n[Success] PSP ISO rebuilt successfully!")
            print(f"Generated ISO: {output_iso}")
        else:
            print("\n[Error] mkisofs failed to build the ISO:")
            print(result.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during build execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
