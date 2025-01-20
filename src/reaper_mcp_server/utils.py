from typing import Union, Dict, List

def remove_empty_strings(data: Union[Dict, List], keep_keys: set = set()) -> Union[Dict, List]:
    if isinstance(data, dict):
        filtered = {
            key: remove_empty_strings(value, keep_keys) if key not in keep_keys else value
            for key, value in data.items()
            if (
                key in keep_keys
                or (isinstance(value, (list, dict)) and bool(value))
                or (not isinstance(value, (str, list, dict)))
                or (isinstance(value, str) and value != "")
            )
        }
        return filtered
    elif isinstance(data, list):
        filtered = [
            remove_empty_strings(item, keep_keys)
            for item in data
            if item != "" and (not isinstance(item, (list, dict)) or bool(item))
        ]
        return filtered
    else:
        return data
