import sys, json
sys.path.insert(0, "/home/matt/ozmadev/bigville")
from bigville.api import create_game
from domains import map_memory as mm
from domains.pack import load_pack
from bigville.tui import render as R
game = create_game(scenario="town100", seed=305000, player="Alby Marsh")
w = game.world
FARMER, INCOMER = "Thaddeus Ramskin", "Thaddeus Puddifoot"
class F: fogged = True
def show(name, title, centre=None, radius=None):
    game.backends[name] = F()
    if centre is None:
        sec = mm.map_section(game, name)
    else:
        sec = mm.map_section(game, name, centre=centre, radius=radius)
    view = game.agent_view(name)
    view["map"] = sec
    print(f"--- {title}: level={sec['level']} caption={sec['caption']!r}")
    lines = R._map_rows(view, "bigville", 9, 40)
    for line in lines:
        if line.strip(): print("   |" + line.rstrip())
    for lab in sec["labels"][:6]:
        print("   label", lab["glyph"], lab["word"])
    print("   paths", sec["paths"][:2])
    return view
reg = mm._registry(game)
print("ROLE", w.eng.node(w._actors[FARMER])["attrs"]["role"], "| INCOMER years", w.eng.node(w._actors[INCOMER])["attrs"]["history"]["years_in_village"])
inc0 = game.characters[INCOMER]
inc0.memories = [m for m in inc0.memories if not (isinstance(m.content, dict) and m.content.get("item") == "place:stone")]
show(FARMER, "farm labourer (Thaddeus Ramskin), own view")
show(FARMER, "farm labourer, window on the fields (full)", reg["field"][0], 3)
def vague_pick(name):
    content = mm.ensure_map(game, name)
    for place, entry in content["places"].items():
        if entry["level"] != 1 or place not in reg:
            continue
        cell = reg[place][0]
        s = mm.map_section(game, name, centre=cell, radius=1)
        if s["level"] == "vague":
            return place, cell
    return None
fp = vague_pick(FARMER)
print("farmer vague pick", fp)
show(FARMER, f"farm labourer, one-cell window on {fp[0]} (a rough place, no cell known: vague)", fp[1], 1)
# a hidden window: far from anything the farmer knows
content = mm.ensure_map(game, FARMER)
best = None
for x in range(2, 50, 4):
    for y in range(2, 38, 4):
        cell = (x, y)
        if cell not in w._map_cells: continue
        if any(mm._chebyshev(cell, c) <= 3 for name in content["places"] for c in mm._cells_of(game, content, name)): continue
        if any(k for k in content["cells"] if abs(int(k.split(",")[0])-x) <= 3 and abs(int(k.split(",")[1])-y) <= 3): continue
        best = cell; break
    if best: break
print("hidden centre", best)
show(FARMER, "farm labourer, window on unknown ground (hidden)", best, 3)
game.characters  # keep
show(INCOMER, "incomer (Thaddeus Puddifoot, 1 year), own view")
inc = game.characters[INCOMER]
# quarry removed from the routine, as the test does
inc.memories = [m for m in inc.memories if not (isinstance(m.content, dict) and m.content.get("item") == "place:stone")]
mm.ensure_map(game, INCOMER)
show(INCOMER, "incomer without the quarry on their routine, own view")
show(INCOMER, "incomer one-cell window on the quarry (nothing known there: hidden)", reg["stone"][0], 1)
ip = vague_pick(INCOMER)
print("incomer vague pick", ip)
show(INCOMER, f"incomer one-cell window on {ip[0]} (rough: vague)", ip[1], 1)
