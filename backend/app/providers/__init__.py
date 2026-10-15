"""Provider boundary (CLAUDE.md §4.2).

Domain code imports only from ``app.providers.base`` and obtains adapters through
``app.providers.registry``. No vendor SDK type may cross this boundary.
"""
