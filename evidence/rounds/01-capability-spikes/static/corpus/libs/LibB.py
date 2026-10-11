"""Test library B: defines a keyword that collides with LibA."""


def do_thing(value: str = "b") -> str:
    """Return value from LibB."""
    return f"B:{value}"
