"""Quant backtest: backtest, sweep, scenario (sandbox local)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.quant_shared import (
    _condition_gate,
    _dated_closes,
    _run_strategy,
    _yf_closes,
)
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
)
from opentrading_mcp.tools.shared import (
    run_blocking as _run_blocking,
)


async def run_blocking(fn, tool, timeout_secs=60.0):
    """Compute-module alias: all blocking work here rides the heavy pool."""
    return await _run_blocking(fn, tool, timeout_secs, heavy=True)


def register_quant_backtest_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def quant_backtest(
        symbol: str,
        cost_bps: float = 10.0,
        strategy: str = "buy_hold",
        slippage_bps: float = 5.0,
        benchmark: str = "VNINDEX",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Backtest mua-giữ kèm chi phí trên lịch sử có sẵn. Dùng khi cần baseline so sánh.

        Dùng khi: baseline "nếu mua giữ 1 năm thì bao nhiêu".
        Không dùng khi: cần chiến lược có quy tắc (SMA/momentum/RSI — dùng backtest_strategies,
            engine thật); cần rủi ro từ chuỗi return (dùng quant_risk).

        Deprecated cho chiến lược: dùng backtest_strategies cho mọi thứ ngoài buy-and-hold.
        strategy: chỉ là nhãn ghi lại (engine là buy-and-hold). cost_bps/slippage_bps:
        bps khứ hồi, mỗi loại trừ 2 lần từ gross. benchmark: nhãn chỉ số tham chiếu.
        """
        fp = f"{symbol}|{cost_bps}|{strategy}|{slippage_bps}|{benchmark}"
        hit = await cache_lookup("quant_backtest", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.report_progress(0, 2, "load candles")
        try:
            candles = await run_blocking(
                # One trading year (~250 sessions): quote_history counts candles.
                functools.partial(vn_p.quote_history, symbol, 250),
                "quant_backtest",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "quant_backtest"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < 2:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        gross = closes[-1] / closes[0] - 1
        net = gross - (cost_bps + slippage_bps) / 10000 * 2
        if ctx is not None:
            await ctx.report_progress(2, 2, "done")
        base = closes[0] or 1.0
        curve = [round(c / base - 1.0, 4) for c in closes]
        step = max(1, len(curve) // 100)
        return await cache_store(
            "quant_backtest",
            fp,
            TTL_SECONDS["hour"],
            {
                "symbol": symbol.upper(),
                "strategy": strategy,
                "benchmark": benchmark,
                "gross_return": round(gross, 4),
                "net_return": round(net, 4),
                "bars": len(closes),
                "cost_bps": cost_bps,
                "slippage_bps": slippage_bps,
                "equity_curve": curve[::step],
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def scenario_simulate(
        scenario: str, symbol: str = "VCB", shock_pct: float = -5.0
    ) -> dict[str, Any]:
        """Đặt cú sốc giá lên giá đóng gần nhất rồi tính L/L mỗi 1000 cổ phiếu. Dùng khi đo khẩu vị
            rủi ro (sizing).

        Dùng khi: "nếu HPG xấu -5% thì mất bao nhiêu".
        Không dùng khi: backtest lịch sử (dùng quant_backtest/backtest_strategies); rủi ro thống kê
            (dùng quant_risk).

        shock_pct: % cú sốc, âm là giảm (ví dụ -5.0). Giá theo nghìn đồng/cổ phiếu như nến;
        pnl_per_1000_shares tính bằng nghìn đồng (-1062,5 = -1.062.500 đ).
        """
        fp = f"{scenario}|{symbol}|{shock_pct}"
        hit = await cache_lookup("scenario_simulate", fp)
        if hit is not None:
            return hit
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 10),
                "scenario_simulate",
                timeout_secs=60.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "scenario_simulate"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if not closes:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        last = closes[-1]
        shocked_exact = last * (1 + shock_pct / 100)
        shocked = round(shocked_exact, 2)
        return await cache_store(
            "scenario_simulate",
            fp,
            TTL_SECONDS["overview"],
            {
                "scenario": scenario,
                "symbol": symbol.upper(),
                "last_close": last,
                "shock_pct": shock_pct,
                "shocked_price": shocked,
                # from the unrounded price: HPG 21.25 -5% is -1062.5, not -1060
                "pnl_per_1000_shares": round((shocked_exact - last) * 1000, 1),
                "assumptions": ["linear shock, no liquidity slippage"],
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def backtest_strategies(
        symbol: str,
        strategy: str = "sma_cross",
        fast: int = 10,
        slow: int = 30,
        cost_bps: float = 10.0,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        months: list[int] | None = None,
        quarters: list[int] | None = None,
        condition_symbol: str | None = None,
        condition_rule: str = "above_sma",
        condition_lookback: int = 20,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Backtest theo quy tắc ngoài mua-giữ. Dùng khi so các quy tắc canh thời điểm trên 1 mã.

        Dùng khi: "nếu cắt MA50 có tốt hơn mua giữ không", kiểm định chiến lược giao
            cắt/seasonality.
        Không dùng khi: chỉ cần baseline mua-giữ (dùng quant_backtest — gọn hơn); kỹ thuật hiện tại
            không backtest (dùng signals_technical).

        strategy: 'sma_cross' (SMA nhanh vượt SMA chậm), 'momentum' (giá trên
        giá[slow] phiên trước), 'rsi_meanrev' (long khi RSI14 < rsi_low, flat khi
        RSI14 > rsi_high), 'buy_hold'. fast/slow: số nến nhìn lại. cost_bps:
        bps mỗi chiều, trừ một lần tại mỗi khớp mua/bán. months/quarters: chỉ vào lệnh theo
        tháng (1-12) / quý (1-4); thoát lệnh luôn cho phép.
        condition_symbol: chặn vào lệnh theo tài sản khác (dầu/vàng/FX: BZ=F, GC=F,
        USDVND...); condition_rule 'above_sma' (trên SMA của nó) hoặc 'rising'
        (đang tăng trong condition_lookback nến). Mã VN qua vnstock, khác qua
        lịch ngày yfinance.
        """
        fp = (f"v2|{symbol}|{strategy}|{fast}|{slow}|{cost_bps}|{rsi_low}|{rsi_high}|"
              f"{months}|{quarters}|{condition_symbol}|{condition_rule}|{condition_lookback}")
        hit = await cache_lookup("backtest_strategies", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"backtest_strategies {symbol} {strategy}")
        if strategy not in ("sma_cross", "momentum", "buy_hold", "rsi_meanrev"):
            return make_envelope(
                {"tool": "backtest_strategies"},
                source="unavailable",
                warnings=[f"unknown strategy {strategy!r}"],
                availability="unavailable",
            )
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 365),
                "backtest_strategies",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "backtest_strategies"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        dates, closes, _walked = _dated_closes(candles)
        opens = [c.get("o") for c in candles if c["c"]]
        cond_ok: list[bool] | None = None
        cond_warn: list[str] = []
        if condition_symbol:
            csym = condition_symbol.strip().upper()
            rule = (condition_rule or "above_sma").strip().lower()
            if rule not in ("above_sma", "rising"):
                return make_envelope(
                    {"tool": "backtest_strategies"},
                    source="unavailable",
                    warnings=[f"unknown condition_rule {condition_rule!r}"],
                    availability="unavailable",
                )
            cd: list[Any] | None = None
            cc: list[float] | None = None
            try:
                cc_candles = await run_blocking(
                    functools.partial(vn_p.quote_history, csym, 400),
                    "backtest_strategies",
                    timeout_secs=60.0,
                )
                cd, cc, _ = _dated_closes(cc_candles)
            except (ProviderUnavailable, ProviderBadData):
                try:
                    cd, cc = await run_blocking(
                        functools.partial(_yf_closes, csym),
                        "backtest_strategies",
                        timeout_secs=60.0,
                    )
                except (ProviderUnavailable, ProviderBadData) as exc2:
                    return make_envelope(
                        {"tool": "backtest_strategies"},
                        source="unavailable",
                        warnings=[f"condition asset {csym} unavailable: {exc2}"],
                        availability="unavailable",
                    )
            assert cd is not None and cc is not None
            cond_ok = _condition_gate(dates, cd, cc, rule, condition_lookback)
            cond_warn.append(
                f"condition-gated on {csym} ({rule}/{condition_lookback}); exits always allowed"
            )
        res = _run_strategy(
            closes,
            strategy,
            fast,
            slow,
            cost_bps,
            dates=dates,
            rsi_low=rsi_low,
            rsi_high=rsi_high,
            months=months,
            quarters=quarters,
            cond_ok=cond_ok,
            opens=opens,
            dates_inferred=_walked,
        )
        out: dict[str, Any] = {
            "symbol": symbol.upper(),
            "strategy": strategy,
            "fast": fast,
            "slow": slow,
            "cost_bps": cost_bps,
            **res,
        }
        if strategy == "rsi_meanrev":
            out["rsi_low"] = rsi_low
            out["rsi_high"] = rsi_high
        if months or quarters:
            out["months"] = months
            out["quarters"] = quarters
        if condition_symbol:
            out["condition_symbol"] = condition_symbol.strip().upper()
            out["condition_rule"] = (condition_rule or "above_sma").strip().lower()
            out["condition_lookback"] = condition_lookback
        warn: list[str] = []
        if months or quarters:
            warn.append(
                "month-filtered: entries only in "
                f"months={months} quarters={quarters}; exits always allowed"
            )
        warn.extend(cond_warn)
        return await cache_store(
            "backtest_strategies", fp, TTL_SECONDS["hour"],
            out, source="computed-local", warnings=warn,
        )

    @server.tool(annotations=READ_ONLY)
    async def param_sweep(
        symbol: str,
        strategy: str = "sma_cross",
        fast_range: list[int] | None = None,
        slow_range: list[int] | None = None,
        cost_bps: float = 10.0,
        months: list[int] | None = None,
        quarters: list[int] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Grid-search strategy lookbacks, ranked by net return. Use to avoid overfit picks.

        fast_range/slow_range: candidate bars (product capped at 30 combos).
        rsi_meanrev allowed (fixed 30/70 thresholds). months/quarters passthrough.
        """
        fp = f"v2|{symbol}|{strategy}|{fast_range}|{slow_range}|{cost_bps}|{months}|{quarters}"
        hit = await cache_lookup("param_sweep", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"param_sweep {symbol} {strategy}")
        if strategy not in ("sma_cross", "momentum", "rsi_meanrev"):
            return make_envelope(
                {"tool": "param_sweep"},
                source="unavailable",
                warnings=[f"sweep supports sma_cross|momentum|rsi_meanrev, got {strategy!r}"],
                availability="unavailable",
            )
        fasts = [max(int(f), 2) for f in (fast_range or [5, 10, 20])][:6]
        slows = [max(int(s), 3) for s in (slow_range or [20, 30, 60])][:6]
        combos = [(f, s) for f in fasts for s in slows if s > f][:30]
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 365),
                "param_sweep",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "param_sweep"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        opens = [c.get("o") for c in candles if c["c"]]
        dates, _, walked = _dated_closes(candles)
        ranked = []
        for f, s in combos:
            res = _run_strategy(
                closes,
                strategy,
                f,
                s,
                cost_bps,
                dates=dates,
                months=months,
                quarters=quarters,
                opens=opens,
                dates_inferred=walked,
            )
            ranked.append({"fast": f, "slow": s, **res})
        ranked.sort(key=lambda r: r["net_return"], reverse=True)
        return await cache_store(
            "param_sweep",
            fp,
            TTL_SECONDS["hour"],
            {
                "symbol": symbol.upper(),
                "strategy": strategy,
                "combos_evaluated": len(ranked),
                "months": months,
                "quarters": quarters,
                "ranked": ranked,
            },
            source="computed-local",
        )

    return [
        {"name": "quant_backtest"},
        {"name": "scenario_simulate"},
        {"name": "backtest_strategies"},
        {"name": "param_sweep"},
    ]
