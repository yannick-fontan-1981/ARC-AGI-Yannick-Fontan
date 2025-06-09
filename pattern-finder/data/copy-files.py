#!/usr/bin/env python3
import shutil
from pathlib import Path

# List of files to copy
FILES = [
    "2dc579da.json",
    "28bf18c6.json",
    "3af2c5a8.json",
    "44f52bb0.json",
    "62c24649.json",
    "67e8384a.json",
    "7468f01a.json",
    "662c240a.json",
    "42a50994.json",
    "56ff96f3.json",
    "50cb2852.json",
    "4347f46a.json",
    "46f33fce.json",
    "a740d043.json",
    "a79310a0.json",
    "aabf363d.json",
    "ae4f1146.json",
    "b27ca6d3.json",
    "ce22a75a.json",
    "dc1df850.json",
    "f25fbde4.json",
    "44d8ac46.json",
    "1e0a9b12.json",
    "0d3d703e.json",
    "3618c87e.json",
    "1c786137.json",
]

def main():
    src_dir = Path("training")
    dst_dir = Path("training-4")
    dst_dir.mkdir(exist_ok=True)

    for fname in FILES:
        src = src_dir / fname
        dst = dst_dir / fname
        if not src.exists():
            print(f"⚠️  Skipping missing file: {src}")
            continue
        shutil.copy(src, dst)
        print(f"Copied {src} → {dst}")

    print(f"\n✅ Done. {len(FILES)} files processed.")

if __name__ == "__main__":
    main()
