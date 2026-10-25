from __future__ import annotations

import asyncio
import unittest

try:
    from fastmcp import Client

    from webde_reader.mcp_server import mcp
except ImportError:  # Core-only installs intentionally omit the optional MCP dependency.
    Client = None
    mcp = None


async def _list_tools_over_mcp():
    async with Client(mcp) as client:
        return await client.list_tools()


@unittest.skipIf(mcp is None, "FastMCP optional dependency is not installed")
class McpTests(unittest.TestCase):
    def test_exposes_only_the_four_read_only_tools(self):
        tools = asyncio.run(_list_tools_over_mcp())
        self.assertEqual(
            {tool.name for tool in tools},
            {"search_messages", "get_message", "reconstruct_thread", "get_attachment"},
        )
        for tool in tools:
            self.assertTrue(tool.annotations.read_only_hint)
            self.assertFalse(tool.annotations.destructive_hint)
            self.assertTrue(tool.annotations.idempotent_hint)


if __name__ == "__main__":
    unittest.main()
