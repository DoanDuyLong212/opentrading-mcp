"""#141: sample-check published values against primary sources (owner-run).

The tool-side half of the audit runs here: each sample calls the tool and reads
the specific published value. The comparison half (HOSE/HNX, the company's IR
report, SBV, GSO with a URL and a date) needs credentials and human eyes, so the
table renders with empty `primary source` / `match` columns. Nothing is ever
marked as matching without that evidence.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

GROUP_STATEMENT = "statement"
GROUP_PRICE = "price"
GROUP_INDEX = "index"
GROUP_MACRO = "macro"


@dataclass(frozen=True)
class Sample:
    id: str
    group: str
    tool: str
    args: dict[str, Any]
    read: Callable[[dict[str, Any]], Any]
    expect: str


# --------------------------------------------------------------------- readers --


def _last(values: Any) -> Any:
    if isinstance(values, dict):
        return next(reversed(values.values()), None) if values else None
    if isinstance(values, list):
        return values[-1] if values else None
    return None


def _statement(section: str, needle: str) -> Callable[[dict[str, Any]], Any]:
    """Newest value of the statement row whose name contains `needle`."""

    def read(data: dict[str, Any]) -> Any:
        rows = (data.get("statements") or {}).get(section) or []
        row = next(
            (r for r in rows if needle.lower() in str(r.get("name", "")).lower()), None
        )
        if row is None:
            raise LookupError(f"row {needle!r} not found in {section}")
        periods = data.get("periods") or []
        values = row.get("values") or {}
        period = periods[-1] if periods else None
        keyed = isinstance(values, dict) and period in values
        picked = values.get(period) if keyed else _last(values)
        return {"name": row.get("name"), "period": period, "value": picked, "unit": row.get("unit")}

    return read


def _detail(needle: str) -> Callable[[dict[str, Any]], Any]:
    """Newest value of a `financial_detail` row (values align with `periods`)."""

    def read(data: dict[str, Any]) -> Any:
        rows = data.get("rows") or []
        row = next((r for r in rows if needle.lower() in str(r.get("name", "")).lower()), None)
        if row is None:
            raise LookupError(f"row {needle!r} not found in {data.get('statement')}")
        periods = data.get("periods") or []
        return {
            "name": row.get("name"),
            "period": periods[-1] if periods else None,
            "value": _last(row.get("values")),
            "unit": "tỷ đồng (financial_detail)",
        }

    return read


def _last_bar(data: dict[str, Any]) -> Any:
    bars = data.get("candles") or []
    if not bars:
        raise LookupError("no candles")
    bar = bars[-1]
    return {"date": bar.get("t"), "close": bar.get("c"), "volume": bar.get("v")}


def _bar_on(day: str) -> Callable[[dict[str, Any]], Any]:
    def read(data: dict[str, Any]) -> Any:
        bar = next(
            (b for b in data.get("candles") or [] if str(b.get("t", ""))[:10] == day), None
        )
        if bar is None:
            raise LookupError(f"no bar dated {day}")
        return {"date": bar.get("t"), "close": bar.get("c"), "volume": bar.get("v")}

    return read


def _sbv(table: str, needle: str) -> Callable[[dict[str, Any]], Any]:
    def read(data: dict[str, Any]) -> Any:
        rows = data.get(table) or []
        row = next(
            (r for r in rows if needle.lower() in str(r.get("name", "")).lower()),
            rows[0] if rows and not needle else None,
        )
        if row is None:
            raise LookupError(f"{needle!r} not on the SBV {table} table")
        return {"name": row.get("name"), "value": row.get("value"), "as_of": data.get("as_of")}

    return read


def _fx_leg(*symbols: str) -> Callable[[dict[str, Any]], Any]:
    """Leg by published symbol; the gold leg is served as GC=F, so aliases are allowed."""

    def read(data: dict[str, Any]) -> Any:
        legs = data.get("series") or []
        for symbol in symbols:
            leg = next((x for x in legs if x.get("symbol") == symbol), None)
            if leg is not None:
                return {
                    "symbol": leg.get("symbol"),
                    "unit": leg.get("unit"),
                    "last": leg.get("last"),
                }
        raise LookupError(f"none of {symbols} in payload")

    return read


def _row_field(
    code_key: str, code: str, field: str, unit: str
) -> Callable[[dict[str, Any]], Any]:
    """Read `field` from the payload row whose `code_key` equals `code`.

    vn_retail_fx rows are {currency_code, buy_cash, buy_transfer, sell} and
    vn_retail_gold rows are {name, code, buy_price, sell_price}; neither uses
    the statement shape, so the field must be named explicitly.
    """

    def read(data: dict[str, Any]) -> Any:
        rows = data.get("rows") or []
        row = next((r for r in rows if str(r.get(code_key)) == code), None)
        if row is None:
            raise LookupError(f"row {code_key}={code} not in payload")
        return {
            "name": row.get("name") or row.get("currency_name"),
            "value": row.get(field),
            "unit": data.get("unit") or unit,
        }

    return read


def _last_point(data: dict[str, Any]) -> Any:
    """Newest year. world_macro_country returns points newest-first, not oldest-first."""
    points = data.get("points") or []
    if not points:
        raise LookupError("no points")
    return max(points, key=lambda point: str(point.get("t", "")))


# --------------------------------------------------------------------- samples --

DIVIDEND_DAY = "2026-07-23"


def _samples() -> tuple[Sample, ...]:
    out: list[Sample] = []

    def _stmt(symbol: str, period: str, section: str, needle: str, expect: str) -> Sample:
        return Sample(
            id=f"stmt-{symbol}-{period}-{needle[:12].strip().lower().replace(' ', '-')}",
            group=GROUP_STATEMENT,
            tool="financial_statements",
            args={"symbol": symbol, "period": period, "statement": section, "periods_n": 4},
            read=_statement(section, needle),
            expect=expect,
        )

    def _cfo(symbol: str) -> Sample:
        return Sample(
            id=f"cfo-{symbol}-annual",
            group=GROUP_STATEMENT,
            tool="financial_detail",
            args={"symbol": symbol, "statement": "LCTT", "periods_n": 4},
            read=_detail("Lưu chuyển tiền thuần từ hoạt động kinh doanh"),
            expect=f"{symbol}: lưu chuyển tiền thuần HĐKD năm gần nhất",
        )

    # 15 statement items: revenue, net profit, equity + three cash-flow rows.
    for symbol, expect in (("FPT", "quý gần nhất"), ("HPG", "quý gần nhất")):
        out.append(_stmt(symbol, "quarter", "KQKD", "Doanh thu", f"{symbol} doanh thu {expect}"))
        out.append(
            _stmt(symbol, "quarter", "KQKD", "Lợi nhuận sau thuế", f"{symbol} LNST {expect}")
        )
        out.append(
            _stmt(symbol, "quarter", "CDKT", "Vốn chủ sở hữu", f"{symbol} vốn chủ {expect}")
        )
    out.extend(_cfo(s) for s in ("VCB", "FPT", "HPG"))
    for symbol in ("VNM", "MWG"):
        out.append(
            _stmt(symbol, "year", "KQKD", "Doanh thu", f"{symbol} doanh thu năm gần nhất")
        )
        out.append(
            _stmt(symbol, "year", "KQKD", "Lợi nhuận sau thuế", f"{symbol} LNST năm gần nhất")
        )
    out.append(_stmt("VCB", "year", "KQKD", "Lợi nhuận sau thuế", "VCB LNST năm gần nhất"))
    out.append(_stmt("VCB", "year", "CDKT", "Vốn chủ sở hữu", "VCB vốn chủ năm gần nhất"))

    # 10 prices: 5 latest closes + 5 bars on a dividend/bonus date (adjusted vs raw).
    for symbol in ("FPT", "HPG", "VCB", "MWG", "SSI"):
        out.append(
            Sample(
                id=f"price-{symbol}-last",
                group=GROUP_PRICE,
                tool="vn_quote_history",
                args={"symbol": symbol, "days": 300},
                read=_last_bar,
                expect=f"{symbol}: giá đóng cửa phiên gần nhất (nguồn: HOSE/HNX, IR)",
            )
        )
    for symbol in ("FPT", "HPG", "VCB", "MWG", "SSI"):
        out.append(
            Sample(
                id=f"price-{symbol}-{DIVIDEND_DAY}",
                group=GROUP_PRICE,
                tool="vn_quote_history",
                args={"symbol": symbol, "days": 400},
                read=_bar_on(DIVIDEND_DAY),
                expect=(
                    f"{symbol}: nến {DIVIDEND_DAY} quanh sự kiện cổ tức/thưởng — "
                    "kiểm tra giá đã điều chỉnh hay chưa"
                ),
            )
        )

    # 5 index levels.
    for symbol in ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX", "VN100"):
        out.append(
            Sample(
                id=f"index-{symbol}",
                group=GROUP_INDEX,
                tool="vn_quote_history",
                args={"symbol": symbol, "days": 30},
                read=_last_bar,
                expect=f"{symbol}: điểm đóng cửa gần nhất (nguồn: HOSE/HNX)",
            )
        )

    # 10 macro values.
    out.extend(
        [
            Sample(
                id="macro-sbv-refinancing",
                group=GROUP_MACRO,
                tool="sbv_rates",
                args={},
                read=_sbv("policy", "tái cấp vốn"),
                expect="Lãi suất tái cấp vốn SBV",
            ),
            Sample(
                id="macro-sbv-discount",
                group=GROUP_MACRO,
                tool="sbv_rates",
                args={},
                read=_sbv("policy", "tái chiết khấu"),
                expect="Lãi suất tái chiết khấu SBV",
            ),
            Sample(
                id="macro-usdvnd-vcb-sell",
                group=GROUP_MACRO,
                tool="vn_retail_fx",
                args={},
                read=_row_field("currency_code", "USD", "sell", "VND/USD"),
                expect="USD/VND giá bán Vietcombank (nguồn: VCB)",
            ),
            Sample(
                id="macro-usdvnd-vcb-buy-transfer",
                group=GROUP_MACRO,
                tool="vn_retail_fx",
                args={},
                read=_row_field("currency_code", "USD", "buy_transfer", "VND/USD"),
                expect="USD/VND giá mua chuyển khoản Vietcombank (nguồn: VCB)",
            ),
            Sample(
                id="macro-eur-vcb-sell",
                group=GROUP_MACRO,
                tool="vn_retail_fx",
                args={},
                read=_row_field("currency_code", "EUR", "sell", "VND/EUR"),
                expect="EUR/VND giá bán Vietcombank (nguồn: VCB)",
            ),
            Sample(
                id="macro-usdvnd-interbank",
                group=GROUP_MACRO,
                tool="vn_msn_fx_gold",
                args={"symbols": ["USDVND"], "days": 10},
                read=_fx_leg("USDVND"),
                expect="USD/VND liên ngân hàng (nguồn: SBV/Reuters)",
            ),
            Sample(
                id="macro-gold-futures",
                group=GROUP_MACRO,
                tool="vn_msn_fx_gold",
                args={"symbols": ["GOLD"], "days": 10},
                read=_fx_leg("GOLD", "GC=F", "XAUUSD"),
                expect="Vàng COMEX GC=F (USD/ozt) — KHÔNG phải SJC/XAU spot",
            ),
            Sample(
                id="macro-gold-sjc",
                group=GROUP_MACRO,
                tool="vn_retail_gold",
                args={},
                read=_row_field("code", "SJC", "sell_price", "đồng/chỉ"),
                expect="Vàng miếng SJC 999.9 giá bán (nguồn: PNJ/SJC)",
            ),
            Sample(
                id="macro-vn-gdp",
                group=GROUP_MACRO,
                tool="world_macro_country",
                args={"iso3": "VNM", "indicator": "NY.GDP.MKTP.KD.ZG", "limit": 5},
                read=_last_point,
                expect="GDP Việt Nam tăng trưởng (%) — đối chiếu GSO",
            ),
            Sample(
                id="macro-vn-cpi",
                group=GROUP_MACRO,
                tool="world_macro_country",
                args={"iso3": "VNM", "indicator": "FP.CPI.TOTL.ZG", "limit": 5},
                read=_last_point,
                expect="CPI Việt Nam (%) — đối chiếu GSO",
            ),
        ]
    )
    return tuple(out)


SAMPLES: tuple[Sample, ...] = _samples()


# --------------------------------------------------------------------- collect --


@dataclass
class Row:
    sample: Sample
    status: str = "pending"
    value: Any = None
    as_of: str | None = None
    availability: str | None = None
    warnings: list[str] = field(default_factory=list)
    note: str = ""


async def collect(
    samples: tuple[Sample, ...] = SAMPLES,
    fns: dict[str, Callable[..., Any]] | None = None,
) -> list[Row]:
    """Call each sample's tool and read the published value; never invent one."""
    if fns is None:
        from opentrading_mcp.server import create_server, register_all

        server = create_server("all")
        register_all(server)
        fns = {tool.name: tool.fn for tool in server._tool_manager.list_tools()}
    rows: list[Row] = []
    for sample in samples:
        row = Row(sample=sample)
        fn = fns.get(sample.tool)
        if fn is None:
            row.status = "unknown_tool"
            row.note = f"{sample.tool} is not registered"
            rows.append(row)
            continue
        try:
            envelope = fn(**sample.args)
            if inspect.isawaitable(envelope):
                envelope = await envelope
        except Exception as exc:  # a failed sample must not abort the audit
            row.status = "error"
            row.note = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue
        body = envelope if isinstance(envelope, dict) else {}
        data = body.get("data")
        row.availability = body.get("availability")
        row.as_of = (body.get("provenance") or {}).get("as_of")
        row.warnings = list(body.get("warnings") or [])
        if row.availability in ("unavailable", "empty"):
            row.status = row.availability
            row.note = "; ".join(row.warnings[:2])
            rows.append(row)
            continue
        try:
            row.value = sample.read(data or {})
        except Exception as exc:
            row.status = "unresolved"
            row.note = f"{type(exc).__name__}: {exc}"
        else:
            row.status = "collected"
        rows.append(row)
    return rows


def render_markdown(
    rows: list[Row], *, title: str = "Sample check vs primary sources (#141)"
) -> str:
    """Table for the issue: tool side filled, human side blank on purpose."""
    lines = [
        f"# {title}",
        "",
        "Generated by `scripts/source_sample_check.py`. Columns `primary source`, "
        "`match`, `notes` are filled by a person with the source URL and date. "
        "`collected` means the tool returned a value — NOT that it is correct.",
        "",
        f"Rows: {len(rows)}",
        "",
        "| # | group | tool | args | value | unit/period | as_of | status | "
        "primary source (URL + date) | match | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n, row in enumerate(rows, start=1):
        value = row.value
        unit = ""
        if isinstance(value, dict):
            unit = str(value.get("unit") or value.get("period") or "")
            value = {k: v for k, v in value.items() if k not in ("unit", "period")}
        rendered = "—" if value is None else str(value).replace("|", "\\|")
        args = str(row.sample.args).replace("|", "\\|")
        note = (row.note or "; ".join(row.warnings[:2])).replace("|", "\\|")
        lines.append(
            f"| {n} | {row.sample.group} | {row.sample.tool} | {args} | {rendered} | "
            f"{unit.replace('|', chr(92) + '|')} | {row.as_of or '—'} | {row.status} | "
            f" |  | {note} |"
        )
    lines.append("")
    lines.append("Expectation per row (what the primary source must show):")
    lines.append("")
    for n, row in enumerate(rows, start=1):
        lines.append(f"{n}. {row.sample.id}: {row.sample.expect}")
    lines.extend(
        [
            "",
            "Known gaps (reported, not guessed): the SBV public rate page served policy rows only",
            "and an empty interbank table, so the interbank interest rate has no row here; it",
            "needs a primary source the project can reach. Vietstock statements and all",
            "SSI/DNSE-derived",
            "price rows stay `unavailable` until provider credentials are set.",
        ]
    )
    return "\n".join(lines) + "\n"


def main_rows_sync(samples: tuple[Sample, ...] = SAMPLES) -> list[Row]:
    return asyncio.run(collect(samples))
