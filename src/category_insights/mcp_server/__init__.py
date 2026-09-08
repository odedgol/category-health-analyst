"""Interface layer: exposes domain operations as MCP tools (Command pattern).

`tools.py` holds the 6 Command classes — plain, independently testable
`execute(input) -> output` objects with their ports injected through the
constructor. `server.py` only wires those commands to the `mcp` SDK; it
contains no logic of its own. Tools operate on `category_id: int`, never
a free-text category name — name resolution is the agent's job, not the
MCP server's.
"""
