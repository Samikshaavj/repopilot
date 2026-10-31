from app.tools import _clean_arguments


def test_aliases_are_renamed():
    cleaned = _clean_arguments("read_file", {"path": "a.py", "line_start": 5, "line_end": 20})
    assert cleaned == {"path": "a.py", "start_line": 5, "end_line": 20}


def test_unknown_arguments_are_dropped():
    cleaned = _clean_arguments("search_code", {"query": "max_age", "path": "", "limit": 5})
    assert cleaned == {"query": "max_age", "limit": 5}