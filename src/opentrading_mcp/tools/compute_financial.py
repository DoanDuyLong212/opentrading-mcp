"""Compute financial tools: forensic, valuation, statements, ratios, peers."""

from __future__ import annotations

import functools
import json
import math
import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from pandas.api.types import is_bool

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.forensic_models import calculate_forensic
from opentrading_mcp.providers import forensic as forensic_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
    price_ttl,
    run_blocking,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


def _finite_metric(value: Any) -> float | None:
    """Reject booleans and non-finite provider values before financial division."""
    if value is None or is_bool(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def _find_numbers(payload: Any, *needles: str, limit: int = 12) -> list[float]:
    found: list[float] = []

    def walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_low = str(key).lower()
                if any(n in key_low for n in needles) and isinstance(value, (int, float)):
                    found.append(float(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _read_runs() -> list[dict[str, Any]] | None:
    path = os.environ.get("MCP_RUNS_FILE", "data/runs.jsonl")
    if not os.path.exists(path):
        return None
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


_ROW_NUMBERING = re.compile(r"^\s*(?:[IVXL]+|[A-Za-z]|\d{1,2})\.\s*")
_ROW_TRAILER = re.compile(r"\s*\([^)]*\)\s*$")


def _row_name(name: Any) -> str:
    """'XIII. Lợi nhuận sau thuế (XI-XII)' -> 'lợi nhuận sau thuế'."""
    text = _ROW_NUMBERING.sub("", str(name or ""))
    text = _ROW_TRAILER.sub("", text)
    return " ".join(text.lower().split())


def _fd_row(
    detail: dict[str, Any], norm_ids: tuple[int, ...], names: tuple[str, ...]
) -> list[float | None]:
    """Values of ONE statement line: the first norm_id in `norm_ids` present, else the
    first row whose name (numbering and trailing '(...)' stripped) equals one of `names`.

    Never sums rows. Matching by substring and summing added a total to its own
    sub-items (FPT receivables 13,501 + 10,851 + 811) and, on a bank statement, put
    "TỔNG NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU" into both debt and equity.
    """
    if not isinstance(detail, dict):
        return []
    rows = [r for r in detail.get("rows") or [] if isinstance(r, dict)]
    chosen = None
    for norm_id in norm_ids:
        chosen = next((r for r in rows if r.get("norm_id") == norm_id), None)
        if chosen is not None:
            break
    if chosen is None:
        chosen = next((r for r in rows if _row_name(r.get("name")) in names), None)
    if chosen is None:
        return []
    values = [float(v) if isinstance(v, (int, float)) else None for v in chosen.get("values") or []]
    return values if any(v is not None for v in values) else []


# Statement lines used by stock_forensic: Vietstock norm ids of the general (FPT), bank
# (VCB), securities (SSI) and insurance (BVH) templates, checked live 2026-10-23, then
# exact line names for any other template.
_FD_LINES: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "revenue": (
        (2216, 4385, 4590, 3204),
        ("doanh thu thuần về bán hàng và cung cấp dịch vụ", "doanh thu thuần",
         "thu nhập lãi thuần", "doanh thu thuần hđkd bh"),
    ),
    "gross": (
        (2217, 4592, 3205),
        ("lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "lợi nhuận gộp",
         "lợi nhuận gộp của hoạt động kinh doanh",
         "lợi nhuận gộp hoạt động kinh doanh bảo hiểm"),
    ),
    "net_income": (
        (2212, 4378, 4585, 3200),
        ("lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế",
         "lợi nhuận kế toán sau thuế tndn"),
    ),
    "selling": ((2227, 5478, 3251), ("chi phí bán hàng",)),
    "admin": ((2224, 3231), ("chi phí quản lý doanh nghiệp", "chi phí quản lý")),
    "receivables": ((3005, 4484, 3104), ("các khoản phải thu ngắn hạn",)),
    "assets": ((2996, 4375, 4476, 3095), ("tổng cộng tài sản",)),
    "cash": (
        (3003, 4774, 3102),
        ("tiền và các khoản tương đương tiền", "tiền và tương đương tiền"),
    ),
    "current_assets": ((3000, 4480, 3099), ("tài sản ngắn hạn",)),
    "current_liabilities": ((3014, 4493, 3113), ("nợ ngắn hạn",)),
    "liabilities": ((2997, 4304, 4477, 3096), ("nợ phải trả", "tổng nợ phải trả")),
    "equity": ((2998, 4325, 4478, 3097), ("vốn chủ sở hữu", "vốn và các quỹ")),
    "cfo": ((2234,), ("lưu chuyển tiền thuần từ hoạt động kinh doanh",)),
}


def _fd_line(detail: dict[str, Any], line: str) -> list[float | None]:
    norm_ids, names = _FD_LINES[line]
    return _fd_row(detail, norm_ids, names)


# vnstock ratio items computed from the price on the period's closing date. A model
# asked for "P/E hiện tại" read FY2025 p_e 15.91 as today's multiple (live ~9.5), so
# these rows are labelled as period-end values in every response that carries them.
_PERIOD_END_PRICE_ITEMS = frozenset(
    {"p_e", "p_b", "p_s", "ev_ebit", "ev_ebitda", "dividend_yield"}
)
_PERIOD_END_SUFFIX = " — tại ngày kết thúc kỳ, không phải giá trị hiện tại"
_PERIOD_END_NOTE = (
    "P/E, P/B, P/S, EV/EBIT, EV/EBITDA, tỷ suất cổ tức ở đây tính theo giá ngày kết thúc"
    " từng kỳ báo cáo, KHÔNG phải bội số hiện tại. Bội số theo giá hôm nay: stock_overview"
    " (PE, PB) hoặc valuation_run (per, pb)."
)


def _label_period_end(row: dict[str, Any]) -> dict[str, Any]:
    """Mark a price-based ratio row as a period-end value; other rows pass unchanged."""
    if row.get("item_id", "").lower() not in _PERIOD_END_PRICE_ITEMS:
        return row
    return {**row, "item": f"{row['item']}{_PERIOD_END_SUFFIX}", "as_of": "period_end"}


# peer_compare metric spellings -> vnstock ratio item_id.
_PEER_METRIC_ALIASES = {
    "pe": "p_e", "p/e": "p_e", "pb": "p_b", "p/b": "p_b", "ps": "p_s",
    "eps": "trailing_eps", "bvps": "book_value_per_share_bvps",
}



def _ratio_quality(ratios: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep source quality flags when a ratio series is projected to one value."""
    return {
        ratio["item_id"]: {
            key: ratio[key]
            for key in ("suspected_placeholder", "quality_note") if key in ratio
        }
        for ratio in ratios
        if "suspected_placeholder" in ratio or "quality_note" in ratio
    }


def register_compute_financial_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_forensic(
        symbol: str,
        detail: bool = False,
        periods_n: int = 4,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Kiểm tra chất lượng lợi nhuận từ các báo cáo năm cùng kỳ và cùng pháp nhân.

        Beneish 8 biến theo bản CFO 2013; Piotroski 9 tín hiệu, turnover dùng
        assets đầu năm (§2.3.3). Chỉ có điểm chuẩn khi đủ input hợp lệ;
        thiếu thì score=null cùng coverage, nguồn, kỳ và danh sách thiếu.
        Ngành tài chính: Beneish không áp dụng, Piotroski chưa được hỗ trợ.
        Đây là tín hiệu cần kiểm tra thêm, không phải kết luận gian lận.
        detail=true giữ input và chẩn đoán nguồn; periods_n chỉ giới hạn hiển thị,
        không cắt lịch sử cần cho phép tính annual.
        """
        sym = symbol.strip().upper()
        display_n = max(1, int(periods_n))
        fp = f"v5|{sym}|{detail}|{display_n}"
        hit = await cache_lookup("stock_forensic", fp)
        if hit is not None:
            return hit
        try:
            bundle = await _call("forensic-annual", forensic_p.annual_inputs, sym, secs=60.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_forensic", str(exc))
        out = calculate_forensic(bundle)
        warnings = list(bundle.get("limitations") or [])
        warnings.extend(str(r.get("reason")) for r in bundle.get("rejected", []))
        complete = all(out[model]["status"] == "complete" for model in ("beneish", "piotroski"))
        if not complete:
            warnings.append(
                "Annual forensic models incomplete or inapplicable; "
                "inspect model status and missing_inputs"
            )
        if detail:
            records = (bundle.get("records") or [])[-display_n:]
            out["series"] = {
                key: [r.get("values", {}).get(key) for r in records]
                for key in sorted({k for r in records for k in r.get("values", {})})
            }
            out["annual_inputs"] = records
            out["diagnostics"] = bundle.get("diagnostics", [])
            out["rejected"] = bundle.get("rejected", [])
        if ctx is not None:
            await ctx.log("info", f"stock_forensic {sym} annual f={out['f_evaluated']}/9 evaluated")
        return await cache_store(
            "stock_forensic", fp, TTL_SECONDS["financeinfo"], out, source="computed-local",
            warnings=warnings or None, availability="available" if complete else "partial",
            data_time=out["data_time"],
        )

    @server.tool(annotations=READ_ONLY)
    async def valuation_run(symbol: str, btype: int = 1, method: str = "auto") -> dict[str, Any]:
        """Ensemble PER/PB. Dùng khi cần vùng giá trị hợp lý của 1 mã.

        Dùng khi: "FPT đáng giá bao nhiêu", vùng mua an toàn.
        Không dùng khi: chỉ cần bội số hiện tại (dùng stock_overview — nhẹ hơn); cần đọc BCTC
            chi tiết (dùng financial_detail). Không có tool nào tên valuation_band — dùng output
            vùng per_pb/pb của tool này. DCF/EV CHƯA có.

        btype→method (method LUÔN có giá trị, không bao giờ null):
        1 thường → per_pb · 2 chứng khoán → pb_bank_broker · 3 ngân hàng → pb_bank_broker
        5 bảo hiểm → per_pb. btype lạ → cảnh báo + method auto.
        method: 'auto' (mặc định, chọn theo btype) hoặc ép 'per'/'pb'/'ensemble'.
        """
        # v5: expose observation and measurement limits alongside raw values.
        fp = f"v5|{symbol}|{btype}|{method}"
        hit = await cache_lookup("valuation_run", fp)
        if hit is not None:
            return hit
        try:
            overview = await _call("v", vs_p.overview_trading, symbol, secs=45.0)
            quotes = await _call("q", vn_p.equity_quote_batch, [symbol.upper()], secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("valuation_run", str(exc))
        info = overview if isinstance(overview, dict) else {}
        price = None
        try:
            quote = quotes[0]
            price = _finite_metric(quote.get("close_price") or quote.get("close"))
            if price is not None and price <= 0:
                price = None
        except (IndexError, AttributeError, TypeError):
            price = None
        # Một số 0 nguồn trả là giá trị (#28), nên chỉ coi None là thiếu (#44 mục 5).
        raw_eps = info.get("EPS") if info.get("EPS") is not None else info.get("eps")
        raw_bvps = info.get("BVPS") if info.get("BVPS") is not None else info.get("bvps")
        eps = _finite_metric(raw_eps)
        bvps = _finite_metric(raw_bvps)
        out: dict[str, Any] = {
            "symbol": symbol.upper(), "price": price, "method": "per_pb",
            "price_source": "vnstock.equity_quote_batch",
            "price_as_of": None,  # recorded batch-quote fixture has no observation timestamp
            "price_unit": "unverified",
            "price_adjustment_basis": "unverified",
            "eps_period": None,
            "eps_frequency": None,
            "eps_basis": "unverified",
            "eps_unit": "unverified",
            "eps_adjustment_basis": "unverified",
            "multiple_comparability": "price/EPS units and adjustment bases unverified",
        }
        if eps is not None:
            out["eps_source"] = "vietstock.overview_trading"
        if bvps is not None:
            out["bvps_source"] = "vietstock.overview_trading"
        warnings: list[str] = []
        if raw_eps is not None and eps is None:
            warnings.append("EPS invalid in Vietstock overview")
        if raw_bvps is not None and bvps is None:
            warnings.append("BVPS invalid in Vietstock overview")
        if price and (eps is None or bvps is None):
            # The trading overview carries no EPS/BVPS: take the trailing EPS and BVPS
            # vnstock reports for its newest period. Not price / PE: that PE is priced at
            # the period end, so it would give a wrong EPS for today's price.
            try:
                fund = await _call("f", vn_p.equity_fundamentals, symbol.upper(), secs=45.0)
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                fund = None
                warnings.append(f"vnstock fundamentals unavailable: {exc}")
            if isinstance(fund, dict):
                label = fund.get("period_label")
                if eps is None and fund.get("eps") is not None:
                    eps = _finite_metric(fund["eps"])
                    if eps is None:
                        warnings.append("EPS invalid in vnstock fundamentals")
                    else:
                        basis = fund.get("eps_basis") or "unverified"
                        suffix = f", period {label}" if label else ""
                        name = "trailing EPS" if basis == "trailing_four_quarters" else "EPS"
                        out["eps_source"] = f"vnstock {name}{suffix}"
                        out["eps_period"] = label
                        out["eps_frequency"] = fund.get("frequency") or "unverified"
                        out["eps_basis"] = basis
                if bvps is None and fund.get("bvps") is not None:
                    bvps = _finite_metric(fund["bvps"])
                    if bvps is None:
                        warnings.append("BVPS invalid in vnstock fundamentals")
                    else:
                        suffix = f", period {label}" if label else ""
                        out["bvps_source"] = f"vnstock BVPS{suffix}"
                        out["bvps_period"] = label
                        out["bvps_frequency"] = fund.get("frequency") or "unverified"
                if fund.get("discarded_period_labels"):
                    out["discarded_period_labels"] = fund["discarded_period_labels"]
        if eps is not None:
            out["eps"] = eps
        if bvps is not None:
            out["bvps"] = bvps
        try:
            # PER/PB chỉ có nghĩa khi EPS/BVPS dương: 0 hay âm vẫn được hiển thị ở trên
            if price and eps is not None and eps > 0:
                per = _finite_metric(price / eps)
                if per is not None:
                    out["per"] = round(per, 2)
                    out["per_basis"] = "quote_price_over_reported_eps"
            if price and bvps is not None and bvps > 0:
                pb = _finite_metric(price / bvps)
                if pb is not None:
                    out["pb"] = round(pb, 2)
                    out["pb_basis"] = "quote_price_over_reported_bvps"
            if method != "auto":
                out["method"] = method
            elif btype in (2, 3):
                out["method"] = "pb_bank_broker"
            else:
                if btype not in (1, 5):
                    warnings.append(
                        f"unknown btype {btype!r} (valid: 1/2/3/5) — method auto"
                    )
                out["method"] = "per_pb"
        except (TypeError, ValueError):
            pass
        missing = "per" not in out and "pb" not in out
        if missing:
            for label, value in (("EPS", eps), ("BVPS", bvps)):
                if value is None:
                    reason = "missing from both sources"
                else:
                    try:
                        if float(value) <= 0:
                            reason = "nonpositive"
                        elif price is None:
                            reason = "price unavailable or invalid"
                        else:
                            reason = "positive but quotient is not finite"
                    except (TypeError, ValueError):
                        reason = "invalid"
                multiple = "PER" if label == "EPS" else "PB"
                warnings.append(f"{label} {reason} — {multiple} not computed")
        return await cache_store(
            "valuation_run",
            fp,
            TTL_SECONDS["overview"],
            out, source="computed-local", warnings=warnings or None,
            availability="partial" if missing else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def financial_statements(
        symbol: str, period: str = "quarter", statement: str = "all", periods_n: int = 15
    ) -> dict[str, Any]:
        """Alias đọc BCTC (tương thích v3). Dùng khi đọc BCTC nhanh gọn, không cần JWT.

        Dùng khi: "báo cáo KQKD 4 quý gần nhất của FPT", đọc statement nhanh.
        Không dùng khi: cần từng dòng chi tiết/forensic (dùng financial_detail — nặng hơn); nguồn
            gốc mirror khi thiếu JWT (dùng vs_financeinfo).

        Bọc vs_financeinfo (không cần JWT). statement: mục BCTC cần đọc
        ('all', 'KQKD' kết quả kinh doanh, 'CDKT' cân đối, 'CSTC' chỉ số); periods_n: số kỳ
        gần nhất. Trả {periods: [kỳ cũ→mới], statements: {tên mục: [{name, unit,
        values: {"Q2/2026": số, ...}}]}} — mỗi số gắn nhãn kỳ của nó; đơn vị theo
        unit của dòng (đồng khi nguồn để trống).
        """
        # v2: values keyed by period (v1 cached the raw pages with reversed Value1..5)
        fp = f"v2|{symbol}|{period}|{statement}|{periods_n}"
        hit = await cache_lookup("financial_statements", fp)
        if hit is not None:
            return hit
        try:
            raw = await _call("f", vs_p.financeinfo, symbol, period, secs=60.0)
            data, warnings = vs_p.align_financeinfo(raw, statement, periods_n)
            return await cache_store(
                "financial_statements", fp, TTL_SECONDS["financeinfo"],
                data, source="vietstock", warnings=warnings or None,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_statements", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def financial_ratios(
        symbol: str,
        set: str = "all",
        period: str = "year",
        peers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Bảng chỉ số tài chính theo kỳ của vnstock. Dùng khi soi chỉ số tài chính của 1 mã qua
            các năm/quý (kèm peers tuỳ chọn).

        Dùng khi: "ROE các năm của VCB", so chỉ số 1 mã với vài peers, P/E các năm trước.
        Không dùng khi: cần P/E, P/B HIỆN TẠI (bảng này là bội số tại ngày kết thúc từng kỳ —
            dùng stock_overview hoặc valuation_run); so dạng bảng head-to-head nhiều mã (dùng
            peer_compare — gọn hơn); cần vùng giá trị (dùng valuation_run).

        period: 'year' (mặc định) hoặc 'quarter'. set: chỉ giữ chỉ số có item_id hoặc tên chứa
        chuỗi này ('all' giữ hết; ví dụ 'roe', 'p_e', 'margin'). Trả periods (mới→cũ) và
        ratios [{item_id, item, values: {kỳ: số}}]: tỷ suất/tăng trưởng tính bằng % (roe 28.3 =
        28,3%), EPS/BVPS bằng đồng, P/E, P/B là bội số tại cuối kỳ (dòng có as_of
        "period_end", kèm note). peers: thêm chỉ số kỳ mới nhất của từng mã.
        metric_quality trên peer giữ cờ nghi vấn và ghi chú nguồn theo từng item_id.
        """
        # v7: disclose rejected period columns and known ratio bases.
        fp = f"v7|{symbol}|{set}|{period}|{peers}"
        hit = await cache_lookup("financial_ratios", fp)
        if hit is not None:
            return hit
        want = set.strip().lower()

        def _keep(row: dict[str, Any]) -> bool:
            if want in ("", "all"):
                return True
            return want in row["item_id"].lower() or want in row["item"].lower()

        try:
            table = await _call("r", vn_p.equity_ratios, symbol, period, secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_ratios", str(exc))
        kept = [r for r in table["ratios"] if _keep(r)]
        out: dict[str, Any] = {"symbol": symbol.upper(), "period": period}
        if any(r["item_id"].lower() in _PERIOD_END_PRICE_ITEMS for r in kept):
            out["note"] = _PERIOD_END_NOTE  # first in the payload, before the numbers
        out["periods"] = table["periods"]
        out["frequency"] = table.get("frequency", "annual" if period == "year" else "quarterly")
        out["period_basis"] = table.get("period_basis", "reported_period_label")
        out["discarded_period_labels"] = table.get("discarded_period_labels", [])
        out["ratios"] = [_label_period_end(r) for r in kept]
        warnings: list[str] = []
        if peers:
            out["peers"] = []
            for peer in peers:
                try:
                    peer_table = await _call("r", vn_p.equity_ratios, peer, period, secs=45.0)
                except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                    out["peers"].append({"symbol": peer.upper(), "error": str(exc)})
                    warnings.append(f"{peer.upper()}: {exc}")
                    continue
                newest = peer_table["periods"][0]
                peer_row: dict[str, Any] = {
                    "symbol": peer.upper(),
                    "period_label": newest,
                    "values": {
                        r["item_id"]: r["values"].get(newest)
                        for r in peer_table["ratios"]
                        if _keep(r)
                    },
                }
                quality = _ratio_quality([r for r in peer_table["ratios"] if _keep(r)])
                if quality:
                    peer_row["metric_quality"] = quality
                bases = {
                    r["item_id"]: r["basis"] for r in peer_table["ratios"]
                    if _keep(r) and "basis" in r
                }
                if bases:
                    peer_row["metric_basis"] = bases
                peer_row["frequency"] = peer_table.get("frequency", out["frequency"])
                peer_row["discarded_period_labels"] = peer_table.get("discarded_period_labels", [])
                if any(k.lower() in _PERIOD_END_PRICE_ITEMS for k in peer_row["values"]):
                    peer_row["valuation_as_of"] = f"cuối kỳ {newest} (không phải hiện tại)"
                out["peers"].append(peer_row)
        return await cache_store(
            "financial_ratios", fp, TTL_SECONDS["overview"],
            out, source="vnstock", warnings=warnings or None,
            availability="partial" if warnings else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def peer_compare(
        symbol: str, peers: list[str], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """So sánh head-to-head chỉ số tài chính giữa các mã. Dùng khi chọn giữa vài ticker cùng
            ngành.

        Dùng khi: "so VCB với TCB với MBB", bảng so sánh trực diện.
        Không dùng khi: cần P/E, P/B HIỆN TẠI (pe/pb ở đây là bội số tại ngày kết thúc năm báo
            cáo — dùng stock_overview cho từng mã); sàng cả thị trường theo điều kiện (dùng
            stock_screener); cần chuỗi thời gian của 1 mã (dùng financial_ratios period).

        peers: tối đa 5 mã khác. metrics: chỉ giữ các item_id nêu tên (pe, pb, roe, roa, eps,
        bvps là tên tắt của p_e, p_b, roe, roa, trailing_eps, book_value_per_share_bvps).
        Mỗi dòng là chỉ số năm báo cáo mới nhất của mã (period_label): % cho tỷ suất, đồng cho
        EPS/BVPS, bội số cuối kỳ cho P/E, P/B (dòng có valuation_as_of, kèm note).
        metric_quality giữ cờ nghi vấn và ghi chú nguồn theo từng item_id được chọn.
        Ví dụ: {"symbol": "VCB", "peers": ["TCB", "MBB"], "metrics": ["pe", "roe"]}.
        """
        # v7: retain reported frequency, metric basis and rejected period labels.
        fp = f"v7|{symbol}|{peers}|{metrics}"
        hit = await cache_lookup("peer_compare", fp)
        if hit is not None:
            return hit
        wanted = (
            {_PEER_METRIC_ALIASES.get(m.strip().lower(), m.strip().lower()) for m in metrics}
            if metrics
            else None
        )
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen_ids: set[str] = set()
        for name in [symbol, *peers][:6]:
            try:
                table = await _call("p", vn_p.equity_ratios, name, "year", secs=45.0)
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                rows.append({"symbol": name.upper(), "error": str(exc)})
                warnings.append(f"{name.upper()}: {exc}")
                continue
            newest = table["periods"][0]
            row: dict[str, Any] = {"symbol": name.upper(), "period_label": newest}
            seen_ids.update(r["item_id"].lower() for r in table["ratios"])
            for ratio in table["ratios"]:
                if wanted is None or ratio["item_id"].lower() in wanted:
                    row[ratio["item_id"]] = ratio["values"].get(newest)
            quality = _ratio_quality([
                r for r in table["ratios"]
                if wanted is None or r["item_id"].lower() in wanted
            ])
            if quality:
                row["metric_quality"] = quality
            bases = {
                r["item_id"]: r["basis"] for r in table["ratios"]
                if (wanted is None or r["item_id"].lower() in wanted) and "basis" in r
            }
            if bases:
                row["metric_basis"] = bases
            row["frequency"] = table.get("frequency", "annual")
            row["discarded_period_labels"] = table.get("discarded_period_labels", [])
            if any(key.lower() in _PERIOD_END_PRICE_ITEMS for key in row):
                row["valuation_as_of"] = f"cuối kỳ {newest} (không phải hiện tại)"
            rows.append(row)
        if wanted is not None and seen_ids:
            for metric in sorted(wanted - seen_ids):
                warnings.append(f"metric {metric!r} is not in the vnstock ratio table")
        result: dict[str, Any] = {"rows": rows}
        if any("valuation_as_of" in r for r in rows):
            result = {"note": _PERIOD_END_NOTE, "rows": rows}
        return await cache_store(
            "peer_compare", fp, TTL_SECONDS["overview"],
            result, source="vnstock", warnings=warnings or None,
            availability="partial" if warnings else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def stock_overview(symbol: str) -> dict[str, Any]:
        """Thông tin giao dịch + hồ sơ công ty gộp một lần. Dùng khi cần dossier nhanh về 1 mã.

        Dùng khi: lần đầu xem 1 mã (giá + công ty làm gì).
        Không dùng khi: cần cổ đông/lãnh đạo chi tiết (dùng vn_company detail=true); chỉ cần giá
            (dùng vn_equity_quote_batch).

        Ví dụ: {"symbol": "FPT"}.
        """
        fp = f"{symbol}"
        hit = await cache_lookup("stock_overview", fp)
        if hit is not None:
            return hit
        try:
            trading = await _call(
                "t", vs_p._post, "/company/tradinginfo", {"code": symbol.upper(), "s": 0}
            )
            company = await _call("c", vs_p.company_info, symbol)
            return await cache_store(
                "stock_overview", fp, price_ttl(),  # embeds a live trading snapshot
                {"trading": trading, "company": company}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_overview", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def company_events(symbol: str, types: str | None = None) -> dict[str, Any]:
        """Classified disclosures and corporate actions. Use for event calendars.

        types: comma-separated kinds to keep, matched against kind/type
        fields (e.g. 'bctc,nghi_quyet'). corporate_calendar is the raw
        unfiltered feed; company_events classifies it per symbol.
        """
        fp = f"{symbol}|{types}"
        hit = await cache_lookup("company_events", fp)
        if hit is not None:
            return hit
        try:
            docs = await _call("e", vs_p.documents, symbol)
            if types is not None and isinstance(docs, list):
                wanted = {t.strip().lower() for t in types.split(",") if t.strip()}
                docs = [
                    d
                    for d in docs
                    if isinstance(d, dict)
                    and wanted.intersection(
                        {str(d.get("kind", "")).lower(), str(d.get("type", "")).lower()}
                    )
                ]
            return await cache_store(
                "company_events", fp, TTL_SECONDS["hour"],
                {"symbol": symbol.upper(), "events": docs}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("company_events", str(exc))

    return [
        {"name": "stock_forensic"},
        {"name": "valuation_run"},
        {"name": "financial_statements"},
        {"name": "financial_ratios"},
        {"name": "peer_compare"},
        {"name": "stock_overview"},
        {"name": "company_events"},
    ]
