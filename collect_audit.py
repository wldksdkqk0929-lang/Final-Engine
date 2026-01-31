import os

# 우리가 감수할 파일 목록 (경로가 정확해야 함)
targets = [
    "engine/gatekeeper.py",
    "src/governance.py",
    "src/models.py" 
]

output_file = "audit_legacy.txt"

print(f"🕵️  Searching for legacy files...")

with open(output_file, "w", encoding="utf-8") as outfile:
    found_count = 0
    for path in targets:
        if os.path.exists(path):
            outfile.write(f"\n{'='*40}\nFILE: {path}\n{'='*40}\n\n")
            try:
                with open(path, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())
                print(f"   ✅ Found & Packed: {path}")
                found_count += 1
            except Exception as e:
                outfile.write(f"Error reading file: {e}\n")
        else:
            print(f"   ⚠️  Missing: {path}")
            outfile.write(f"\n{'='*40}\nFILE: {path} (NOT FOUND)\n{'='*40}\n\n")

print(f"\n📄 Result saved to: {output_file} ({found_count} files)")
