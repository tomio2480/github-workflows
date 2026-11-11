def normalize_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("count must be an integer")
    if value < 0:
        raise ValueError("count must be nonnegative")
    return value
