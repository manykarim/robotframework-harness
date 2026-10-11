"""Test library A: defines a keyword that collides with LibB."""


def do_thing(value: str = "a") -> str:
    """Return value from LibA."""
    return f"A:{value}"


def only_in_a(count: int, flag: bool = False) -> int:
    """Keyword unique to LibA with typed args."""
    return count
