"""Smoke: module vn_reversal dang ky tool thanh cong (khong DB)."""
import importlib


def test_vn_reversal_registers():
    from opentrading_mcp.server import create_server, _REGISTER_BY_MODULE
    assert _REGISTER_BY_MODULE.get("vn_reversal") == "register_vn_reversal_tools"
    mod = importlib.import_module("opentrading_mcp.tools.vn_reversal")
    assert hasattr(mod, "register_vn_reversal_tools")
    s = create_server("all")
    assert s is not None
