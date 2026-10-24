import asyncio, json
import pandas as pd
from opentrading_mcp.providers import vnstock as vn, screener, store
from opentrading_mcp.server import create_server, register_preset

print('ALL_ZERO', vn._long_ratio_values(pd.DataFrame([
 {'item_id':'roe','2025':0.0,'2024':0.0},
 {'item_id':'trailing_eps','2025':0.0,'2024':0.0},
 {'item_id':'book_value_per_share_bvps','2025':8000.0,'2024':7000.0},
])))
print('NAN_DIRECT_FILTER', screener.apply_filters([{'symbol':'AAA','pe':float('nan')}], {'pe':[1,10]}))

async def repro():
    store._memory.clear()
    vn.listing_symbols=lambda: [{'symbol':'AAA'}]
    vn.equity_fundamentals=lambda symbol: {'pe':float('nan'),'roe':0.2}
    server=create_server('scan'); register_preset(server,'scan')
    env=await server._tool_manager.get_tool('stock_screener').fn(filters={'pe':[1,10]})
    print('NAN_TOOL', json.dumps(env,ensure_ascii=False))

asyncio.run(repro())
