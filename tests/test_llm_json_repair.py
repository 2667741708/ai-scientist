from open_coscientist.llm import attempt_json_repair


def test_json_repair_escapes_literal_newlines_inside_strings() -> None:
    raw = '{"hypothesis": "line one\nline two", "items": ["a", "b",],}'

    repaired, was_major = attempt_json_repair(raw)

    assert was_major is False
    assert repaired == {"hypothesis": "line one\nline two", "items": ["a", "b"]}
