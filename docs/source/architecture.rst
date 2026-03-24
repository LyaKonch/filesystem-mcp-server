Architecture
============

Project structure
-----------------

- ``main.py`` — server startup and tool registration.
- ``tools/*`` — user-facing MCP tools (filesystem, monitoring, management).
- ``utilities/*`` — shared helpers (validation, logging, error handling, storage).
- ``auth/*`` — authentication provider and permission middleware.

Interaction flow
----------------

1. ``main.py`` creates FastMCP app.
2. ``AuthMiddleware`` processes incoming requests.
3. Tool handlers execute business logic.
4. Errors pass through unified formatting in ``utilities/error_handling.py``.
