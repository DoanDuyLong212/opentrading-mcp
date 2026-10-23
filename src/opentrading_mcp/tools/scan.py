"""Scan: screener, breadth, rotation, alerts, flows, insider, technical."""

from __future__ import annotations

import asyncio
import functools
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import technicals as tech_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    READ_WRITE_STATE,
    AnyContext,
    blocking_slots,
    cache_lookup,
    cache_store,
    price_ttl,
    run_blocking,
)

ALERT_STATE_KEY = "mcp:scan:alert_state"
# Cross state must outlive a single scan cycle, otherwise cross_up/cross_down
# lose their prev value and re-fire every call (or silently reset). One hour
# covers normal scheduler gaps; a fresh state only costs one seeded first
# observation.
ALERT_STATE_TTL = 3600


def register_scan_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_screener(
        filters: dict[str, Any] | None = None,
        max_pe: float | None = None,
        min_roe: float | None = None,
        limit: int = 20,
        technical: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Sàng lọc toàn thị trường theo định giá và chất lượng. Dùng khi săn ứng viên theo tiêu
            chí.

        Dùng khi: "lọc cổ phiếu PE<10 ROE>15%", tìm mã theo điều kiện.
        Không dùng khi: đã biết mã cần phân tích (đi thẳng tool của mã đó); cần so vài mã cụ thể
            (dùng peer_compare); cần full chỉ báo kỹ thuật 1 mã (dùng signals_technical).

        filters: {trường: [min, max]} (None là không chặn) hoặc chuỗi cho khớp mã/sàn;
        dùng signals_screener_columns để biết trường hợp lệ. max_pe/min_roe là phím tắt.
        technical: lọc thời điểm vòng 3 trên ứng viên đã lọc
        ({rsi_lt, rsi_gt, above_sma20: true, below_sma20: true}).
        """
        fp = f"{filters}|{max_pe}|{min_roe}|{limit}|{technical}"
        hit = await cache_lookup("stock_screener", fp)
        if hit is not None:
            return hit
        from opentrading_mcp.providers import screener as sc_p
        from opentrading_mcp.providers import technicals as tech_p

        eff: dict[str, Any] = dict(filters or {})
        if max_pe is not None and "pe" not in eff:
            eff["pe"] = [None, max_pe]
        if min_roe is not None and "roe" not in eff:
            eff["roe"] = [min_roe, None]
        try:
            rows = await run_blocking(vn_p.listing_symbols, "stock_screener")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "stock_screener"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        warnings: list[str] = []
        # Bounded enrich: full width (≤30) only when a valuation filter needs
        # fundamentals; otherwise cap at 10 for display. Concurrent via
        # asyncio.gather + semaphore matched to blocking slots (10s per symbol
        # run_blocking timeout starts at submission, so an oversized semaphore
        # would only amplify queue timeouts).
        needs_valuation = any(k in eff for k in ("pe", "roe", "market_cap"))
        if needs_valuation:
            enrich_n = min(len(rows), max(max(limit, 1) * 2, 20), 30)
        else:
            enrich_n = min(len(rows), 10)
        enriched = 0
        sem = asyncio.Semaphore(blocking_slots())

        async def _enrich_one(entry: dict[str, Any]) -> bool:
            sym = str(entry.get("symbol", "")).upper()
            if not sym:
                return False
            async with sem:
                try:
                    info = await run_blocking(
                        functools.partial(vn_p.equity_fundamentals, sym),
                        "stock_screener",
                        timeout_secs=10.0,
                    )
                except Exception:
                    return False
            if isinstance(info, dict):
                hit = False
                for key in ("pe", "roe", "market_cap"):
                    if info.get(key) is not None:
                        entry[key] = info[key]
                        hit = True
                return hit
            return False

        if enrich_n:
            results = await asyncio.gather(*(_enrich_one(entry) for entry in rows[:enrich_n]))
            enriched = sum(1 for r in results if r)
        if rows and enrich_n and enriched < enrich_n:
            warnings.append(f"fundamentals best-effort: {enriched}/{enrich_n} enriched")
        try:
            candidates = sc_p.apply_filters(rows, eff)
        except Exception as exc:
            return make_envelope(
                {"tool": "stock_screener"},
                source="unavailable",
                warnings=[f"filter error: {exc}"],
                availability="unavailable",
            )
        if technical is not None:
            allowed = {"rsi_lt", "rsi_gt", "above_sma20", "below_sma20"}
            unknown = [k for k in technical if k not in allowed]
            if unknown:
                return make_envelope(
                    {"tool": "stock_screener"},
                    source="unavailable",
                    warnings=[f"unknown technical rules: {unknown}"],
                    availability="unavailable",
                )
            shortlisted = candidates[: max(limit, 1)]

            async def _tech_ok(entry: dict[str, Any]) -> bool:
                sym = str(entry.get("symbol", "")).upper()
                if not sym:
                    return False
                async with sem:
                    try:
                        candles = await run_blocking(
                            functools.partial(vn_p.quote_history, sym, 80),
                            "stock_screener",
                            timeout_secs=10.0,
                        )
                        out = tech_p.compute(candles)
                    except Exception:
                        return False
                try:
                    if "rsi_lt" in technical and not (out["rsi14"] < float(technical["rsi_lt"])):
                        return False
                    if "rsi_gt" in technical and not (out["rsi14"] > float(technical["rsi_gt"])):
                        return False
                    if technical.get("above_sma20") and not (
                        out["sma20"] is not None and out["last"] > out["sma20"]
                    ):
                        return False
                    if technical.get("below_sma20") and not (
                        out["sma20"] is not None and out["last"] < out["sma20"]
                    ):
                        return False
                except (TypeError, ValueError):
                    return False
                return True

            kept = await asyncio.gather(*(_tech_ok(e) for e in shortlisted))
            candidates = [e for e, ok in zip(shortlisted, kept, strict=True) if ok]
        partial = bool(warnings) or (bool(enrich_n) and enriched < enrich_n)
        return await cache_store(
            "stock_screener",
            f"{filters}|{max_pe}|{min_roe}|{limit}|{technical}",
            TTL_SECONDS["overview"],
            {
                "universe": len(rows),
                "filters": eff,
                "candidates": candidates[: max(limit, 1)],
            },
            source="vnstock",
            warnings=warnings,
            availability="partial" if partial else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_screener_columns(
        group: str | None = None, search: str | None = None
    ) -> dict[str, Any]:
        """Screener column catalog (valuation/quality/universe/price). Use to build filters.

        group: keep only that column group; search: keep columns whose
        key or label contains this substring (case-insensitive).
        """
        fp = f"{group}|{search}"
        hit = await cache_lookup("signals_screener_columns", fp)
        if hit is not None:
            return hit
        from opentrading_mcp.providers import screener as sc_p

        cols = sc_p.screener_columns(group=group, search=search)
        if not cols:
            return await cache_store(
                "signals_screener_columns",
                fp,
                TTL_SECONDS["categories"],
                {"count": 0, "group": group, "search": search, "columns": {}},
                source="local",
                availability="empty",
            )
        return await cache_store(
            "signals_screener_columns",
            fp,
            TTL_SECONDS["categories"],
            {"count": len(cols), "group": group, "search": search, "columns": cols},
            source="local",
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_technical(
        symbol: str,
        interval: str = "1D",
        indicators: list[str] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Chấm kỹ thuật đầy đủ từ nến local trên 1D/1W/1M. Dùng khi chọn thời điểm vào lệnh cho 1
            mã.

        Dùng khi: "FPT có nên mua lúc này", RSI/MACD/MA, hỗ trợ/kháng cự, vị trí 52 tuần.
        Không dùng khi: sàng nhiều mã (dùng stock_screener với technical); chỉ cần nến thô (dùng
            vn_quote_history); backtest quy tắc (dùng backtest_strategies).

        indicators: chỉ giữ output nêu tên (vd rsi14, macd, sma20, recommend,
        patterns, support, resistance, rs_vs_bench, pos_52w, sma150, ichimoku,
        swings, swing_trend, fib); bỏ qua để lấy full. interval: 1D (250 nến),
        1W (dài, tối thiểu 30 nến) hoặc 1M (tối thiểu 24 nến); chỉ báo nào chưa đủ
        nến thì null (không điền 50/0). ichimoku (displacement 26 như TradingView, lệch 25
        nến): senkou_a/senkou_b là mây dưới giá hiện tại (tính từ 25 nến trước),
        senkou_*_ahead là mây chiếu tới; chikou là giá đóng cửa 25 nến trước.
        """
        from opentrading_mcp.providers import technicals as tech_p

        # v2: null for uncomputable indicators, Ichimoku cloud under today's price
        fp = f"v2|{symbol}|{interval}|{indicators}"
        hit = await cache_lookup("signals_technical", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"signals_technical {symbol} {interval}")
        warnings_list: list[str] = []
        iv = (interval or "1D").strip().upper()
        if iv not in ("1D", "1W", "1M"):
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[f"unknown interval {interval!r} (1D|1W|1M)"],
                availability="unavailable",
            )
        days = {"1D": 250, "1W": 600, "1M": 1800}[iv]
        min_bars = {"1D": 30, "1W": 30, "1M": 24}[iv]
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, days, iv),
                "signals_technical",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        if not isinstance(candles, list) or len(candles) < min_bars:
            return make_envelope(
                {
                    "symbol": symbol.upper(),
                    "interval": iv,
                    "note": "insufficient history",
                    "n": len(candles) if isinstance(candles, list) else 0,
                },
                source="vnstock",
                warnings=warnings_list,
                availability="empty",
            )
        try:
            bench_candles = await run_blocking(
                functools.partial(vn_p.quote_history, "VNINDEX", days, iv),
                "signals_technical",
            )
            bench = [c["c"] for c in bench_candles if c.get("c")]
        except (ProviderUnavailable, ProviderBadData) as exc:
            bench = []
            warnings_list.append(f"VNINDEX benchmark unavailable: {exc}")
        try:
            out = tech_p.compute(candles, benchmark=bench or None)
        except Exception as exc:
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[f"technicals compute failed: {exc}"],
                availability="unavailable",
            )
        if indicators is not None:
            wanted = {i.lower() for i in indicators}
            out = {k: v for k, v in out.items() if str(k).lower() in wanted}
        return await cache_store(
            "signals_technical",
            fp,
            price_ttl(),
            {"symbol": symbol.upper(), "interval": iv, **out},
            source="computed-local",
            warnings=warnings_list,
        )

    @server.tool(annotations=READ_ONLY)
    async def sector_performance(level: int = 1, top_n: int = 50) -> dict[str, Any]:
        """Dòng heatmap GICS. Dùng khi đọc luân chuyển ngành (ngành nào đang khỏe).

        Dùng khi: "ngành nào đang khỏe", so hiệu suất các ngành.
        Không dùng khi: cần độ rộng toàn sàn (dùng breadth_scan); cần giá trị một ngành theo thời
            gian (dùng vn_global_index hoặc chỉ số ngành tương ứng).

        level: độ sâu cây GICS. top_n: số dòng trả về.
        """
        fp = f"{level}|{top_n}"
        hit = await cache_lookup("sector_performance", fp)
        if hit is not None:
            return hit
        try:
            from opentrading_mcp.providers import vietstock as vs_p

            heatmap = await run_blocking(
                vs_p.industry_heatmap, "sector_performance", timeout_secs=45.0
            )
            rows = heatmap if isinstance(heatmap, list) else heatmap.get("data", [])
            filtered = [
                r
                for r in rows
                if isinstance(r, dict) and int(r.get("Level", level) or level) == level
            ] or rows
            return await cache_store(
                "sector_performance",
                f"{level}|{top_n}",
                TTL_SECONDS["world"],
                {"level": level, "rows": filtered[: max(int(top_n), 1)]},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "sector_performance"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )

    @server.tool(annotations=READ_ONLY)
    async def money_flow(symbols: list[str] | None = None) -> dict[str, Any]:
        """Tổng hợp dòng ngoại: DNSE WS trước, Vietstock đối chiếu sau. Dùng khi đọc smart money
            tổng hợp.

        Dùng khi: "khối ngoại đang mua hay bán", dòng tiền thông minh hôm nay.
        Không dùng khi: cần mua/bán ròng theo ngày để đối chiếu (dùng vs_nn_flow); cần dòng tiền
            live từng mã (dùng dnse_foreign_flow); cần thỏa thuận từng mã (ghép với block_trades —
            độ chi tiết khác nhau: tổng hợp vs từng lệnh).

        symbols: kênh WS cần đọc (mặc định ["VNINDEX"]); cache lạnh thì rơi về
        biểu đồ NN của Vietstock. Lưu ý (issue #38): nhánh DNSE WS chỉ chứa
        foreign flow của các kênh đã subscribe (VN30F1M — futures), trường
        `foreign_scope` khai báo rõ; dòng ngoại toàn thị trường xem vs_nn_flow.
        """
        fp = f"v2|{symbols}"
        hit = await cache_lookup("money_flow", fp)
        if hit is not None:
            return hit
        try:
            from opentrading_mcp.providers import dnse as dnse_mod

            ws = dnse_mod.ws_snapshot(symbols or ["VNINDEX"])
            return await cache_store(
                "money_flow", fp, price_ttl(),
                {
                    "primary": "dnse-ws",
                    "snapshot": ws,
                    "foreign_scope": dnse_mod.WS_FOREIGN_SCOPE,
                    "note": (
                        "WS foreign chỉ phủ các kênh đã subscribe (VN30F1M — futures);"
                        " dòng ngoại toàn thị trường: vs_nn_flow"
                    ),
                },
                source="dnse-ws",
            )
        except ProviderUnavailable:
            pass
        try:
            from opentrading_mcp.providers import vietstock as vs_mod

            data = await run_blocking(
                vs_mod.nn_flow_chart,
                "money_flow",
                timeout_secs=45.0,
            )
            return await cache_store(
                "money_flow", fp, price_ttl(),
                {"primary": "vietstock", "flow": data}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "money_flow"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )

    @server.tool(annotations=READ_WRITE_STATE)
    async def alert_check(rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate price/RSI rules against live quotes. Use for live watch.

        Each rule: {symbol, threshold, metric ('price'|'rsi14'), op ('>'|'gt'|'>='|'gte'|
        '<'|'lt'|'<='|'lte'|'cross_up'|'cross_down')}.
        """
        wanted: dict[str, dict[str, Any]] = {}
        for entry in rules:
            if (
                isinstance(entry, dict)
                and entry.get("symbol")
                and entry.get("threshold") is not None
            ):
                wanted[str(entry["symbol"]).upper()] = entry
        if not wanted:
            return make_envelope(
                {"rules": len(rules), "triggered": [], "note": "rules need symbol+threshold"},
                source="local",
                availability="empty",
            )
        needs_history = any(
            str(e.get("metric", "price")) == "rsi14" for e in wanted.values()
        ) or any(str(e.get("op", ">")) in ("cross_up", "cross_down") for e in wanted.values())
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, list(wanted)),
                "alert_check",
            )
            quotes, _batch_missing = vn_p.split_batch(quotes)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "alert_check"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        # rsi14 metric needs candle history; cross ops need previous values
        history: dict[str, list[dict[str, Any]]] = {}
        prev_state: dict[str, Any] = {}
        warnings_list: list[str] = []
        if _batch_missing:
            warnings_list.append(f"batch partial: {len(_batch_missing)} symbols missing")
        if needs_history:
            from opentrading_mcp.providers import store as st_p

            raw_state = await st_p.acache_get(ALERT_STATE_KEY)
            if isinstance(raw_state, (str, bytes)):
                try:
                    prev_state = json.loads(raw_state)
                except Exception as exc:
                    warnings_list.append(f"alert state unreadable, reset: {exc}")
                    prev_state = {}
            elif isinstance(raw_state, dict):
                prev_state = raw_state
            symbol_list = sorted(
                {str(q.get("symbol", "")).upper() for q in quotes if q.get("symbol")}
            )
            # Bound concurrency to the blocking slots: run_blocking timeouts count
            # queue time, so an unbounded gather over many symbols serializes into
            # mass timeouts on a 2-slot executor.
            alert_sem = asyncio.Semaphore(blocking_slots())

            async def _rsi_history(sym: str) -> Any:
                async with alert_sem:
                    return await run_blocking(
                        functools.partial(vn_p.quote_history, sym, 30),
                        "alert_check_rsi",
                        timeout_secs=20.0,
                    )

            results = await asyncio.gather(
                *(_rsi_history(sym) for sym in symbol_list),
                return_exceptions=True,
            )
            for sym, res in zip(symbol_list, results, strict=True):
                if isinstance(res, BaseException):
                    warnings_list.append(f"{sym}: history fetch failed: {res}")
                elif isinstance(res, list) and res:
                    history[sym] = res

        triggered: list[dict[str, Any]] = []
        for quote in quotes:
            symbol = str(quote.get("symbol", "")).upper()
            rule: dict[str, Any] | None = wanted.get(symbol)
            if rule is None:
                continue
            metric = str(rule.get("metric", "price"))
            if metric == "rsi14":
                candles = history.get(symbol)
                if not candles:
                    warnings_list.append(f"{symbol}: no history for rsi14")
                    continue
                try:
                    out = tech_p.compute(candles)
                    value = float(out["rsi14"])
                except Exception as exc:
                    warnings_list.append(f"{symbol}: rsi14 compute failed: {exc}")
                    continue
            else:
                price = quote.get("close_price") or quote.get("close") or 0
                try:
                    value = float(price)
                except (TypeError, ValueError):
                    continue
            try:
                threshold = float(rule["threshold"])
            except (TypeError, ValueError):
                continue
            op = str(rule.get("op", ">"))
            state_key = f"{symbol}:{metric}"
            if op.startswith("cross"):
                prev = prev_state.get(state_key)
                if prev is None:
                    # first observation: standing beyond threshold fires and seeds
                    hit = value > threshold if op == "cross_up" else value < threshold
                    if hit:
                        warnings_list.append(f"{symbol}: first state seeded for {op}")
                else:
                    try:
                        prev_f = float(prev)
                    except (TypeError, ValueError):
                        continue
                    if op == "cross_up":
                        hit = prev_f <= threshold and value > threshold
                    else:
                        hit = prev_f >= threshold and value < threshold
                prev_state[state_key] = value
            elif op in (">", "gt"):
                hit = value > threshold
            elif op in (">=", "gte"):
                hit = value >= threshold
            elif op in ("<", "lt"):
                hit = value < threshold
            elif op in ("<=", "lte"):
                hit = value <= threshold
            else:
                hit = value < threshold
            if hit:
                triggered.append(
                    {
                        "symbol": symbol,
                        "metric": metric,
                        "price": value,
                        "op": op,
                        "threshold": threshold,
                    }
                )
        if needs_history and prev_state:
            await st_p.acache_set(ALERT_STATE_KEY, prev_state, ttl_seconds=ALERT_STATE_TTL)
        return make_envelope(
            {"rules": len(rules), "evaluated": len(quotes), "triggered": triggered},
            source="computed-local",
            warnings=warnings_list,
        )

    return [
        {"name": "stock_screener"},
        {"name": "signals_screener_columns"},
        {"name": "signals_technical"},
        {"name": "sector_performance"},
        {"name": "money_flow"},
        {"name": "alert_check"},
    ]
