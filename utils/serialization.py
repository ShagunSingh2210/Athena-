"""Generic, recursive "make this JSON-safe" helper for api.py.

Every module in this codebase returns whatever's natural for its own logic —
pandas DataFrames, dataclasses (some nesting other dataclasses or Enums),
numpy scalars. None of that is directly JSON-serializable. Rather than have
each endpoint in api.py hand-roll its own conversion, every endpoint passes
its return value through `to_jsonable()` once, here, in one place.
"""
from __future__ import annotations

import dataclasses
import math
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


def to_jsonable(obj: Any) -> Any:
    """Recursively convert `obj` into plain dict/list/str/int/float/bool/None.

    Args:
        obj: Anything a function in `modules/`, `data_pipelines/`, or `run_demo.py`
            might return or nest: a DataFrame, a `Series`, a dataclass instance
            (including ones with nested dataclasses, Enums, or DataFrame fields),
            a numpy scalar/array, a `pandas.Timestamp`, or an already-plain
            dict/list/tuple/primitive.

    Returns:
        An equivalent structure built only from JSON-safe types. NaN/Infinity
        floats become `None` — raw NaN isn't valid JSON and silently breaks
        strict `JSON.parse` on the frontend even though Python's `json` module
        will emit it uncomplaining by default.
    """
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        value = float(obj)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, pd.DataFrame):
        # Route through to_jsonable again rather than assuming to_dict's output
        # is already JSON-safe — it still carries numpy scalars and NaNs.
        return to_jsonable(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return to_jsonable(obj.to_dict())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Deliberately not `dataclasses.asdict(obj)`: asdict() deep-copies every
        # field (expensive and pointless for a DataFrame field) and leaves
        # non-dataclass values like Enums untouched — exactly the two things
        # this function exists to handle. Walking fields and recursing here
        # gets both right in one pass.
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj
