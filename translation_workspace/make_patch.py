import os
import sys
import subprocess
import argparse

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Create xdelta binary patch for Valhalla Knights ISO.")
    parser.add_argument("--original", required=True, help="Path to the original Japanese ISO file")
    parser.add_argument("--modified", required=True, help="Path to the modified Korean ISO file")
    parser.add_argument("--output", default="valhalla_korean.xdelta", help="Path where the output xdelta patch will be saved")
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
        
    if not os.path.exists(args.modified):
        print(f"Error: Modified ISO not found at {args.modified}")
        sys.exit(1)
        
    print("=== Creating xdelta3 binary patch ===")
    print(f"Original ISO: {args.original}")
    print(f"Modified ISO: {args.modified}")
    print(f"Output Patch: {args.output}")
    print("Please wait, this might take a minute...")
    
    # xdelta3 create patch command: xdelta3.exe -e -s <original> <modified> <patch>
    # -f forces overwriting of existing patch file
    # -9 enables maximum compression
    cmd = [xdelta_exe, "-f", "-9", "-e", "-s", args.original, args.modified, args.output]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("\n[Success] Binary patch created successfully!")
            print(f"Saved to: {os.path.abspath(args.output)}")
        else:
            print("\n[Error] xdelta3 failed to create patch:")
            print(result.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
