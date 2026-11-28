#!/usr/bin/env python3
"""One-shot Photon/Komoot address search for unlocated nurseries.
Report only high-confidence address matching with exact house numbers.
"""
import json,re,urllib.parse,urllib.request,pathlib,time,unicodedata
ROOT=pathlib.Path(__file__).resolve().parents[1]
folder=ROOT/"nidi-roma"
html=(folder/"index.html").read_text(encoding="utf-8")
rows=json.loads(re.search(r"const STRUCTURES = (\[[^\n]*\]);",html).group(1))
for line in json.loads(re.search(r'const EXTRA_ROWS=("[^\n]*");',html).group(1)).splitlines():
 town,mun,name,address,*_=line.split("|")
 rows.append({"nome":name,"comune":town,"indirizzo":address})
found={}
for name in ("BUNDLED_COORDS","ADDITIONAL_GEOCODES","GEOROMA_GEOCODES","SCHOOLS_GEOCODES","REVIEWED_GEOCODES"):
 found.update(json.loads(re.search(r"const "+name+r" = (\{[^\n]*\});",html).group(1)))
def norm(s):
 s=unicodedata.normalize("NFD",str(s or "").upper())
 s="".join(ch for ch in s if not unicodedata.combining(ch))
 return re.sub(r"\s+"," ",re.sub(r"[^A-Z0-9 ]"," ",s)).strip()
ignore={"VIA","VIALE","LARGO","PIAZZA","PIAZZALE","DEL","DI","DELLA","DEI","D","DA","DEGLI","DELLE","S","SAN","SANTA"}
def road(s):
 return [w for w in norm(s).split() if w not in ignore and not w.isdigit()]
def classify(target,feature):
 p=feature["properties"]
 coords=feature["geometry"]["coordinates"]
 lat,lon=coords[1],coords[0]
 if not (41.35<lat<42.5 and 11.2<lon<13.4):return None
 town=target.get("comune","Roma")
 actual=p.get("city") or p.get("county") or ""
 if town!="Roma" and norm(town) not in norm(actual+" "+p.get("state","")):return None
 # For Rome, smaller towns and municipalities around city are sometimes tagged as Rome.
 if town=="Roma" and not (41.65<lat<42.15 and 12.2<lon<12.85):return None
 name=p.get("street","") or p.get("name","")
 aa=set(road(target["indirizzo"]));bb=set(road(name))
 if len(aa)<1 or len(bb)<1 or len(aa&bb)/len(aa)<.85:return None
 match=re.search(r",?\s+(\d{1,4}[A-Z]?)\s*(?:/\d+[A-Z]?)?\s*$",target["indirizzo"],re.I)
 want=norm(match.group(1)) if match else ""
 got=norm(p.get("housenumber",""))
 if want:
  if got!=want:return None
  quality="Photon-exact-civic"
 else:
  # No civic number: only allow exact named POI.
  targetName=norm(target["nome"])
  gotName=norm(p.get("name",""))
  if targetName!=gotName:return None
  quality="Photon-POI-no-civic"
 return {"lat":lat,"lng":lon,"quality":quality,"address":name,"number":got,"provider":"Photon/OSM","matchedCity":actual}
def main():
 missing=[r for r in rows if ((r.get("comune") or "Roma")+" | "+r["indirizzo"]).upper().strip() not in found]
 accepted={};unresolved=[]
 for i,row in enumerate(missing):
  town=row.get("comune") or "Roma"
  q=row["indirizzo"]+", "+town+", Lazio"
  url="https://photon.komoot.io/api/?"+urllib.parse.urlencode({"q":q,"limit":10,"lang":"it"})
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"RomaNidiMap/1.1 contact https://github.com/nebelwerfer41/nebelwerfer41.github.io"})
   with urllib.request.urlopen(req,timeout=12) as res:result=json.load(res)
   options=[a for f in result.get("features",[]) if (a:=classify(row,f))]
   if options:
    choice=options[0]
    key=(town+" | "+row["indirizzo"]).upper().strip()
    accepted[key]=choice
    print(i+1,"MATCH",row["nome"],q,choice["lat"],choice["lng"],flush=True)
   else:
    unresolved.append({"name":row["nome"],"addr":row["indirizzo"],"town":town})
    print(i+1,"NOT_MATCHED",q,flush=True)
  except Exception as e:
   unresolved.append({"name":row["nome"],"addr":row["indirizzo"],"town":town,"error":str(e)})
   print(i+1,"ERROR",str(e),flush=True)
  time.sleep(0.85)
 (folder/"coordinates-photon.json").write_text(json.dumps(accepted,ensure_ascii=False,indent=2)+"\n")
 (folder/"coordinates-photon-report.json").write_text(json.dumps({"attempted":len(missing),"found":len(accepted),"notFound":unresolved},ensure_ascii=False,indent=2)+"\n")
 print("REPORT",len(missing),len(accepted),flush=True)
if __name__=="__main__":main()
