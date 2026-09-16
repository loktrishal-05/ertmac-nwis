"""Importing this package populates the tool registry. Nothing here is
imported elsewhere for its own logic — only for the register() side effects
in each submodule."""
from app.agents.tools import knowledge, maintenance, sensors  # noqa: F401
