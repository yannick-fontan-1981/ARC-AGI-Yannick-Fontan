#!/usr/bin/env python3
import shutil
from pathlib import Path

# List of files to copy
FILES = [
    "8efcae92.json",
    "445eab21.json",
    "6f8cd79b.json",
    "2013d3e2.json",
    "41e4d17e.json",
    "9565186b.json",
    "aedd82e4.json",
    "bb43febb.json",
    "e98196ab.json",
    "f76d97a5.json",
    "ce9e57f2.json",
    "22eb0ac0.json",
    "9f236235.json",
    "a699fb00.json",
]

def main():
    src_dir = Path("training")
    dst_dir = Path("training-5")
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
