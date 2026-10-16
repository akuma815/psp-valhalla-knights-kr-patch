import os
import sys
import csv

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def merge_translations():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    total_csv_path = os.path.join(workspace_dir, "total_translation.csv")
    
    if not os.path.exists(total_csv_path):
        print(f"Error: Unified CSV file not found: {total_csv_path}")
        return

    # 1. Recursively scan for individual CSV and TSV files in workspace (excluding total_translation.csv)
    translation_files = []
    for root, dirs, files in os.walk(workspace_dir):
        for file in files:
            file_lower = file.lower()
            if (file_lower.endswith(".csv") or file_lower.endswith(".tsv")) and file_lower != "total_translation.csv":
                translation_files.append(os.path.join(root, file))
            
    if not translation_files:
        print("No individual CSV or TSV files found to merge.")
        return
        
    print(f"Found {len(translation_files)} files (CSV/TSV) to process.")
    
    # 2. Gather translations
    # Key: (Normalized File Path, Index), Value: Translated text
    translations_map = {}
    
    for file_path in translation_files:
        print(f"Reading: {os.path.relpath(file_path, workspace_dir)}")
        # Detect delimiter based on extension
        is_tsv = file_path.lower().endswith(".tsv")
        delim = "\t" if is_tsv else ","
        
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=delim)
                
                # Check header structure
                if not reader.fieldnames or "Translated" not in reader.fieldnames:
                    print(f"  Warning: Skipping - 'Translated' column missing.")
                    continue
                    
                count = 0
                for row in reader:
                    f_path = row.get("File Path")
                    string_idx = row.get("Index")
                    translated = row.get("Translated")
                    
                    if translated is not None:
                        translated = translated.strip()
                        
                    if f_path and string_idx and translated:
                        # Normalize path: convert backslashes to slashes, strip spaces
                        norm_path = f_path.strip().replace('\\', '/')
                        key = (norm_path, string_idx.strip())
                        translations_map[key] = translated
                        count += 1
                print(f"  Collected {count} translated strings.")
        except Exception as e:
            print(f"  Error reading file: {e}")
            
    if not translations_map:
        print("No new translations collected from files. Merge aborted.")
        return
        
    print(f"\nTotal unique translations gathered: {len(translations_map)}")
    
    # 3. Read and update total_translation.csv
    updated_rows = []
    total_updated_count = 0
    
    try:
        with open(total_csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                f_path = row.get("File Path", "").strip().replace('\\', '/')
                string_idx = row.get("Index", "").strip()
                key = (f_path, string_idx)
                
                # If there's a new translation gathered, update it
                if key in translations_map:
                    old_val = row.get("Translated")
                    if old_val is not None:
                        old_val = old_val.strip()
                    else:
                        old_val = ""
                        
                    new_val = translations_map[key]
                    
                    if old_val != new_val:
                        row["Translated"] = new_val
                        total_updated_count += 1
                        
                updated_rows.append(row)
    except Exception as e:
        print(f"Error reading total_translation.csv: {e}")
        return

    # 4. Write back to total_translation.csv
    if total_updated_count > 0:
        try:
            with open(total_csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(updated_rows)
            print(f"\nSuccessfully updated {total_updated_count} rows in total_translation.csv!")
        except Exception as e:
            print(f"Error writing to total_translation.csv: {e}")
    else:
        print("\ntotal_translation.csv is already up to date. No changes written.")

if __name__ == "__main__":
    merge_translations()
