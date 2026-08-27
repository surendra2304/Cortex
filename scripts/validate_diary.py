import sys
import glob

def validate_diary_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    total_lines = len(lines)
    
    # Extract Daily Summary lines specifically under ## Daily Summary
    in_summary = False
    summary_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped == '## Daily Summary':
            in_summary = True
            continue
        elif stripped.startswith('## '):
            in_summary = False
        
        if in_summary and stripped.startswith('-'):
            summary_count += 1

    print(f'File: {filepath} | Total Lines: {total_lines} | Summary Bullets: {summary_count}')
    assert 50 < total_lines < 100, f'Total lines {total_lines} must be between 51 and 99 in {filepath}'
    assert 15 < summary_count < 30, f'Summary bullets {summary_count} must be between 16 and 29 in {filepath}'

if __name__ == '__main__':
    files = glob.glob('diary/*.md')
    if not files:
        print('No diary files found.')
        sys.exit(1)
    for f in files:
        validate_diary_file(f)
    print('All diary files strictly comply with constraints!')
