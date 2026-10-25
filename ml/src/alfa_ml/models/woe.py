"""WoE-биннинг: интервалы фичи и вес доказательства (WoE) каждого интервала.

WoE интервала = ln(доля всех дефолтов, попавших в интервал / доля всех недефолтов): больше — рискованнее.

Числовая фича: пред-биннинг по квантилям, затем соседние интервалы сливаются, пока
- доля дефолтов не станет монотонной в ожидаемую по смыслу сторону (direction: 1 — больше значение, выше риск);
- в каждом интервале не окажется хотя бы min_share выборки;
- интервалов не станет не больше max_bins (сливаются самые близкие по доле дефолтов).
Если данные не подтверждают направление, интервалы сливаются в один и фича получает IV = 0.

Категориальная фича: интервал на категорию; редкие категории сливаются с ближайшей по доле дефолтов.

Пропуск — отдельный интервал, если таких наблюдений не меньше missing_min_share: пропуск обычно что-то
значит («нет кредитной истории»), и такая группа может быть меньше обычного интервала. Совсем редкий
пропуск сливается с самым рискованным интервалом: незнакомое считаем рискованным. Неизвестная категория при скоринге получает WoE пропуска.
Если пропуск значит «нет информации» (neutral_missing), его WoE — 0, а WoE интервалов считается только
по заявкам со значением: фича не повторяет то, из-за чего значения нет (например, молодость бизнеса).
"""
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

SMOOTHING = 0.5  # добавка к числу дефолтов и недефолтов интервала: WoE пустого класса конечен


@dataclass
class Binning:
    name: str
    kind: str  # numeric | categorical
    woe: list[float]
    counts: list[int]
    events: list[int]
    edges: list[float] = field(default_factory=list)  # numeric: интервал i — [edges[i-1], edges[i])
    groups: list[list[str]] = field(default_factory=list)  # categorical: категории интервала i
    missing_woe: float = 0.0
    missing_count: int = 0
    missing_events: int = 0
    iv: float = 0.0

    def bin_index(self, values) -> np.ndarray:
        """Номер интервала; −1 — пропуск или неизвестная категория."""
        if self.kind == "numeric":
            x = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)
            index = np.searchsorted(np.asarray(self.edges, dtype=float), x, side="right")
            return np.where(np.isnan(x), -1, index)
        lookup = {category: i for i, group in enumerate(self.groups) for category in group}
        return np.array([lookup.get(key, -1) for key in category_keys(values)], dtype=int)

    def transform(self, values) -> np.ndarray:
        woe = np.append(np.asarray(self.woe, dtype=float), self.missing_woe)
        return woe[self.bin_index(values)]  # индекс −1 берёт последний элемент — WoE пропуска

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Binning":
        return cls(**data)


def category_keys(values) -> list:
    """Категории строками; 0/1 и True/False — как "0"/"1"; пропуск — None."""
    keys = []
    for value in pd.Series(values, dtype=object):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            keys.append(None)
        elif isinstance(value, (bool, np.bool_, int, np.integer)) or (isinstance(value, float) and value.is_integer()):
            keys.append(str(int(value)))
        else:
            keys.append(str(value))
    return keys


def _woe(events, counts, total_events: int, total_goods: int) -> np.ndarray:
    events = np.asarray(events, dtype=float)
    goods = np.asarray(counts, dtype=float) - events
    return np.log((events + SMOOTHING) / total_events) - np.log((goods + SMOOTHING) / total_goods)


def _merge(bins: list[dict], i: int) -> None:
    """Сливает интервал i со следующим."""
    left, right = bins[i], bins.pop(i + 1)
    left["count"] += right["count"]
    left["events"] += right["events"]
    left["upper"] = right["upper"]
    left["members"] = left["members"] + right["members"]


def _rate(b: dict) -> float:
    return b["events"] / b["count"]


def _merge_small(bins: list[dict], min_count: float) -> None:
    """Сливает самый маленький интервал с соседом, ближайшим по доле дефолтов, пока все не станут не меньше min_count."""
    while len(bins) > 1:
        j = min(range(len(bins)), key=lambda k: bins[k]["count"])
        if bins[j]["count"] >= min_count:
            return
        neighbours = [k for k in (j - 1, j + 1) if 0 <= k < len(bins)]
        k = min(neighbours, key=lambda k: abs(_rate(bins[k]) - _rate(bins[j])))
        _merge(bins, min(j, k))


def _limit(bins: list[dict], max_bins: int) -> None:
    """Сливает соседей с самой близкой долей дефолтов, пока интервалов больше max_bins."""
    while len(bins) > max_bins:
        i = min(range(len(bins) - 1), key=lambda k: abs(_rate(bins[k]) - _rate(bins[k + 1])))
        _merge(bins, i)


def _finish(name: str, kind: str, bins: list[dict], y: np.ndarray, missing: np.ndarray, missing_min_share: float,
            neutral_missing: bool = False, **layout) -> Binning:
    """WoE интервалов и пропуска, IV фичи. counts и events в результате — без пропусков."""
    counts = np.array([b["count"] for b in bins], dtype=float)
    events = np.array([b["events"] for b in bins], dtype=float)
    missing_count, missing_events = int(missing.sum()), int(y[missing].sum())
    own_missing = not neutral_missing and missing_count >= missing_min_share * y.size
    riskiest = int(np.argmax(events / counts))
    woe_counts, woe_events = counts.copy(), events.copy()
    if own_missing:
        woe_counts, woe_events = np.append(counts, missing_count), np.append(events, missing_events)
    elif not neutral_missing:
        # Пропусков мало — они сливаются с самым рискованным интервалом.
        woe_counts[riskiest] += missing_count
        woe_events[riskiest] += missing_events
    total_events, total_goods = woe_events.sum(), (woe_counts - woe_events).sum()
    woe = _woe(woe_events, woe_counts, total_events, total_goods)
    iv = float(np.sum((woe_events / total_events - (woe_counts - woe_events) / total_goods) * woe))
    if neutral_missing:
        missing_woe = 0.0
        iv *= 1 - missing.mean()  # у пропуска вклада нет
    else:
        missing_woe = float(woe[-1] if own_missing else woe[riskiest])
    return Binning(name=name, kind=kind, woe=[round(float(w), 6) for w in woe[:len(bins)]],
                   counts=[int(c) for c in counts], events=[int(e) for e in events],
                   missing_woe=round(missing_woe, 6), missing_count=missing_count, missing_events=missing_events,
                   iv=round(iv, 6), **layout)


def fit_numeric(name: str, values, target, direction: int, min_share: float = 0.05, max_bins: int = 8,
                prebins: int = 20, missing_min_share: float = 0.01, neutral_missing: bool = False) -> Binning:
    x = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)
    y = np.asarray(target, dtype=int)
    missing = np.isnan(x)
    min_count = min_share * y.size
    present, y_present = x[~missing], y[~missing]
    edges = np.unique(np.quantile(present, np.linspace(0, 1, prebins + 1)[1:-1])) if present.size else np.array([])
    index = np.searchsorted(edges, present, side="right")
    counts = np.bincount(index, minlength=edges.size + 1)
    events = np.bincount(index, weights=y_present, minlength=edges.size + 1)
    uppers = list(edges) + [np.inf]
    bins = [{"count": int(c), "events": float(e), "upper": u, "members": []}
            for c, e, u in zip(counts, events, uppers) if c > 0]

    # Монотонность: сливаем первую пару соседей, нарушающую ожидаемое направление, пока такие есть.
    while True:
        violation = next((i for i in range(len(bins) - 1)
                          if direction * (_rate(bins[i]) - _rate(bins[i + 1])) > 0), None)
        if violation is None:
            break
        _merge(bins, violation)
    _merge_small(bins, min_count)
    _limit(bins, max_bins)
    return _finish(name, "numeric", bins, y, missing, missing_min_share, neutral_missing,
                   edges=[float(b["upper"]) for b in bins[:-1]])


def fit_categorical(name: str, values, target, min_share: float = 0.05, max_bins: int = 8,
                    missing_min_share: float = 0.01) -> Binning:
    keys = pd.Series(category_keys(values), dtype=object)
    y = np.asarray(target, dtype=int)
    missing = keys.isna().to_numpy()
    min_count = min_share * y.size
    table = pd.DataFrame({"key": keys[~missing].to_numpy(), "y": y[~missing]}).groupby("key")["y"].agg(["size", "sum"])
    table = table.assign(rate=table["sum"] / table["size"]).sort_values("rate")
    # По возрастанию доли дефолтов: соседи по списку — ближайшие по риску категории.
    bins = [{"count": int(row["size"]), "events": float(row["sum"]), "upper": None, "members": [str(key)]}
            for key, row in table.iterrows()]
    _merge_small(bins, min_count)
    _limit(bins, max_bins)
    return _finish(name, "categorical", bins, y, missing, missing_min_share, groups=[sorted(b["members"]) for b in bins])
