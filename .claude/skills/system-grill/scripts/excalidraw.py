#!/usr/bin/env python3
"""system-grill 설계도 spec(JSON) -> Obsidian Excalidraw 파일(.excalidraw.md).

사용법: python3 -I excalidraw.py <spec.json> <출력.excalidraw.md>

spec 형식:
{
  "lanes": ["클라이언트", "진입", "서비스", "메시지·캐시", "저장소"],   # 왼쪽 -> 오른쪽, 빈 계층은 빼고 적는다
  "nodes": [ {"id": "lbs", "lane": 2, "row": 0, "label": "LBS\\nQ4 지오해시", "kind": "svc"} ],
  "edges": [ {"from": "lb", "to": "lbs", "label": "②", "style": "solid"} ],
  "legend": "실선 = 주변 검색 · 점선 = 쓰기·비동기 · 굵은 빨간 선 = 돌발 대응"
}
kind:  client | svc | cache | bus | db   (db 는 타원, 나머지는 둥근 상자)
style: solid(핵심 흐름) | dashed(쓰기·비동기) | bold(돌발 대응)
"""
import json, sys

W, H, GX, GY = 220, 80, 320, 140
COLOR = {"client": "#e9ecef", "svc": "#a5d8ff", "cache": "#ffec99", "bus": "#d0bfff", "db": "#b2f2bb"}
COMMON = dict(angle=0, strokeColor="#1e1e1e", fillStyle="solid", strokeWidth=2, strokeStyle="solid",
              roughness=1, opacity=100, groupIds=[], frameId=None, version=1, isDeleted=False,
              updated=1, link=None, locked=False)


def build(spec):
    els, texts, seq = [], [], [100]

    def seed():
        seq[0] += 1
        return seq[0]

    def text(id, x, y, w, h, t, container=None, size=16):
        els.append(dict(COMMON, id=id, type="text", x=x, y=y, width=w, height=h,
                        backgroundColor="transparent", roundness=None, seed=seed(), versionNonce=seed(),
                        boundElements=None, text=t, originalText=t, fontSize=size, fontFamily=2,
                        textAlign="center", verticalAlign="middle", containerId=container,
                        autoResize=True, lineHeight=1.25))
        texts.append((t, id))

    for i, name in enumerate(spec["lanes"]):
        text(f"lane{i}", i * GX, -70, W, 25, name, size=20)

    box, max_row = {}, 0
    for n in spec["nodes"]:
        kind = n.get("kind", "svc")
        x, y = n["lane"] * GX, n["row"] * GY
        max_row = max(max_row, n["row"])
        e = dict(COMMON, id=n["id"], type="ellipse" if kind == "db" else "rectangle", x=x, y=y,
                 width=W, height=H, backgroundColor=COLOR[kind],
                 roundness=None if kind == "db" else {"type": 3}, seed=seed(), versionNonce=seed(),
                 boundElements=[{"type": "text", "id": n["id"] + "-t"}])
        els.append(e)
        box[n["id"]] = e
        text(n["id"] + "-t", x + 10, y + 20, W - 20, 40, n["label"], container=n["id"])

    for k, ed in enumerate(spec["edges"]):
        eid, a, b = f"e{k}", box[ed["from"]], box[ed["to"]]
        if a["x"] == b["x"]:  # 같은 계층: 위아래로 연결
            down = b["y"] > a["y"]
            sx, sy = a["x"] + W / 2, a["y"] + H if down else a["y"]
            ex, ey = b["x"] + W / 2, b["y"] if down else b["y"] + H
        elif a["x"] < b["x"]:  # 왼쪽 -> 오른쪽
            sx, sy, ex, ey = a["x"] + W, a["y"] + H / 2, b["x"], b["y"] + H / 2
        else:  # 오른쪽 -> 왼쪽 (응답 등)
            sx, sy, ex, ey = a["x"], a["y"] + H / 2, b["x"] + W, b["y"] + H / 2
        dx, dy = ex - sx, ey - sy
        arr = dict(COMMON, id=eid, type="arrow", x=sx, y=sy, width=abs(dx), height=abs(dy),
                   backgroundColor="transparent", roundness={"type": 2}, seed=seed(), versionNonce=seed(),
                   points=[[0, 0], [dx, dy]], lastCommittedPoint=None,
                   startBinding={"elementId": ed["from"], "focus": 0, "gap": 4},
                   endBinding={"elementId": ed["to"], "focus": 0, "gap": 4},
                   startArrowhead=None, endArrowhead="arrow", elbowed=False, boundElements=[])
        style = ed.get("style", "solid")
        if style == "dashed":
            arr["strokeStyle"] = "dashed"
        elif style == "bold":
            arr["strokeWidth"], arr["strokeColor"] = 4, "#e03131"
        els.append(arr)
        a["boundElements"].append({"type": "arrow", "id": eid})
        b["boundElements"].append({"type": "arrow", "id": eid})
        if ed.get("label"):
            arr["boundElements"].append({"type": "text", "id": eid + "-t"})
            text(eid + "-t", sx + dx / 2 - 40, sy + dy / 2 - 10, 80, 20, ed["label"], container=eid, size=14)

    if spec.get("legend"):
        text("legend", 0, (max_row + 1) * GY + 40, 700, 25, spec["legend"])

    doc = {"type": "excalidraw", "version": 2,
           "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin",
           "elements": els, "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"}, "files": {}}
    text_section = "\n\n".join(f"{t} ^{i}" for t, i in texts)
    return ("---\n\nexcalidraw-plugin: parsed\ntags: [excalidraw]\n\n---\n"
            "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠==\n\n\n"
            f"# Excalidraw Data\n\n## Text Elements\n{text_section}\n\n%%\n## Drawing\n```json\n"
            f"{json.dumps(doc, ensure_ascii=False, indent=1)}\n```\n%%\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: excalidraw.py <spec.json> <out.excalidraw.md>")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    ids = {n["id"] for n in spec["nodes"]}
    bad = [e for e in spec["edges"] if e["from"] not in ids or e["to"] not in ids]
    if bad:
        sys.exit(f"edges 에 없는 노드 id: {bad}")
    open(sys.argv[2], "w", encoding="utf-8").write(build(spec))
    print(f"ok: {len(spec['nodes'])} nodes, {len(spec['edges'])} edges -> {sys.argv[2]}")
