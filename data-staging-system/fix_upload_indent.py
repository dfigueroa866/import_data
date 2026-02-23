#!/usr/bin/env python
"""Script to fix indentation error in upload.py line 234"""

file_path = r'd:\Desarrollos\data_staging_to_prod\data-staging-system\src\data_staging\api\v1\upload.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 234 (index 233) needs 4 more spaces of indentation
# Currently has 16 spaces, needs 20 spaces
if len(lines) > 233:
    line_234 = lines[233]
    if line_234.strip().startswith('elif isinstance(data, dict):'):
        # Add 4 spaces to the beginning
        lines[233] = '    ' + line_234
        print(f"Fixed line 234: Changed indentation from 16 to 20 spaces")
    else:
        print(f"Line 234 doesn't match expected content: {line_234}")
else:
    print(f"File has only {len(lines)} lines")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("File updated successfully!")
