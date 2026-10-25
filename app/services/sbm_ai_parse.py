"""SBM table parsing for the sbm_draft helper: rows and amounts are read by code only.

One annex table per paste. Shapes tried in order: province (annex 31, 30, 16), road
(annex 1), route (annex 17), single national amount (annex 3). The fixed province map
turns the PMK spellings ("R I A U", "D.K.I. JAKARTA") into PROV-xx codes. The AI only
names components and grade groups, never amounts.
"""
import hashlib
import re
from typing import Optional

# --- fixed province map: (ISO suffix, display name, names as written in the PMK) ---
_P = [
    ("AC", "Aceh", "ACEH"), ("SU", "Sumatera Utara", "SUMATRA UTARA", "SUMATERA UTARA"),
    ("RI", "Riau", "RIAU"), ("KR", "Kepulauan Riau", "KEPULAUAN RIAU"), ("JA", "Jambi", "JAMBI"),
    ("SB", "Sumatera Barat", "SUMATRA BARAT", "SUMATERA BARAT"),
    ("SS", "Sumatera Selatan", "SUMATRA SELATAN", "SUMATERA SELATAN"),
    ("LA", "Lampung", "LAMPUNG"), ("BE", "Bengkulu", "BENGKULU"),
    ("BB", "Kepulauan Bangka Belitung", "BANGKA BELITUNG", "KEPULAUAN BANGKA BELITUNG"),
    ("BT", "Banten", "BANTEN"), ("JB", "Jawa Barat", "JAWA BARAT"),
    ("JK", "DKI Jakarta", "D.K.I. JAKARTA", "DKI JAKARTA", "JAKARTA"),
    ("JT", "Jawa Tengah", "JAWA TENGAH"), ("YO", "DI Yogyakarta", "D.I. YOGYAKARTA", "YOGYAKARTA"),
    ("JI", "Jawa Timur", "JAWA TIMUR"), ("BA", "Bali", "BALI"),
    ("NB", "Nusa Tenggara Barat", "NUSA TENGGARA BARAT"), ("NT", "Nusa Tenggara Timur", "NUSA TENGGARA TIMUR"),
    ("KB", "Kalimantan Barat", "KALIMANTAN BARAT"), ("KT", "Kalimantan Tengah", "KALIMANTAN TENGAH"),
    ("KS", "Kalimantan Selatan", "KALIMANTAN SELATAN"), ("KI", "Kalimantan Timur", "KALIMANTAN TIMUR"),
    ("KU", "Kalimantan Utara", "KALIMANTAN UTARA"), ("SA", "Sulawesi Utara", "SULAWESI UTARA"),
    ("GO", "Gorontalo", "GORONTALO"), ("SR", "Sulawesi Barat", "SULAWESI BARAT"),
    ("SN", "Sulawesi Selatan", "SULAWESI SELATAN"), ("ST", "Sulawesi Tengah", "SULAWESI TENGAH"),
    ("SG", "Sulawesi Tenggara", "SULAWESI TENGGARA"), ("MA", "Maluku", "MALUKU"),
    ("MU", "Maluku Utara", "MALUKU UTARA"), ("PA", "Papua", "PAPUA"), ("PB", "Papua Barat", "PAPUA BARAT"),
    ("PD", "Papua Barat Daya", "PAPUA BARAT DAYA"), ("PT", "Papua Tengah", "PAPUA TENGAH"),
    ("PS", "Papua Selatan", "PAPUA SELATAN"), ("PE", "Papua Pegunungan", "PAPUA PEGUNUNGAN"),
]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z]", "", s.upper())


PROVINCES = {_norm(a): f"PROV-{p[0]}" for p in _P for a in p[2:]}
PROV_NAMES = {f"PROV-{p[0]}": p[1] for p in _P}

_NUM = re.compile(r"^\d{1,4}\.?$")
_UNIT = re.compile(r"^(O[A-Za-z]|Orang/[A-Za-z]+)$")  # OP, OH, Orang/Kali
_AMT = re.compile(r"^Rp\s*([\d.,]+)$")
_AMT_ANY = re.compile(r"Rp\s*([\d.,]+)")
_COLNUM = re.compile(r"^\(\d+\)$")
_PAGE = re.compile(r"^-\s*\d+\s*-$")
_BLOCK = re.compile(r"^([a-zA-Z])\.\s+\S")


def _amount(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", ".")) if "," in raw else float(raw.replace(".", ""))


def _amt(line: str) -> float:
    return _amount(_AMT.match(line).group(1))


# --- table readers, one per shape. Each returns (entries, skipped notes, used line indexes) ---

def _scan_province(lines):
    """number, province name, unit, amounts (Lampiran 31, 30, 16)."""
    entries, skipped, used = [], [], set()
    block, i, n = "", 0, len(lines)
    while i < n:
        ln = lines[i]
        if _NUM.match(ln) and i + 2 < n and _UNIT.match(lines[i + 2]):
            name, j, amts = lines[i + 1], i + 3, []
            while j < n and _AMT.match(lines[j]):
                amts.append(_amt(lines[j]))
                j += 1
            code = PROVINCES.get(_norm(name))
            if code:
                entries.append({"kind": "province", "block": block, "code": code, "name": name, "amounts": amts})
            else:
                skipped.append(f"{name} ({len(amts)} amounts)")
            used.update(range(i, j))
            i = j
            continue
        m = _BLOCK.match(ln)
        if m:
            block = m.group(1).lower()
        i += 1
    return entries, skipped, used


def _scan_road(lines):
    """province heading, then rows: number, capital, regency or city, unit, ONE amount (Lampiran 1)."""
    entries, skipped, used = [], [], set()
    prov, i, n = None, 0, len(lines)
    while i < n:
        ln = lines[i]
        if (_NUM.match(ln) and i + 4 < n and not _AMT.match(lines[i + 1]) and not _AMT.match(lines[i + 2])
                and _UNIT.match(lines[i + 3]) and _AMT.match(lines[i + 4])):
            entries.append({"kind": "road", "origin": lines[i + 1], "dest": lines[i + 2], "province": prov,
                            "amounts": [_amt(lines[i + 4])]})
            used.update(range(i, i + 5))
            i += 5
            continue
        if i + 1 < n and _NUM.match(lines[i + 1]) and PROVINCES.get(_norm(ln)):
            prov = PROVINCES[_norm(ln)]
            used.add(i)
        i += 1
    return entries, skipped, used


def _scan_route(lines):
    """number, origin city, destination city, amounts (Lampiran 17)."""
    entries, skipped, used = [], [], set()
    i, n = 0, len(lines)
    while i < n:
        if _NUM.match(lines[i]) and i + 2 < n and not any(
                _AMT.match(lines[k]) or _NUM.match(lines[k]) or _UNIT.match(lines[k]) for k in (i + 1, i + 2)):
            j, amts = i + 3, []
            while j < n and _AMT.match(lines[j]):
                amts.append(_amt(lines[j]))
                j += 1
            if amts:
                entries.append({"kind": "route", "origin": lines[i + 1], "dest": lines[i + 2], "amounts": amts})
                used.update(range(i, j))
                i = j
                continue
            if j >= n:  # the pasted text ends in the middle of a row
                skipped.append(f"{lines[i + 1]} to {lines[i + 2]} (cut off, no amounts)")
                used.update(range(i, j))
                i = j
                continue
        i += 1
    return entries, skipped, used


def _scan(source: str):
    """Returns (shape, entries, structure lines, skipped notes). Amounts are read by code only."""
    lines = [x.strip() for x in source.splitlines() if x.strip()]
    shape, entries, skipped, used = None, [], [], set()
    for name, fn in (("province", _scan_province), ("road", _scan_road), ("route", _scan_route)):
        e, s, u = fn(lines)
        if e:
            shape, entries, skipped, used = name, e, s, u
            break
    if not shape:
        found = _AMT_ANY.findall(source)
        if len(found) == 1:  # one national amount, no place (Lampiran 3)
            shape, entries = "single", [{"kind": "single", "amounts": [_amount(found[0])]}]
    structure, seen = [], set()
    for k, ln in enumerate(lines):  # first occurrence keeps the column order
        if k in used or _NUM.match(ln) or _PAGE.match(ln) or _COLNUM.match(ln) or _AMT.match(ln):
            continue
        if ln not in seen:
            seen.add(ln)
            structure.append(ln)
    return shape, entries, structure, skipped


def _cap(notes: list) -> list:
    return notes if len(notes) <= 20 else notes[:20] + [f"... and {len(notes) - 20} more"]


# --- places ---

def _title(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).title()[:100]


def _city_code(name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    code = f"CITY-{base}"
    if len(code) > 30:
        code = f"CITY-{base[:20]}-{hashlib.md5(name.lower().encode()).hexdigest()[:4]}"
    return code


def _add_city(places: dict, name: str, prov_code: Optional[str] = None) -> str:
    title = _title(name)
    code = _city_code(title)
    prov = PROV_NAMES.get(prov_code) if prov_code else None
    if code not in places:
        places[code] = {"code": code, "name": title, "city": title, "province": prov}
    elif prov and not places[code]["province"]:
        places[code]["province"] = prov
    return code


def _add_province(places: dict, code: str) -> str:
    if code not in places:
        places[code] = {"code": code, "name": f"Provinsi {PROV_NAMES[code]}", "city": None, "province": PROV_NAMES[code]}
    return code


def _nm(s) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    return re.sub(r"\bkab\.\s*|\bkab\s+", "kabupaten ", s).strip()


def _core(s) -> str:
    return re.sub(r"^(kabupaten|kota)\s+", "", _nm(s))


def _match_rows(rows, spec: dict):
    """Match a place spec against ONE tier of ref_location rows (the org's or the national master)."""
    code = spec["code"].lower()
    hit = [r for r in rows if r.location_code.lower() == code]
    if not hit and not code.startswith("prov-"):
        key = _nm(spec["name"])
        hit = [r for r in rows if key in (_nm(r.location_code), _nm(r.location_name), _nm(r.city))]
        if not hit and not key.startswith(("kabupaten ", "kota ")):
            core = _core(spec["name"])
            hit = [r for r in rows if core and core in (_core(r.location_name), _core(r.city))]
        if len(hit) > 1 and spec.get("province"):
            narrowed = [r for r in hit if r.province and _nm(r.province) == _nm(spec["province"])]
            hit = narrowed or hit
        if len(hit) > 1:
            # the row whose name is spelled exactly as in the table beats longer spellings
            exact = [r for r in hit if _nm(r.location_name) == key]
            hit = exact or hit
    return hit


def _resolve(rows, spec: dict):
    """Match a place to an existing location: the organisation's own rows first, then the shared
    national master (ref_location rows with root_org_id IS NULL). Returns (location_id or None, ambiguous)."""
    tiers = ([r for r in rows if r.root_org_id is not None],
             [r for r in rows if r.root_org_id is None])
    for tier in tiers:
        hit = _match_rows(tier, spec)
        if len(hit) == 1:
            return hit[0].location_id, False
        if len(hit) > 1:
            return None, True
    return None, False
