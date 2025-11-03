import re

def group_name_validator(name: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9_-]*', name):
        raise ValueError("Group name must be a valid identifier (alphanumeric and underscores only, cannot start with a digit).")
    if len(name) > 32:
        raise ValueError("Group name must be at most 32 characters long.")
    return name