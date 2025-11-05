import re

def group_name_validator(name: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9_-]*', name):
        raise ValueError("Group name must be a valid identifier (alphanumeric and underscores only, cannot start with a digit).")
    if len(name) > 32:
        raise ValueError("Group name must be at most 32 characters long.")
    return name

def note_ticket_validator(ticket: str) -> str:
    if not ticket.isalnum():
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    if len(ticket) > 9:
        raise ValueError("Ticket numbers must be alphanumeric with 9 characters or less")
    return ticket

def user_password_validator(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    if not re.search(r'[A-Z]', password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r'[a-z]', password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain at least one digit.")
    return password

def user_name_validator(username: str) -> str:
    if not re.fullmatch(r'[^:,]*', username):
        raise ValueError("Username cannot contain the characters ':' or ','.")
    return username