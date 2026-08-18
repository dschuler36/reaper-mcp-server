import math
from typing import Any, Union, Dict, List

# Keys that must survive the empty-value filter. A track with no name still
# needs its `name` key, otherwise consumers cannot tell "unnamed" from "field
# missing" and the object stops being addressable. The analysis tool labels
# rows with track_name/item_name, so those carry the same requirement.
IDENTITY_KEYS = {'name', 'track_name', 'item_name'}

DEFAULT_MAX_ENCODED_LENGTH = 1024


def truncate_encoded_params(data: Any, max_length: int = DEFAULT_MAX_ENCODED_LENGTH) -> Any:
    """Shorten oversized FX payloads for transport.

    Applied at serialization time, after the tree is built, so truncation can
    never affect parsing. The reported size is the real one.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == 'encoded_param' and isinstance(value, str) and len(value) > max_length:
                result[key] = f"<DATA_TRUNCATED: Original size {len(value)} bytes>"
            else:
                result[key] = truncate_encoded_params(value, max_length)
        return result
    if isinstance(data, list):
        return [truncate_encoded_params(item, max_length) for item in data]
    return data


def sanitize_floats(data: Any) -> Any:
    """Replace non-finite floats with None.

    Silence gives a peak of -inf, and json.dumps emits that as the bare token
    `-Infinity`, which is not valid JSON and is rejected by strict parsers on
    the other side of the transport.
    """
    if isinstance(data, dict):
        return {key: sanitize_floats(value) for key, value in data.items()}
    if isinstance(data, list):
        return [sanitize_floats(item) for item in data]
    if isinstance(data, float) and not math.isfinite(data):
        return None
    return data


def remove_empty_strings(data: Union[Dict, List], keep_keys: set = IDENTITY_KEYS) -> Union[Dict, List]:
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
