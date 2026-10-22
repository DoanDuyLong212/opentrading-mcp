"""Compute financial tools: forensic, valuation, statements, ratios, peers."""

from __future__ import annotations

import functools
import json
import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
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


# Statement lines used by stock_forensic: Vietstock norm ids of the general (FPT) and
# bank (VCB) templates, checked live 2026-10-23, then exact line names for other templates.
_FD_LINES: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "revenue": (
        (2216, 4385),
        ("doanh thu thuần về bán hàng và cung cấp dịch vụ", "doanh thu thuần",
         "thu nhập lãi thuần"),
    ),
    "gross": ((2217,), ("lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "lợi nhuận gộp")),
    "net_income": (
        (2212, 4378),
        ("lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế"),
    ),
    "selling": ((2227,), ("chi phí bán hàng",)),
    "admin": ((2224,), ("chi phí quản lý doanh nghiệp", "chi phí quản lý")),
    "receivables": ((3005,), ("các khoản phải thu ngắn hạn",)),
    "assets": ((2996, 4375), ("tổng cộng tài sản",)),
    "cash": ((3003,), ("tiền và các khoản tương đương tiền", "tiền và tương đương tiền")),
    "current_assets": ((3000,), ("tài sản ngắn hạn",)),
    "current_liabilities": ((3014,), ("nợ ngắn hạn",)),
    "liabilities": ((2997, 4304), ("nợ phải trả", "tổng nợ phải trả")),
    "equity": ((2998, 4325), ("vốn chủ sở hữu", "vốn và các quỹ")),
    "cfo": ((2234,), ("lưu chuyển tiền thuần từ hoạt động kinh doanh",)),
}


def _fd_line(detail: dict[str, Any], line: str) -> list[float | None]:
    norm_ids, names = _FD_LINES[line]
    return _fd_row(detail, norm_ids, names)


# Beneish (1999) 8-variable model without DEPI (depreciation is not exposed upstream).
# SGAI enters with a negative weight; -1.78 is the 8-variable cut-off, so with DEPI
# dropped the threshold is approximate.
BENEISH_INTERCEPT = -4.84
BENEISH_COEF = {
    "dsri": 0.920,
    "gmi": 0.528,
    "aqi": 0.404,
    "sgi": 0.892,
    "sgai": -0.172,
    "tata": 4.679,
    "lvgi": -0.327,
}


def register_compute_financial_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_forensic(
        symbol: str,
        detail: bool = False,
        periods_n: int = 4,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Điểm gian lận Beneish M-Score + chất lượng lợi nhuận Piotroski F-Score từ BCTC chi tiết
            đầy đủ. Dùng khi kiểm tra chất lượng lợi nhuận trước khi định giá.

        Dùng khi: "lợi nhuận FPT có ảo không", chấm điểm trước BCTC.
        Không dùng khi: chỉ cần đọc BCTC (dùng financial_detail); chỉ cần bội số nhanh (dùng
            vn_fundamentals).

        Nguồn: chi tiết KQKD/CDKT/LCTT (dòng thật theo quý: phải thu,
        tiền, CFO). M-Score 7 chỉ số (thiếu DEPI — nguồn không có, nên
        ngưỡng -1.78 chỉ là gần đúng); chỉ đủ công thức khi đủ input,
        thiếu thì trả partial kèm danh sách thiếu.
        F-Score: 6/9 mục trên gói Standard (CFO từ LCTT trống phía nguồn;
        mục số cổ phiếu không có); 8/9 khi BCTC trả phí mở LCTT.
        detail=true thêm chuỗi input thô.
        """
        fp = f"v2|{symbol}|{detail}|{periods_n}"  # v2: single-line inputs, no CFO-as-0
        hit = await cache_lookup("stock_forensic", fp)
        if hit is not None:
            return hit
        sym = symbol.strip().upper()
        try:
            kq = await _call(
                "fk", vs_p.financial_detail, sym, "KQKD", max(int(periods_n), 2), secs=60.0
            )
            cd = await _call(
                "fc", vs_p.financial_detail, sym, "CDKT", max(int(periods_n), 2), secs=60.0
            )
            # LCTT detail is empty upstream on Standard pack (norms {} + values 0) —
            # CFO items are only counted when BCTC paid unlocks LCTT later.
            try:
                lc = await _call(
                    "fl", vs_p.financial_detail, sym, "LCTT", max(int(periods_n), 2), secs=60.0
                )
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
                lc = {}
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_forensic", str(exc))
        rev = _fd_line(kq, "revenue")
        gross = _fd_line(kq, "gross")
        ni = _fd_line(kq, "net_income")
        recv = _fd_line(cd, "receivables")
        assets = _fd_line(cd, "assets")
        cash = _fd_line(cd, "cash")
        curr_assets = _fd_line(cd, "current_assets")
        curr_liab = _fd_line(cd, "current_liabilities")
        debt = _fd_line(cd, "liabilities")
        equity = _fd_line(cd, "equity")
        cfo = _fd_line(lc, "cfo")
        selling = _fd_line(kq, "selling")
        admin = _fd_line(kq, "admin")
        if len(rev) < 2 or not assets:
            return make_envelope(
                {"symbol": sym, "note": "insufficient detail fields", "missing": True},
                source="vietstock",
                availability="empty",
            )

        def _g(seq: list[float], back: int) -> float | None:
            """Value back positions from newest end; None when absent/empty."""
            if not seq or len(seq) <= back:
                return None
            return seq[len(seq) - 1 - back]

        def _safe_div(num: Any, den: Any) -> float | None:
            if num is None or den is None or den == 0:
                return None
            return float(num) / float(den)

        rev_t, rev_p = _g(rev, 0), _g(rev, 1)
        recv_t, recv_p = _g(recv, 0), _g(recv, 1)
        assets_t, assets_p = _g(assets, 0), _g(assets, 1)
        dsri = _safe_div(_safe_div(recv_t, rev_t), _safe_div(recv_p, rev_p))
        gross_t, gross_p = _g(gross, 0), _g(gross, 1)
        ni_t, ni_p = _g(ni, 0), _g(ni, 1)
        if gross_t is None and ni_t is not None:
            gross_t = rev_t - ni_t if rev_t is not None else None
        if gross_p is None and ni_p is not None:
            gross_p = rev_p - ni_p if rev_p is not None else None
        gmi = _safe_div(
            _safe_div(gross_p, rev_p) or _safe_div((rev_p or 0) - (ni_p or 0), rev_p),
            _safe_div(gross_t, rev_t) or _safe_div((rev_t or 0) - (ni_t or 0), rev_t),
        )
        cash_t, cash_p = _g(cash, 0) or 0.0, _g(cash, 1) or 0.0
        ca_t, ca_p = _g(curr_assets, 0), _g(curr_assets, 1)
        cl_t, cl_p = _g(curr_liab, 0), _g(curr_liab, 1)
        aqi = None
        # No current assets/liabilities line (bank template): AQI is not computable,
        # not 1.0 from zeros.
        if None not in (ca_t, ca_p, cl_t, cl_p) and assets_t and assets_p:
            aqi_num_t = 1 - (_safe_div(ca_t - cl_t - cash_t, assets_t) or 0)
            aqi_num_p = 1 - (_safe_div(ca_p - cl_p - cash_p, assets_p) or 0)
            aqi = _safe_div(aqi_num_t, aqi_num_p)
        sgi = _safe_div(rev_t, rev_p)
        selling_t, selling_p = _g(selling, 0), _g(selling, 1)
        admin_t, admin_p = _g(admin, 0), _g(admin, 1)
        sgai = _safe_div(
            _safe_div((selling_t or 0) + (admin_t or 0), rev_t),
            _safe_div((selling_p or 0) + (admin_p or 0), rev_p),
        )
        debt_t, debt_p = _g(debt, 0), _g(debt, 1)
        eq_t, eq_p = _g(equity, 0), _g(equity, 1)
        lvgi = _safe_div(_safe_div(debt_t, eq_t), _safe_div(debt_p, eq_p))
        cfo_t = _g(cfo, 0)
        # TATA needs CFO: without the cash-flow line it stays missing (the M-Score is
        # then partial), instead of NI/TA as if CFO were 0.
        tata = (
            _safe_div(ni_t - cfo_t, assets_t)
            if ni_t is not None and cfo_t is not None and assets_t
            else None
        )
        missing = [
            k
            for k, v in (
                ("dsri", dsri),
                ("gmi", gmi),
                ("aqi", aqi),
                ("sgai", sgai),
                ("lvgi", lvgi),
                ("tata", tata),
            )
            if v is None
        ]
        indexes = {
            "dsri": dsri,
            "gmi": gmi,
            "aqi": aqi,
            "sgi": sgi,
            "sgai": sgai,
            "tata": tata,
            "lvgi": lvgi,
        }
        parts = [BENEISH_COEF[k] * v for k, v in indexes.items() if v is not None]
        m_score = round(BENEISH_INTERCEPT + sum(parts), 4) if not missing else None
        flags: list[str] = []
        if dsri and dsri > 1.2:
            flags.append("receivables growing faster than sales (DSRI>1.2)")
        if sgi and sgi > 1.3:
            flags.append("unusually fast sales growth (SGI>1.3)")
        if m_score is not None and m_score > -1.78:
            flags.append(f"M-Score {m_score} above -1.78 (manipulation evidence)")
        # Piotroski: 6 items always computable here; +2 CFO items when LCTT exists.
        items: list[tuple[str, bool | None]] = []
        if ni_t is not None and assets_t:
            roa_t, roa_p = _safe_div(ni_t, assets_t), _safe_div(ni_p, assets_p)
            items.append(("ROA>0", roa_t is not None and roa_t > 0))
            items.append(("dROA>0", roa_t is not None and roa_p is not None and roa_t > roa_p))
            lev_t, lev_p = _safe_div(debt_t, eq_t), _safe_div(debt_p, eq_p)
            items.append(
                ("leverage down", lev_t is not None and lev_p is not None and lev_t < lev_p)
            )
            cr_t, cr_p = _safe_div(ca_t, cl_t), _safe_div(ca_p, cl_p)
            items.append(
                ("current ratio up", cr_t is not None and cr_p is not None and cr_t > cr_p)
            )
            gm_t, gm_p = _safe_div(gross_t, rev_t), _safe_div(gross_p, rev_p)
            items.append(("gross margin up", gm_t is not None and gm_p is not None and gm_t > gm_p))
            to_t, to_p = _safe_div(rev_t, assets_t), _safe_div(rev_p, assets_p)
            items.append(("turnover up", to_t is not None and to_p is not None and to_t > to_p))
            if cfo_t is not None:
                items.append(("CFO>0", cfo_t > 0))
                items.append(("CFO>NI", ni_t is not None and cfo_t > ni_t))
        counted = sum(1 for _, ok in items if ok is True)
        out: dict[str, Any] = {
            "symbol": sym,
            "dsri": round(dsri, 4) if dsri else None,
            "gmi": round(gmi, 4) if gmi else None,
            "aqi": round(aqi, 4) if aqi else None,
            "sgi": round(sgi, 4) if sgi else None,
            "sgai": round(sgai, 4) if sgai else None,
            "lvgi": round(lvgi, 4) if lvgi else None,
            "tata": round(tata, 4) if tata is not None else None,
            "m_score": m_score,
            "m_partial": missing or None,
            "f_score": f"{counted}/{len(items)}",
            "flags": flags,
        }
        if detail:
            out["series"] = {
                "revenue": rev,
                "gross": gross,
                "net_income": ni,
                "receivables": recv,
                "assets": assets,
                "cash": cash,
                "cfo": cfo,
            }
        if ctx is not None:
            await ctx.log("info", f"stock_forensic {sym} f={counted}")
        return await cache_store(
            "stock_forensic", fp, TTL_SECONDS["financeinfo"],
            out, source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def valuation_run(symbol: str, btype: int = 1, method: str = "auto") -> dict[str, Any]:
        """Ensemble PER/PB. Dùng khi cần vùng giá trị hợp lý của 1 mã.

        Dùng khi: "FPT đáng giá bao nhiêu", vùng mua an toàn.
        Không dùng khi: chỉ cần bội số hiện tại (dùng vs_overview_trading — nhẹ hơn); cần đọc BCTC
            chi tiết (dùng financial_detail). Không có tool nào tên valuation_band — dùng output
            vùng per_pb/pb của tool này. DCF/EV CHƯA có.

        btype→method (method LUÔN có giá trị, không bao giờ null):
        1 thường → per_pb · 2 chứng khoán → pb_bank_broker · 3 ngân hàng → pb_bank_broker
        5 bảo hiểm → per_pb. btype lạ → cảnh báo + method auto.
        method: 'auto' (mặc định, chọn theo btype) hoặc ép 'per'/'pb'/'ensemble'.
        """
        fp = f"{symbol}|{btype}|{method}"
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
            price = float(quotes[0].get("close_price") or quotes[0].get("close") or 0) or None
        except (IndexError, TypeError, ValueError):
            price = None
        eps = info.get("EPS") or info.get("eps")
        bvps = info.get("BVPS") or info.get("bvps")
        out: dict[str, Any] = {"symbol": symbol.upper(), "price": price, "method": "per_pb"}
        warnings: list[str] = []
        if not eps and price:
            # overview lacks EPS — derive from vnstock PE (price/pe), best-effort
            try:
                fund = await _call("f", vn_p.equity_fundamentals, symbol.upper(), secs=45.0)
                pe = (fund or {}).get("pe") if isinstance(fund, dict) else None
                if pe and float(pe) > 0:
                    eps = round(price / float(pe), 0)
                    warnings.append("EPS derived from vnstock PE (overview lacks EPS)")
            except Exception:
                pass
        try:
            if price and eps and float(eps) > 0:
                out["per"] = round(price / float(eps), 2)
            if price and bvps and float(bvps) > 0:
                out["pb"] = round(price / float(bvps), 2)
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
        return await cache_store(
            "valuation_run",
            f"{symbol}|{btype}|{method}",
            TTL_SECONDS["overview"],
            out, source="computed-local", warnings=warnings or None,
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
        """Overview gộp ratios của vnstock. Dùng khi lọc/soi chỉ số tài chính của 1 mã (kèm peers
            tuỳ chọn).

        Dùng khi: "ROE các năm của VCB", so chỉ số 1 mã với vài peers.
        Không dùng khi: so dạng bảng head-to-head nhiều mã (dùng peer_compare — gọn hơn); cần bội số
            snapshot (dùng vs_overview_trading); cần vùng giá trị (dùng valuation_run).

        set: chỉ giữ key ratios chứa chuỗi này ('all' giữ hết).
        period: kỳ BCTC ('year'); peers: thêm mã vào danh sách.
        Rơi về vnstock fundamentals khi overview Vietstock trống.
        """
        fp = f"{symbol}|{set}|{period}|{peers}"
        hit = await cache_lookup("financial_ratios", fp)
        if hit is not None:
            return hit
        try:
            overview = await _call("r", vs_p.overview_trading, symbol)
            if not overview:
                try:
                    fb = await _call("r", vn_p.equity_fundamentals, symbol, secs=45.0)
                    out_fb: dict[str, Any] = {
                        "symbol": symbol.upper(),
                        "period": period,
                        "ratios": fb,
                    }
                    return await cache_store(
                        "financial_ratios", fp, TTL_SECONDS["overview"],
                        out_fb, source="vnstock",
                    )
                except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
                    pass
            ratios = overview if isinstance(overview, dict) else {"overview": overview}
            if set != "all":
                ratios = {k: v for k, v in ratios.items() if set.lower() in str(k).lower()}
            out: dict[str, Any] = {"symbol": symbol.upper(), "period": period, "ratios": ratios}
            if peers:
                out["peers"] = []
                for peer in peers:
                    try:
                        peer_data = await _call("r", vs_p.overview_trading, peer)
                    except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                        peer_data = {"symbol": peer.upper(), "error": str(exc)}
                    if isinstance(peer_data, dict) and "symbol" not in peer_data:
                        peer_data = {"symbol": peer.upper(), **peer_data}
                    out["peers"].append(peer_data)
            return await cache_store(
                "financial_ratios", fp, TTL_SECONDS["overview"],
                out, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_ratios", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def peer_compare(
        symbol: str, peers: list[str], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """So sánh head-to-head các dòng overview giữa các mã. Dùng khi chọn giữa vài ticker cùng
            ngành.

        Dùng khi: "so VCB với TCB với MBB", bảng so sánh trực diện.
        Không dùng khi: sàng cả thị trường theo điều kiện (dùng stock_screener); cần chuỗi thời gian
            của 1 mã (dùng financial_ratios period).

        peers: tối đa 5 mã khác. metrics: chỉ giữ key ratios khớp
        (cột symbol luôn giữ).
        Ví dụ: {"symbol": "VCB", "peers": ["TCB", "MBB"], "metrics": ["pe", "roe"]}.
        """
        fp = f"{symbol}|{peers}|{metrics}"
        hit = await cache_lookup("peer_compare", fp)
        if hit is not None:
            return hit
        wanted = {m.lower() for m in metrics} if metrics else None
        rows: list[dict[str, Any]] = []
        for name in [symbol, *peers][:6]:
            try:
                data = await _call("p", vs_p.overview_trading, name)
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                rows.append({"symbol": name.upper(), "error": str(exc)})
                continue
            if wanted is not None and isinstance(data, dict):
                data = {"symbol": name.upper()} | {
                    k: v for k, v in data.items() if str(k).lower() in wanted
                }
            elif isinstance(data, dict) and "symbol" not in data:
                data = {"symbol": name.upper(), **data}
            rows.append(data if isinstance(data, dict) else {"symbol": name.upper(), "data": data})
        return await cache_store(
            "peer_compare", fp, TTL_SECONDS["overview"],
            {"rows": rows}, source="vietstock",
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
