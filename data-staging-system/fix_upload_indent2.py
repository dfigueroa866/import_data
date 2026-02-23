#!/usr/bin/env python
"""Script to fix indentation error - lines 235-241 need more indentation"""

file_path = r'd:\Desarrollos\data_staging_to_prod\data-staging-system\src\data_staging\api\v1\upload.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 235-241 (indices 234-240) need 4 more spaces
# They are the content inside the elif block
lines_to_fix = [235, 236, 237, 238, 239, 240, 241]  # Line numbers (1-indexed)

for line_num in lines_to_fix:
    idx = line_num - 1  # Convert to 0-indexed
    if idx < len(lines):
        original = lines[idx]
        # Add 4 spaces
        lines[idx] = '    ' + original
        print(f"Line {line_num}: Added 4 spaces")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\nFile updated successfully!")
print("Lines 235-241 now have correct indentation for elif block")
