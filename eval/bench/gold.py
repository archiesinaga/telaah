"""Calculation golds computed in Python from checked figures (never taken from the drafter)."""


def fmt_id(x: float, dec: int = 2) -> str:
    """Indonesian number: '.' thousands, ',' decimals; integers without decimals."""
    s = f"{x:,.{dec}f}" if abs(x - round(x)) > 1e-9 else f"{round(x):,}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def compute(figures: list[dict], op: str) -> tuple[float, str]:
    v = [float(f["value_float"]) for f in figures]
    if op == "growth_pct":
        x = (v[1] - v[0]) / abs(v[0]) * 100
    elif op == "difference":
        x = v[1] - v[0]
    elif op == "sum":
        x = sum(v)
    elif op == "ratio_pct":
        x = v[0] / v[1] * 100
    elif op == "ratio":
        x = v[0] / v[1]
    elif op == "mean":
        x = sum(v) / len(v)
    else:
        raise ValueError(f"unknown op {op}")
    pct = op in ("growth_pct", "ratio_pct")
    return x, fmt_id(round(x, 2)) + ("%" if pct else "")
