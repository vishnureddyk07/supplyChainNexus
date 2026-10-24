"""Import adapter for the sensor simulator's hyphenated directory."""

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "sensor-simulator" / "simulator.py"
_SPEC = importlib.util.spec_from_file_location("sensor_simulator_module", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"could not load sensor simulator at {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
generate_sensor_event = _MODULE.generate_sensor_event
