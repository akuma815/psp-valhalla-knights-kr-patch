import os
import sys
import subprocess
import argparse

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Apply xdelta binary patch to restore Korean Valhalla Knights ISO.")
    parser.add_argument("--original", required=True, help="Path to the original clean Japanese ISO file")
    parser.add_argument("--patch", required=True, help="Path to the .xdelta patch file")
    parser.add_argument("--output", default="valhalla_korean.iso", help="Path where the output Korean ISO will be saved")
    args = parser.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    game_root = os.path.dirname(script_dir)
    xdelta_exe = os.path.join(game_root, "tool", "xdelta3-3.2.0-windows-x86_64", "xdelta3.exe")
    
    if not os.path.exists(xdelta_exe):
        # Fallback to absolute workspace path if run from elsewhere
        xdelta_exe = r"g:\Downloads\Korean Traslate Project\Games\Valhalla Knights (Korea)\tool\xdelta3-3.2.0-windows-x86_64\xdelta3.exe"
        
    if not os.path.exists(xdelta_exe):
        print(f"Error: Could not find xdelta3.exe at {xdelta_exe}")
        sys.exit(1)
        
    if not os.path.exists(args.original):
        print(f"Error: Original ISO not found at {args.original}")
        sys.exit(1)
        
    if not os.path.exists(args.patch):
        print(f"Error: Patch file not found at {args.patch}")
        sys.exit(1)
        
    print("=== Applying xdelta3 binary patch ===")
    print(f"Original ISO: {args.original}")
    print(f"Patch File: {args.patch}")
    print(f"Output ISO: {args.output}")
    print("Applying patch, please wait...")
    
    # xdelta3 apply patch command: xdelta3.exe -d -s <original> <patch> <output>
    # -f forces overwriting of existing output file
    cmd = [xdelta_exe, "-f", "-d", "-s", args.original, args.patch, args.output]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("\n[Success] Patch applied successfully! Korean ISO generated.")
            print(f"Saved to: {os.path.abspath(args.output)}")
        else:
            print("\n[Error] xdelta3 failed to apply patch:")
            print(result.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
