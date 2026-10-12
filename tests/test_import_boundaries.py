"""Importing the API must not initialize models or download embeddings."""
import subprocess
import sys


def test_api_import_does_not_build_embedding_or_chat_models():
    result = subprocess.run(
        [sys.executable, '-c',
         "import model.factory as f; import api.server; "
         "assert not f._cache, 'API import constructed a model'"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]
