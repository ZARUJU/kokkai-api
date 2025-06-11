import os
import sys
import types
import pytest

# Stub external dependencies not installed in the test environment
sys.modules.setdefault("requests", types.ModuleType("requests"))
bs4_stub = types.ModuleType("bs4")
bs4_stub.BeautifulSoup = object
sys.modules.setdefault("bs4", bs4_stub)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.qa_shu_utils import extract_submitter_count

@pytest.mark.parametrize("text,expected", [
    ("原口　一博君外二名", 3),
    ("田中　太郎君", 1),
    ("佐藤　太郎君外十一名", 12),
    ("佐藤　太郎君外十二名", 13),
])
def test_extract_submitter_count(text, expected):
    assert extract_submitter_count(text) == expected
