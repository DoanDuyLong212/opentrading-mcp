import asyncio, json
from opentrading_mcp.providers import vnstock as vn, store
from opentrading_mcp.server import create_server, register_preset

async def main():
    vn.listing_symbols=lambda: [{'symbol':'AAA'}]
    server=create_server('scan'); register_preset(server,'scan')
    fn=server._tool_manager.get_tool('stock_screener').fn
    for value in (None,[None,None]):
        store._memory.clear()
        vn.equity_fundamentals=lambda symbol: {'roe':0.2}
        env=await fn(filters={'pe':value})
        print(json.dumps({'input':value,'data':env['data'],'availability':env['availability'],'warnings':env['warnings']},ensure_ascii=False))
asyncio.run(main())
