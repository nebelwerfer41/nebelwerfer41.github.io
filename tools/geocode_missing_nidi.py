#!/usr/bin/env python3
"""One-time, strictly validated OpenStreetMap address geocoding for Roma nurseries.

No guessed/centroid locations. Geographic outputs are generated independently
of Google (whose geocoding content cannot be put onto a MapLibre map).
"""
import json
import pathlib
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parents[1]
FOLDER = ROOT / "nidi-roma"
HTML = FOLDER / "index.html"
OFFICIAL = FOLDER / "coordinates.json"
OUT = FOLDER / "coordinates-extra.json"
REPORT = FOLDER / "coordinates-extra-report.json"

def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]+", " ", s)).strip()

ARTICLES = {"VIA","VIALE","PIAZZA","PIAZZALE","LARGO","CORSO","VICOLO",
            "CIRCONVALLAZIONE","STRADA","DEL","DI","DELLA","DEI","D","DA",
            "DEGLI","DELLE","S","SAN","SANTA","SANTO","E"}

def road_tokens(s):
    return [t for t in norm(s).split() if t not in ARTICLES and len(t)>1]

def street_similarity(a,b):
    aa,bb=road_tokens(a),set(road_tokens(b))
    if not aa or not bb: return 0
    return sum(t in bb for t in aa)/len(aa)

def street_info(raw):
    a=raw.strip()
    if re.search(r"\bKM\s*\d",a,re.I):
        return a,"",False
    m=re.search(r"(?:,|\s)\s*(\d{1,4}[A-Z]?)\s*(?:[/\\-]\s*\d+[A-Z]?)?\s*$",a,re.I)
    if m: return a[:m.start()].strip(" ,"),m.group(1).upper(),True
    return re.sub(r"\bSNC\b","",a,flags=re.I).strip(" ,"),"",False

def load_all():
    s=HTML.read_text(encoding="utf-8")
    main=json.loads(re.search(r"const STRUCTURES = (\[[^\n]*\]);",s).group(1))
    extra=json.loads(re.search(r'const EXTRA_ROWS=("[^\n]*");',s).group(1))
    for line in extra.splitlines():
        town,mun,name,addr,*_=line.split("|")
        main.append({"nome":name,"indirizzo":addr,"comune":town,"municipio":mun})
    return main

def town_match(town,result):
    address=result.get("address") or {}
    display=norm(result.get("display_name",""))
    expected=norm(town)
    components=" ".join(norm(address.get(k,"")) for k in ("city","town","village","municipality","county"))
    if expected=="ROMA":
        return "ROMA" in norm(components+" "+display)
    return expected in norm(components+" "+display)

def acceptable(item,result):
    try:lat,lng=float(result["lat"]),float(result["lon"])
    except (ValueError,TypeError,KeyError):return None
    town=item.get("comune","Roma")
    if town=="Roma":
        if not (41.65<lat<42.15 and 12.15<lng<12.83):return None
    elif not (41.35<lat<42.55 and 11.15<lng<13.45):
        return None
    if not town_match(town,result):return None
    road,house,has_house=street_info(item["indirizzo"])
    addr=result.get("address") or {}
    output_road=" ".join(str(addr.get(x,"")) for x in ("road","pedestrian","square","residential","footway","path","place"))
    display=result.get("display_name","")
    sim=max(street_similarity(road,output_road),street_similarity(road,display)*0.90)
    if sim<0.7:return None
    got_house=norm(addr.get("house_number","")).replace(" ","")
    got_house=re.split(r"[/\\-]",got_house)[0]
    target=norm(house).replace(" ","")
    # Require the exact house number wherever a civic address was supplied.
    if has_house:
        if not got_house or got_house!=target:return None
        quality="house-number-verified"
        rank=5+sim
    else:
        # Without a civic number, require exact school name in the mapping record.
        name=norm(item["nome"])
        displayed=norm(result.get("name","")+" "+display)
        v=SequenceMatcher(None,name,displayed[:len(name)+30]).ratio()
        if not name or (name not in displayed and v<.86):return None
        quality="named-place-no-house-number"
        rank=3+sim
    return {"lat":lat,"lng":lng,"quality":"osm-"+quality,
            "source":"OpenStreetMap Nominatim","displayAddress":display,
            "checkedAddress":item["indirizzo"],"rank":rank}

last=0
def search(query):
    global last
    delta=time.monotonic()-last
    if delta<1.25:time.sleep(1.25-delta)
    last=time.monotonic()
    url="https://nominatim.openstreetmap.org/search?"+urllib.parse.urlencode({
        "q":query, "countrycodes":"it","format":"jsonv2",
        "limit":8,"addressdetails":1,"accept-language":"it"
    })
    request=urllib.request.Request(url,headers={
        "User-Agent":"RomaNidiMap/1.1 (+https://github.com/nebelwerfer41/nebelwerfer41.github.io)",
        "Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=12) as res:
        return json.load(res)

def key(row):
    return ((row.get("comune") or "Roma")+" | "+row["indirizzo"]).upper().strip()

def main():
    allrows=load_all()
    official=json.loads(OFFICIAL.read_text(encoding="utf-8"))
    previous=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    targets={}
    for row in allrows:
        k=key(row)
        if k not in official and k not in previous:
            targets.setdefault(k,row)
    print("Targets unique:",len(targets), "of",len(allrows),"records",flush=True)
    found=dict(previous);rejected=[];errors=[]
    for i,(k,row) in enumerate(targets.items(),1):
        addr=row["indirizzo"];town=row.get("comune","Roma")
        road,house,_=street_info(addr)
        q=(road+" "+house+", "+town+", Lazio, Italia").strip()
        try:
            candidates=search(q)
            accepted=[a for obj in candidates if (a:=acceptable(row,obj))]
            # For named places, a second query can find an actual building POI.
            if not accepted and (not house or not candidates):
                candidates=search(row["nome"]+", "+addr+", "+town+", Italia")
                accepted=[a for obj in candidates if (a:=acceptable(row,obj))]
            if accepted:
                best=max(accepted,key=lambda a:a["rank"])
                best.pop("rank",None)
                found[k]=best
                print(f"{i}/{len(targets)} OK {row['nome']} | {addr} -> {best['lat']:.6f},{best['lng']:.6f} [{best['quality']}]",flush=True)
            else:
                rejected.append({"name":row["nome"],"address":addr,"town":town})
                print(f"{i}/{len(targets)} NOT_MATCHED {row['nome']} | {addr}",flush=True)
        except Exception as e:
            errors.append({"name":row["nome"],"address":addr,"error":str(e)})
            print(f"{i}/{len(targets)} ERROR {row['nome']} {type(e).__name__}: {e}",flush=True)
            if len(errors)>=8 and len(found)==len(previous):
                print("Too many errors without a successful match; stopping early",flush=True)
                break
    OUT.write_text(json.dumps(found,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary={"provider":"OpenStreetMap Nominatim","source":"https://nominatim.openstreetmap.org/",
             "originalMunicipalCoordinates":len(official),
             "newVerifiedAddresses":len(found),"attempted":len(targets),
             "rejected":rejected,"errors":errors,
             "matchingRule":"Same municipality, matching street, exact house number (or exact named POI for addresses without number)"}
    REPORT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("REPORT",json.dumps({k:v if not isinstance(v,list) else len(v) for k,v in summary.items()}),flush=True)

if __name__=="__main__":
    main()
