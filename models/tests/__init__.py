"""Test utilities for Pydantic validation assertions."""

from typing import Any, Dict, Iterable, List

from pydantic import ValidationError


def check_model_error(errors: Any, expected_errors: List[Dict[str, Any]]) -> None:
    """
    Compare a Pydantic ValidationError against an expected structure.

    `errors` should be the context manager output from `pytest.raises(ValidationError)`.
    Only keys provided in each expected error are checked, allowing partial matching.
    Extra actual errors are allowed; we just require every expected error to be found.
    """
    if not isinstance(errors.value, ValidationError):
        raise AssertionError(f"Expected ValidationError, got {type(errors.value).__name__}")

    actual_errors: Iterable[Dict[str, Any]] = errors.value.errors()
    actual_list = list(actual_errors)

    for expected in expected_errors:
        match = False
        for actual in actual_list:
            # all keys in expected must match the actual error entry
            if all(key in actual and actual[key] == value for key, value in expected.items()):
                match = True
                break
        if not match:
            raise AssertionError(f"Expected error {expected!r} not found in actual errors: {actual_list}")
