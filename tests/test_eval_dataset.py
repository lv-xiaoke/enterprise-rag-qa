from collections import Counter
import hashlib
from pathlib import Path
from eval.run_eval import load_golden_set


def test_heldout_cases_pin_source_content_and_evidence():
    items = load_golden_set(Path('eval/test_set.jsonl'))
    assert Counter(row['category'] for row in items) == {
        'synonym':8, 'numeric':6, 'cross_document':6, 'unanswerable':5, 'permission':5}
    assert len({row['id'] for row in items}) == 30
    for row in items:
        assert row['reference_answer']
        for name, fragment in zip(row['expected_sources'], row['evidence_snippets']):
            content = (Path('data/enterprise') / name).read_bytes()
            assert hashlib.sha256(content).hexdigest() == row['document_content_sha256'][name]
            assert fragment in content.decode('utf-8')
