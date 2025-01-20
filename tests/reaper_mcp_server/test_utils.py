import pytest
from reaper_mcp_server.utils import remove_empty_strings

def test_remove_empty_strings_simple_dict():
    input_dict = {
        "key1": "value1",
        "key2": "",
        "key3": "value3",
        "key4": ""
    }
    expected = {
        "key1": "value1",
        "key3": "value3"
    }
    assert remove_empty_strings(input_dict) == expected

def test_remove_empty_strings_nested_dict():
    input_dict = {
        "key1": {
            "nested1": "value1",
            "nested2": "",
            "nested3": {
                "deep1": "deep_value",
                "deep2": ""
            }
        },
        "key2": ""
    }
    expected = {
        "key1": {
            "nested1": "value1",
            "nested3": {
                "deep1": "deep_value"
            }
        }
    }
    assert remove_empty_strings(input_dict) == expected

def test_remove_empty_strings_list():
    input_list = ["item1", "", "item2", "", "item3"]
    expected = ["item1", "item2", "item3"]
    assert remove_empty_strings(input_list) == expected

def test_remove_empty_strings_nested_list():
    input_data = {
        "key1": ["item1", "", "item2"],
        "key2": "",
        "key3": [
            {"subkey1": "value1", "subkey2": ""},
            {"subkey3": "", "subkey4": "value4"}
        ]
    }
    expected = {
        "key1": ["item1", "item2"],
        "key3": [
            {"subkey1": "value1"},
            {"subkey4": "value4"}
        ]
    }
    assert remove_empty_strings(input_data) == expected

def test_remove_empty_strings_non_string_values():
    input_dict = {
        "key1": 42,
        "key2": "",
        "key3": 0,
        "key4": False,
        "key5": None
    }
    expected = {
        "key1": 42,
        "key3": 0,
        "key4": False,
        "key5": None
    }
    assert remove_empty_strings(input_dict) == expected

def test_remove_empty_strings_empty_structures():
    assert remove_empty_strings({}) == {}
    assert remove_empty_strings([]) == []
    assert remove_empty_strings({"key": {}}) == {}
    assert remove_empty_strings({"key": []}) == {}
    assert remove_empty_strings({"key1": {}, "key2": "value"}) == {"key2": "value"}

def test_remove_empty_strings_with_keep_keys():
    input_dict = {
        "name": "",
        "key1": "value1",
        "key2": "",
        "key3": {
            "name": "",
            "nested1": "val1",
            "nested2": ""
        },
        "key4": []
    }
    expected = {
        "name": "",
        "key1": "value1",
        "key3": {
            "name": "",
            "nested1": "val1"
        }
    }
    assert remove_empty_strings(input_dict, keep_keys={'name'}) == expected
