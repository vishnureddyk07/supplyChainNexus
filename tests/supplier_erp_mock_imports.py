"""Import adapters for the supplier ERP mock, whose directory uses a hyphen."""

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "supplier-erp-mock"
    / "generator.py"
)
_SPEC = importlib.util.spec_from_file_location("supplier_erp_generator", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"could not load supplier generator at {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
generate_supplier = _MODULE.generate_supplier
