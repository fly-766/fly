"""Fetch only locked official source files when absent; never replace an existing checkout."""
import hashlib,io,json,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/"config/contracts-deps.lock.json").read_text())
for name,spec in lock.items():
    base=ROOT/"lib"/name
    missing=[rel for rel in spec["files"] if not (base/rel).exists()]
    if missing:
        url="https://codeload.github.com/"+spec["repository"]+"/tar.gz/refs/tags/"+spec["tag"]
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(30_000_001)
        if len(data)>30_000_000:raise ValueError("Dependency archive too large")
        with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as archive:
            members={m.name.split("/",1)[1]:m for m in archive.getmembers() if "/" in m.name and m.isfile()}
            for rel in missing:
                item=members.get(rel)
                if item is None:raise ValueError("Locked source missing from official archive")
                body=archive.extractfile(item).read()
                if hashlib.sha256(body).hexdigest()!=spec["files"][rel]:raise ValueError("Official dependency differs from source lock")
                target=base/rel
                if not target.resolve().is_relative_to((ROOT/"lib").resolve()):raise ValueError("Invalid dependency path")
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
    for rel,expected in spec["files"].items():
        if hashlib.sha256((base/rel).read_bytes()).hexdigest()!=expected:raise ValueError("Existing dependency differs: "+name+"/"+rel)
    print(name,spec["tag"],len(spec["files"]),"locked files verified")
