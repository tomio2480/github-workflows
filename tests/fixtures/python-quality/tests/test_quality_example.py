import pytest

from quality_example import normalize_count


@pytest.mark.parametrize("value", [0, 3, 100])
def test_accepts_nonnegative_integer(value: int) -> None:
    assert normalize_count(value) == value


@pytest.mark.parametrize("value", [True, False, 1.5, "3", None])
def test_rejects_noninteger(value: object) -> None:
    with pytest.raises(TypeError):
        normalize_count(value)


@pytest.mark.parametrize("value", [-1, -20])
def test_rejects_negative_integer(value: int) -> None:
    with pytest.raises(ValueError):
        normalize_count(value)
