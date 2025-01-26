from typing import NamedTuple


class Token:
    """A token for a specific service.

    This class is used to store a sensitive token,
    obfuscating it when printed.
    """

    def __init__(self, token: str | None, name: str):
        self._token = token
        self.name = name
        return

    def get(self):
        return self._token

    def __repr__(self):
        return f"<{self.name} Token>"

    def __str__(self):
        return f"***{self.name} Token***"

    def __bool__(self):
        return bool(self._token)


class _TitledEmoji(NamedTuple):
    title: str
    emoji: str
