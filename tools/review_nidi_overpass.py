#!/usr/bin/env python3
"""Find candidate locations for still-unmapped nurseries from OpenStreetMap Overpass.
Candidates are NOT published to the map until reviewed.
"""
import json
import pathlib
import re
import urllib.parse
import urllib.request
import unicodedata
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
FOLDER=ROOT/"nidi-roma"
HTML=(FOLDER/"index.html").read_text(encoding="utf-8")
BASE=json.loads(re.search(r"const STRUCTURES = (\[[^\n]*\]);",HTML).group(1))
EXTRA=json.loads(re.search(r'const EXTRA_ROWS=("[^\n]*");',HTML).group(1))
for line in EXTRA.splitlines():
    town,mun,name,address,*_=line.split("|")
    BASE.append({"nome":name,"indirizzo":address,"comune":town,"municipio":mun})
KNOWN={}
for k in ("BUNDLED_COORDS","ADDITIONAL_GEOCODES","GEOROMA_GEOCODES","SCHOOLS_GEOCODES"):
    KNOWN.update(json.loads(re.search(r"const "+k+r" = (\{[^\n]*\});",HTML).group(1)))
TARGET=[r for r in BASE if ((r.get("comune") or "Roma")+" | "+r["indirizzo"]).upper().strip() not in KNOWN]

def normal(s):
    s=unicodedata.normalize("NFD",str(s or "").upper())
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+"," ",re.sub(r"[^A-Z0-9 ]"," ",s)).strip()

def nameparts(s):
    return [t for t in normal(s).split() if t not in
            {"IL","LA","L","LO","DI","DEI","DEL","DELLA","DELL","ASILO","NIDO",
             "COMUNALE","COMUNALI","SCUOLA","INFANZIA","POLO","0","6",
             "I","DA","DE","A","VIA","MICRONIDO","SEZIONE","PROGETTO","EX"}]

def similarity(a,b):
    aa,bb=set(nameparts(a)),set(nameparts(b))
    if not aa or not bb:return 0
    return len(aa&bb)/max(len(aa),len(bb))

def query(text):
    body=urllib.parse.urlencode({"data":text}).encode()
    endpoints=["https://overpass.kumi.systems/api/interpreter",
               "https://overpass-api.de/api/interpreter"]
    for ep in endpoints:
        try:
            req=urllib.request.Request(ep,data=body,
                headers={"User-Agent":"RomaNidiMap/1.1 contact https://github.com/nebelwerfer41/nebelwerfer41.github.io",
                         "Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as res:
                data=json.load(res)
            print("Successful Overpass",ep,len(data.get("elements",[])),flush=True)
            return data
        except Exception as e:
            print("Overpass error",ep,type(e).__name__,str(e)[:200],flush=True)
    return {"elements":[]}

def run():
    # Search only for still unresolved facility names; split to avoid expensive queries.
    groups=[TARGET[:15],TARGET[15:]]
    items={}
    for group in groups:
        pattern="|".join(re.escape(n) for n in
          sorted({t for r in group for t in ([r["nome"]] + ([" ".join(nameparts(r["nome"]))] if len(nameparts(r["nome"]))>1 else []))},key=len,reverse=True))
        pattern=pattern.replace('"',r'\"')
        q='[out:json][timeout:35];nwr(41.3,11.4,42.6,13.4)["name"~"'+pattern+'",i];out center tags;'
        data=query(q)
        for o in data.get("elements",[]):
            lat=o.get("lat",o.get("center",{}).get("lat"))
            lon=o.get("lon",o.get("center",{}).get("lon"))
            if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)):continue
            items[f'{o["type"]}:{o["id"]}']={"lat":lat,"lng":lon,"name":o.get("tags",{}).get("name",""),"tags":o.get("tags",{})}
        time.sleep(2)
    result=[]
    for r in TARGET:
        matches=[]
        for id,o in items.items():
            score=similarity(r["nome"],o["name"])
            if score<0.58:continue
            tags=o["tags"]
            matches.append({"id":id,"name":o["name"],"lat":o["lat"],"lng":o["lng"],
                            "score":round(score,3),"street":tags.get("addr:street",""),
                            "number":tags.get("addr:housenumber",""),
                            "city":tags.get("addr:city",""),
                            "amenity":tags.get("amenity","")})
        matches.sort(key=lambda x:x["score"],reverse=True)
        result.append({"target":r,"matches":matches[:12]})
    dest=FOLDER/"overpass-candidates.json"
    dest.write_text(json.dumps({"count":len(TARGET),"references":result,
                                 "matched":sum(bool(r["matches"]) for r in result),
                                 "rawItems":len(items)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("REPORT",len(TARGET),"matched",sum(bool(r["matches"]) for r in result),"unique OSM objects",len(items),flush=True)

if __name__=="__main__":
    run()
