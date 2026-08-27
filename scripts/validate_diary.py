import sys
import glob

def validate_diary_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    total_lines = len(lines)
    summary_lines = len([l for l in lines[2:35] if l.strip().startswith('-')])
    print(f'File: {filepath} | Total Lines: {total_lines} | Summary Lines: {summary_lines}')
    assert 50 < total_lines < 100, f'Total lines {total_lines} must be between 51 and 99 in {filepath}'
    assert 15 < summary_lines < 30, f'Summary lines {summary_lines} must be between 16 and 29 in {filepath}'

if __name__ == '__main__':
    files = glob.glob('diary/*.md')
    if not files:
        print('No diary files found.')
        sys.exit(1)
    for f in files:
        validate_diary_file(f)
    print('All diary files strictly comply with constraints!')
