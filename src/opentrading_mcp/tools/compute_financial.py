"""Compute financial tools: forensic, valuation, statements, ratios, peers."""

from __future__ import annotations

import functools
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


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


def _fd_series(detail: dict[str, Any], include: str, exclude: str = "") -> list[float]:
    """Sum values of detail rows whose name matches include (and no exclude)."""
    if not isinstance(detail, dict):
        return []
    series: list[float] | None = None
    for row in detail.get("rows") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        if include not in name or (exclude and exclude in name):
            continue
        values = [
            float(v) if isinstance(v, (int, float)) else 0.0 for v in (row.get("values") or [])
        ]
        if not any(values):
            continue
        if series is None:
            series = values
        else:
            series = [a + b for a, b in zip(series, values, strict=False)]
    return series or []


def _fd_pick(detail: dict[str, Any], *priority: tuple[str, str]) -> list[float]:
    """First matching (include, exclude) pair that yields a series."""
    for include, exclude in priority:
        got = _fd_series(detail, include, exclude)
        if got:
            return got
    return []


def _fd_first(detail: dict[str, Any], *needles: str) -> list[float]:
    for needle in needles:
        got = _fd_series(detail, needle)
        if got:
            return got
    return []


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
        tiền, CFO). M-Score 7 chỉ số (thiếu DEPI — nguồn không có); chỉ đủ
        công thức khi đủ input, thiếu thì trả partial kèm danh sách thiếu.
        F-Score: 6/9 mục trên gói Standard (CFO từ LCTT trống phía nguồn;
        mục số cổ phiếu không có); 8/9 khi BCTC trả phí mở LCTT.
        detail=true thêm chuỗi input thô.
        """
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
        rev = _fd_pick(
            kq,
            ("doanh thu thuần về bán hàng", ""),
            ("thu nhập lãi thuần", ""),
            ("doanh thu thuần", ""),
        )
        gross = _fd_pick(kq, ("lợi nhuận gộp", ""), ("lợi nhuận gộp về bán hàng", ""))
        ni = _fd_pick(kq, ("sau thuế", "mẹ"), ("sau thuế", "cổ đông"))
        recv = _fd_pick(cd, ("phải thu ngắn hạn", "dự phòng"), ("phải thu", "dự phòng"))
        recv = recv or _fd_pick(cd, ("phải thu", ""))
        assets = _fd_first(cd, "tổng cộng tài sản", "tổng tài sản")
        cash = _fd_first(cd, "tiền và tương đương", "tiền ")
        curr_assets = _fd_first(cd, "tài sản ngắn hạn")
        curr_liab = _fd_first(cd, "nợ ngắn hạn")
        debt = _fd_first(cd, "nợ phải trả")
        equity = _fd_first(cd, "vốn chủ sở hữu")
        cfo = _fd_pick(lc, ("thuần từ hoạt động kinh doanh", ""), ("kinh doanh", "đầu tư"))
        selling = _fd_first(kq, "chi phí bán hàng")
        admin = _fd_first(kq, "chi phí quản lý")
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
        cash = cash or []
        cash_t, cash_p = _g(cash, 0) or 0.0, _g(cash, 1) or 0.0
        ca_t, ca_p = _g(curr_assets, 0), _g(curr_assets, 1)
        cl_t, cl_p = _g(curr_liab, 0), _g(curr_liab, 1)
        aqi_num_t = 1 - (_safe_div((ca_t or 0) - (cl_t or 0) - cash_t, assets_t) or 0)
        aqi_num_p = 1 - (_safe_div((ca_p or 0) - (cl_p or 0) - cash_p, assets_p) or 0)
        aqi = _safe_div(aqi_num_t, aqi_num_p) if assets_t and assets_p else None
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
        tata = (
            _safe_div((ni_t or 0) - (cfo_t or 0), assets_t)
            if ni_t is not None and assets_t
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
        raw_parts = [
            (0.92, dsri),
            (0.528, gmi),
            (0.404, aqi),
            (0.892, sgi),
            (0.115, sgai),
            (4.679, tata),
            (-0.327, lvgi),
        ]
        parts = [c * v for c, v in raw_parts if v is not None]
        m_score = round(-4.84 + sum(parts), 4) if not missing else None
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
        return make_envelope(out, source="computed-local")

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
        return make_envelope(out, source="computed-local", warnings=warnings or None)

    @server.tool(annotations=READ_ONLY)
    async def financial_statements(
        symbol: str, period: str = "quarter", statement: str = "all", periods_n: int = 15
    ) -> dict[str, Any]:
        """Alias đọc BCTC (tương thích v3). Dùng khi đọc BCTC nhanh gọn, không cần JWT.

        Dùng khi: "báo cáo KQKD 4 quý gần nhất của FPT", đọc statement nhanh.
        Không dùng khi: cần từng dòng chi tiết/forensic (dùng financial_detail — nặng hơn); nguồn
            gốc mirror khi thiếu JWT (dùng vs_financeinfo).

        Bọc vs_financeinfo (không cần JWT). statement: mục BCTC cần đọc
        ('all', hoặc khóa như 'KQKD'/'CDKT'); periods_n giới hạn số kỳ trả về.
        """
        try:
            data = await _call("f", vs_p.financeinfo, symbol, period, secs=60.0)
            pages = data.get("pages", []) if isinstance(data, dict) else []
            if statement != "all" and isinstance(pages, list):
                matched = [
                    p
                    for p in pages
                    if isinstance(p, dict) and any(statement.lower() in str(k).lower() for k in p)
                ]
                if matched:
                    flat: list[Any] = []
                    for page in matched:
                        for values in page.values():
                            flat.extend(values if isinstance(values, list) else [values])
                    return make_envelope(
                        {"symbol": symbol.upper(), "periods": flat[: max(int(periods_n), 1)]},
                        source="vietstock",
                    )
                return make_envelope(
                    {"symbol": symbol.upper(), "periods": pages},
                    source="vietstock",
                    warnings=[f"statement {statement!r} not found, returning all pages"],
                )
            return make_envelope(data, source="vietstock")
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
                    return make_envelope(out_fb, source="vnstock")
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
            return make_envelope(out, source="vietstock")
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
        return make_envelope({"rows": rows}, source="vietstock")

    @server.tool(annotations=READ_ONLY)
    async def stock_overview(symbol: str) -> dict[str, Any]:
        """Thông tin giao dịch + hồ sơ công ty gộp một lần. Dùng khi cần dossier nhanh về 1 mã.

        Dùng khi: lần đầu xem 1 mã (giá + công ty làm gì).
        Không dùng khi: cần cổ đông/lãnh đạo chi tiết (dùng vn_company detail=true); chỉ cần giá
            (dùng vn_equity_quote_batch).

        Ví dụ: {"symbol": "FPT"}.
        """
        try:
            trading = await _call(
                "t", vs_p._post, "/company/tradinginfo", {"code": symbol.upper(), "s": 0}
            )
            company = await _call("c", vs_p.company_info, symbol)
            return make_envelope({"trading": trading, "company": company}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_overview", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def company_events(symbol: str, types: str | None = None) -> dict[str, Any]:
        """Classified disclosures and corporate actions. Use for event calendars.

        types: comma-separated kinds to keep, matched against kind/type
        fields (e.g. 'bctc,nghi_quyet'). corporate_calendar is the raw
        unfiltered feed; company_events classifies it per symbol.
        """
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
            return make_envelope({"symbol": symbol.upper(), "events": docs}, source="vietstock")
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
