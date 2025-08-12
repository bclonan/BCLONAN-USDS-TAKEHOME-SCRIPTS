import json, subprocess, sys
from pathlib import Path

def test_validate_json_script(tmp_path):
    doc = {
        "title_number": "1",
        "title_name": "Title One",
        "parts": [
            {"part_number": "1", "sections": [
                {"section_number": "1.1", "section_name": "Intro", "content": "Hello world", "word_count": 2}
            ]}
        ],
        "stats": {"total_sections": 1, "word_count": 2, "paragraph_count": 1}
    }
    out_file = tmp_path / 'title1.json'
    out_file.write_text(json.dumps(doc), encoding='utf-8')
    script = Path('scripts') / 'validate_json.py'
    proc = subprocess.run([sys.executable, str(script), str(out_file)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert isinstance(report, list)
    assert report[0]['errors'] == []
