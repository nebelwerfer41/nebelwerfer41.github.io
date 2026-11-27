#!/usr/bin/env python3
"""Geolocate 2026 nursery entries from Roma Capitale 2024 civil-protection tables.

The SC6 coordinates in the 2024 report are identified as 2019 data.
Only addresses that can be reconciled confidently are exported.
"""
import json
import pathlib
import re
import sys
import unicodedata
import urllib.request
from difflib import SequenceMatcher

SOURCE = "https://www.comune.roma.it/web-resources/cms/documents/PPC2024_1_InformazioneGenerale_Allegati.pdf"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "nidi-roma" / "coordinates.json"
REPORT = ROOT / "nidi-roma" / "coordinates-report.json"


def clean(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = s.replace("’", "'").replace("'", " ")
    s = re.sub(r"\bS[.]\s+", "SAN ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


STREET_TYPES = {"VIA", "VIALE", "LARGO", "LARG0", "PIAZZA", "PIAZZALE", "SALITA",
                "CIRCONVALLAZIONE", "VICOLO", "STRADA", "LUNGOTEVERE", "PZA", "PZZA"}
ARTICLES = {"DI", "DEL", "DELLA", "DELL", "DEI", "DEGLI", "DELLE", "DA", "D", "LA", "LE"}
ROAD_RE = re.compile(r"\b(?:VIA|VIALE|PIAZZALE|PIAZZA|LARGO|SALITA|CIRCONVALLAZIONE|STRADA|LUNGOTEVERE|VICOLO)\b", re.I)


def address(s):
    raw = str(s or "").upper()
    raw = re.sub(r",?\s*(?:SNC|S\.N\.C\.)\s*$", "", raw)
    house = ""
    # Only the trailing house number counts; numerals in street names do not.
    match = re.search(r"(?:,|\s)(\d{1,4}[A-Z]?)(?:\s*[/\-]\s*\d+[A-Z]?)?\s*$", raw)
    if match:
        house = match.group(1)
        raw = raw[:match.start()].strip(" ,")
    tokens = clean(raw).split()
    if tokens and tokens[0] in STREET_TYPES:
        tokens = tokens[1:]
    core = " ".join(t for t in tokens if t not in ARTICLES)
    return core, house


def normal_name(s):
    tokens = clean(s).split()
    drop = {"POLO", "NIDO", "MICRONIDO", "ASILO", "SEZIONE", "PONTE", "INFANZIA", "06", "0", "6"}
    return " ".join(t for t in tokens if t not in drop)


def name_score(a, b):
    a, b = normal_name(a), normal_name(b)
    if not a or not b:
        return 0
    if a == b:
        return 1
    return SequenceMatcher(None, a, b).ratio()


def load_original():
    html = (ROOT / "nidi-roma" / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const STRUCTURES = (\[[^\n]+\]);", html)
    if not m:
        raise RuntimeError("STRUCTURES not found in HTML")
    rows = json.loads(m.group(1))
    e = re.search(r"const EXTRA_ROWS=(\"[^\n]*\");", html)
    if not e:
        raise RuntimeError("EXTRA_ROWS not found in HTML")
    for n, line in enumerate(json.loads(e.group(1)).splitlines(), 1):
        comune, _municipio, nome, addr, _subtipo, _fonte = line.split("|")
        rows.append({"id": "extra-%02d" % n, "nome": nome, "indirizzo": addr, "comune": comune})
    return rows


def fetch_document(path):
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "RomaNidiMap/1.0 (public data comparison)"})
    with urllib.request.urlopen(req, timeout=100) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("Remote file is not a PDF")
    path.write_bytes(data)
    print("Downloaded city PDF:", len(data), "bytes")


def parse_pdf(path):
    import pdfplumber
    found = {}
    with pdfplumber.open(str(path)) as pdf:
        print("Source pages:", len(pdf.pages))
        # SC6 is at printed pages 95-106; include a few surrounding pages.
        page_start = min(90, len(pdf.pages))
        page_end = min(115, len(pdf.pages))
        for index in range(page_start, page_end):
            page = pdf.pages[index]
            text = page.extract_text() or ""
            if "SC6" not in text:
                continue
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines", "horizontal_strategy": "lines",
                "snap_tolerance": 3, "intersection_tolerance": 4
            })
            for table in tables:
                for cells in table:
                    if not cells or len(cells) < 7:
                        continue
                    v = [" ".join(str(x or "").split()) for x in cells if str(x or "").strip()]
                    # Some tables contain extra empty columns.
                    at = next((i for i, x in enumerate(v) if x.strip() == "SC6"), -1)
                    if at < 0 or at < 1 or at + 5 >= len(v):
                        continue
                    try:
                        lat, lon = float(v[at+4].replace(",", ".")), float(v[at+5].replace(",", "."))
                    except (ValueError, IndexError):
                        continue
                    if not (41.45 < lat < 42.3 and 11.6 < lon < 13.1):
                        continue
                    try: ident = str(int(v[at-1]))
                    except ValueError: continue
                    found[ident] = {"id": ident, "municipio": v[at+1],
                                    "nome": v[at+2], "indirizzo": v[at+3],
                                    "lat": lat, "lng": lon}
    print("Parsed SC6 records:", len(found))
    return list(found.values())


def reconcile(targets, reference):
    results, examples, ambiguous = {}, [], []
    for r in targets:
        town = r.get("comune", "Roma")
        if town != "Roma":
            continue
        street, civico = address(r.get("indirizzo"))
        if not street or len(street) < 4:
            continue
        candidates = []
        for source in reference:
            otherstreet, othernum = address(source["indirizzo"])
            if street != otherstreet:
                continue
            score = name_score(r["nome"], source["nome"])
            if civico and othernum:
                if civico != othernum:
                    continue
                rank, quality = 3, "indirizzo"
            elif not civico and not othernum and score >= .81:
                rank, quality = 2, "via-e-nome"
            elif (not civico or not othernum) and score >= .93:
                rank, quality = 1, "via-e-nome-senza-civico"
            else:
                continue
            candidates.append((rank, score, source, quality))
        if not candidates:
            continue
        candidates.sort(key=lambda z: (z[0], z[1]), reverse=True)
        best_rank, best_score, winner, qual = candidates[0]
        near = [c for c in candidates if c[0] == best_rank and abs(c[1]-best_score) < .15]
        if len(near) > 1:
            # Multiple historical nurseries sharing the same address are fine if
            # their mapped locations agree within ~50 metres.
            coords = {(round(c[2]["lat"], 3), round(c[2]["lng"], 3)) for c in near}
            if len(coords) > 1:
                ambiguous.append({"id":r["id"], "name":r["nome"], "address":r["indirizzo"]})
                continue
        key = (town + " | " + r["indirizzo"]).upper().strip()
        results[key] = {"lat":winner["lat"], "lng":winner["lng"],
                        "quality":"storico-ufficiale-" + qual,
                        "sourceYear": 2019, "sourceId":winner["id"],
                        "sourceName":winner["nome"], "sourceAddress":winner["indirizzo"]}
        if len(examples) < 12:
            examples.append({"2026":r["nome"],"at":r["indirizzo"],
                             "2019":winner["nome"], "reference":winner["indirizzo"],"match":qual})
    return results, examples, ambiguous


def main():
    import tempfile
    targets=load_original()
    with tempfile.TemporaryDirectory() as t:
        p = pathlib.Path(t) / "roma.pdf"
        fetch_document(p)
        records=parse_pdf(p)
    if len(records) < 150:
        raise RuntimeError("SC6 extraction suspiciously small: "+str(len(records)))
    matches,examples,ambiguous=reconcile(targets,records)
    if len(matches) < 100:
        raise RuntimeError("Too few confident matches: "+str(len(matches)))
    OUT.write_text(json.dumps(matches, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    summary={"source":SOURCE,"sourceDatasetYear":2019,"sourceCount":len(records),
             "catalogCount":len(targets),"geolocated":len(matches),
             "remaining":len(targets)-len(matches),
             "ambiguous":ambiguous,"samples":examples}
    REPORT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("OUTPUT",json.dumps({k:v for k,v in summary.items() if k not in ("ambiguous","samples")},ensure_ascii=False))
    for example in examples: print("MATCH",example)


if __name__=="__main__":
    main()
