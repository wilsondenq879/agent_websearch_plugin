import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from agent_websearch import broker
from agent_websearch.config import init,load


@unittest.skipUnless(importlib.util.find_spec('mcp'),'Optional MCP extra is not installed')
class MCPTests(unittest.TestCase):
    def test_real_stdio_handshake_tool_listing_and_status(self):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);init(root,18769)
            config=load(root/'config.json');server=broker.make_server(config|{'port':0})
            config['port']=server.server_port;(root/'config.json').write_text(json.dumps(config))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            async def run():
                params=StdioServerParameters(command=sys.executable,args=['-m','agent_websearch.mcp_server'],
                    env={**os.environ,'AGENT_WEBSEARCH_HOME':str(root)})
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        tools=await session.list_tools()
                        self.assertEqual({t.name for t in tools.tools},{'browser_status','web_search','read_webpage',
                            'inspect_webpage','image_search','video_search'})
                        response=await session.call_tool('browser_status',{})
                        self.assertFalse(response.isError)
                        data=json.loads(response.content[0].text)
                        self.assertEqual(data['protocol_version'],1)
                        self.assertFalse(data['connected'])
            try:asyncio.run(run())
            finally:server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__':unittest.main()
