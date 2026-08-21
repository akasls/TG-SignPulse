import pytest
from backend.utils.names import validate_storage_name


def test_validate_storage_name_valid():
    assert validate_storage_name("my_account_1", field_name="account") == "my_account_1"
    assert validate_storage_name("task-test.1", field_name="task") == "task-test.1"
    assert validate_storage_name("中文账号", field_name="account") == "中文账号"


def test_validate_storage_name_empty_or_whitespace():
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_storage_name("", field_name="name")
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_storage_name("   ", field_name="name")


def test_validate_storage_name_dot_traversal():
    with pytest.raises(ValueError, match="cannot be '\\.' or '\\.\\.'"):
        validate_storage_name(".", field_name="name")
    with pytest.raises(ValueError, match="cannot be '\\.' or '\\.\\.'"):
        validate_storage_name("..", field_name="name")


def test_validate_storage_name_trailing_dot_or_space():
    with pytest.raises(ValueError, match="cannot end with a dot or space"):
        validate_storage_name("test.", field_name="name")


def test_validate_storage_name_illegal_chars():
    illegal_samples = [
        "foo/bar",
        "foo\\bar",
        "foo:bar",
        "foo*bar",
        "foo?bar",
        'foo"bar',
        "foo<bar",
        "foo>bar",
        "foo|bar",
        "foo\x00bar",
        "foo\x1fbar",
    ]
    for sample in illegal_samples:
        with pytest.raises(ValueError, match="illegal characters"):
            validate_storage_name(sample, field_name="name")


def test_validate_storage_name_windows_reserved():
    reserved = ["con", "PRN", "aux", "nul", "com1", "LPT2", "com9.txt"]
    for name in reserved:
        with pytest.raises(ValueError, match="reserved system device name"):
            validate_storage_name(name, field_name="name")
