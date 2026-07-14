import asyncio
import os
import sys

# Ensure app imports work
sys.path.insert(0, os.path.abspath('.'))

from app.services.notebooklm_service import notebooklm_service
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

async def main():
    if not notebooklm_service._mcp_exe:
        print("MCP EXE not found")
        return

    server_params = StdioServerParameters(
        command=notebooklm_service._mcp_exe,
        args=[],
        env=None
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                if t.name == "note":
                    print(f"Tool Name: {t.name}")
                    print(f"Arguments: {t.inputSchema}")
                    print("---")

asyncio.run(main())
