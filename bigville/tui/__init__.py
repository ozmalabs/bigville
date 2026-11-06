"""Terminal interface for one resident (Phase 057).

    python -m bigville.tui --player NAME            embedded in-process game (town100 by default)
    python -m bigville.tui --player NAME --url URL  a server in agent mode (GET /api/view, POST /api/turn)
    python -m bigville.tui --player NAME --plain    the text-adventure line mode (any terminal, pipes, tests)

The interface reads only the agent view (domains/agent_view.py). Rendering is in render.py, parsing in
commands.py, the connections in client.py, and the session and front ends in app.py.
"""
