#!/usr/bin/env python3
"""Trainer-roster Pokemon co-occurrence analytics.

Builds an undirected weighted graph where:
  * nodes  = every species that appears on at least one trainer's team,
  * edges  = a pair of species that share a roster, weighted by the number of
             trainers whose team contains both.

Then runs Louvain community detection plus a handful of network analyses and
emits an interactive HTML visualization (sprites pulled from the Pokemon
Showdown CDN) and a markdown report.
"""

from __future__ import annotations

import itertools
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import community as community_louvain
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from pyvis.network import Network

REPO = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
PARTIES = REPO / "randomizer" / "trainer_parties.h"
NAMES = REPO / "src" / "data" / "text" / "species_names.h"
TRAINERS = REPO / "randomizer" / "trainers.h"

SPRITE_URL = "https://play.pokemonshowdown.com/sprites/gen5/{slug}.png"

PARTY_BLOCK = re.compile(r"sParty_(\w+)\[\]\s*=\s*\{(.*?)\n\};", re.S)
SPECIES_REF = re.compile(r"\.species\s*=\s*(SPECIES_[A-Z0-9_]+)")
NAME_ROW = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*_\(\"([^\"]+)\"\)")

_SPRITE_JS = "https://play.pokemonshowdown.com/sprites/gen5/"

_SIDEBAR_JS = (
    "function pkSprite(slug){return '" + _SPRITE_JS + "'+slug+'.png';}\n"
    "function pkShow(id){\n"
    "  var d=POKE_INFO[id]; if(!d) return;\n"
    "  var h='<div id=\"pkHero\"><img src=\"'+pkSprite(d.slug)+'\">'+\n"
    "    '<div><h2 style=\"color:'+d.color+'\">'+d.name+'</h2>'+\n"
    "    '<div class=\"sub\">Community '+d.community+'</div></div></div>';\n"
    "  h+='<div class=\"stats\">'+\n"
    "    '<div class=\"stat\"><b>'+d.trainers+'</b><span>trainers field it</span></div>'+\n"
    "    '<div class=\"stat\"><b>'+d.individuals+'</b><span>total individuals</span></div>'+\n"
    "    '<div class=\"stat\"><b>'+d.degree+'</b><span>distinct teammates</span></div>'+\n"
    "    '<div class=\"stat\"><b>'+d.wdegree+'</b><span>weighted degree</span></div></div>';\n"
    "  h+='<h3>Top connections</h3>';\n"
    "  d.connections.slice(0,15).forEach(function(c){\n"
    "    h+='<div class=\"conn\" onclick=\"pkFocus(\\''+c.id+'\\')\">'+\n"
    "      '<img src=\"'+pkSprite(c.slug)+'\"><span class=\"n\">'+c.name+'</span>'+\n"
    "      '<span class=\"w\">'+c.weight+'</span></div>';\n"
    "  });\n"
    "  if(d.topTrainers.length){ h+='<h3>Fielded by</h3>';\n"
    "    d.topTrainers.forEach(function(t){h+='<div class=\"tr\">'+t+'</div>';}); }\n"
    "  document.getElementById('pkBody').innerHTML=h;\n"
    "  document.getElementById('pkSidebar').classList.add('open');\n"
    "}\n"
    "function pkFocus(id){ if(typeof network!=='undefined'&&network){\n"
    "    network.selectNodes([id]); network.focus(id,{scale:1.1,animation:true}); }\n"
    "  pkShow(id);\n"
    "}\n"
    "(function attach(){\n"
    "  if(typeof network==='undefined'||!network){return setTimeout(attach,120);}\n"
    "  network.on('click',function(p){ if(p.nodes.length){pkShow(p.nodes[0]);} });\n"
    "})();\n"
)

_LEGEND_JS = (
    "function pkBuildLegend(){\n"
    "  var el=document.getElementById('pkLegend');\n"
    "  var comms=Object.keys(COMM_INFO).map(Number).sort(function(a,b){\n"
    "    return COMM_INFO[b].size-COMM_INFO[a].size;});\n"
    "  var h='<h4>Communities</h4>';\n"
    "  h+='<div class=\"lg all\" onclick=\"pkIsolate(-1)\">\u2b1c Show all</div>';\n"
    "  comms.forEach(function(c){ var d=COMM_INFO[c];\n"
    "    if(d.size<2) return;\n"
    "    h+='<div class=\"lg\" id=\"lg'+c+'\" onclick=\"pkIsolate('+c+')\">'+\n"
    "      '<span class=\"sw\" style=\"background:'+d.color+'\"></span>'+\n"
    "      '<span class=\"t\">'+d.headliners.join(', ')+'</span>'+\n"
    "      '<span class=\"c\">'+d.size+'</span></div>';\n"
    "  });\n"
    "  el.innerHTML=h;\n"
    "}\n"
    "var pkActiveComm=-1;\n"
    "function pkIsolate(c){\n"
    "  if(typeof network==='undefined'||!network) return;\n"
    "  if(c===pkActiveComm) c=-1;\n"
    "  pkActiveComm=c;\n"
    "  var upd=[];\n"
    "  Object.keys(POKE_INFO).forEach(function(id){\n"
    "    var hide=(c!==-1 && POKE_INFO[id].community!==c);\n"
    "    upd.push({id:id,hidden:hide});\n"
    "  });\n"
    "  network.body.data.nodes.update(upd);\n"
    "  document.querySelectorAll('#pkLegend .lg').forEach(function(e){e.classList.remove('active');});\n"
    "  var act=document.getElementById('lg'+c); if(act) act.classList.add('active');\n"
    "}\n"
    "pkBuildLegend();\n"
)


_TRAINER_GRAPH_JS = (
    "function pkTab(t){\n"
    "  document.getElementById('pkLegend').style.display=(t==='legend')?'block':'none';\n"
    "  document.getElementById('pkTrainers').style.display=(t==='trainers')?'block':'none';\n"
    "  document.getElementById('tabLegend').classList.toggle('on',t==='legend');\n"
    "  document.getElementById('tabTr').classList.toggle('on',t==='trainers');\n"
    "}\n"
    "function pkTrApply(){\n"
    "  if(typeof network==='undefined'||!network) return;\n"
    "  var sel=[];document.querySelectorAll('#pkTrList input:checked').forEach(function(c){sel.push(+c.value);});\n"
    "  document.getElementById('pkTrCount').textContent=sel.length+' selected';\n"
    "  var show=null;\n"
    "  if(sel.length){show={};sel.forEach(function(i){TR_GRAPH[i].s.forEach(function(id){show[id]=1;});});}\n"
    "  var upd=[];\n"
    "  Object.keys(POKE_INFO).forEach(function(id){upd.push({id:id,hidden:show?!show[id]:false});});\n"
    "  network.body.data.nodes.update(upd);\n"
    "  if(sel.length){pkActiveComm=-1;document.querySelectorAll('#pkLegend .lg').forEach(function(e){e.classList.remove('active');});}\n"
    "}\n"
    "function pkTrGroup(g){\n"
    "  document.querySelectorAll('#pkTrList input').forEach(function(c){\n"
    "    if(g==='all'){c.checked=true;}else if(g==='none'){c.checked=false;}\n"
    "    else{c.checked=(TR_GRAPH[+c.value].g===g);}\n"
    "  });\n"
    "  pkTrApply();\n"
    "}\n"
    "function pkTrFilter(){var q=document.getElementById('pkTrSearch').value.toLowerCase();\n"
    "  document.querySelectorAll('#pkTrList .tr').forEach(function(e){\n"
    "    e.style.display=(!q||e.dataset.l.indexOf(q)>=0)?'':'none';});\n"
    "}\n"
)


def load_species_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for const, raw in NAME_ROW.findall(NAMES.read_text()):
        names[const] = raw.title()
    return names


def slug_for(const: str) -> str:
    return const.replace("SPECIES_", "").lower()


def parse_rosters() -> list[tuple[str, list[str]]]:
    text = PARTIES.read_text()
    rosters = []
    for name, body in PARTY_BLOCK.findall(text):
        species = SPECIES_REF.findall(body)
        if species:
            rosters.append((name, species))
    return rosters


def parse_trainer_labels() -> dict[str, str]:
    """Map sParty_<Name> -> human trainer label ("Class Name") from trainers.h."""
    text = TRAINERS.read_text()
    labels: dict[str, str] = {}
    # Each trainer entry references its party via *_MOVES(sParty_X) and has a
    # trainerName and trainerClass field nearby.
    for block in re.split(r"\[TRAINER_", text)[1:]:
        party = re.search(r"\(sParty_(\w+)\)", block)
        tname = re.search(r"\.trainerName\s*=\s*_\(\"([^\"]*)\"\)", block)
        tclass = re.search(r"\.trainerClass\s*=\s*TRAINER_CLASS_([A-Z0-9_]+)", block)
        if not party:
            continue
        name = tname.group(1).strip() if tname else ""
        cls = tclass.group(1).replace("_", " ").title() if tclass else ""
        label = (cls + " " + name).strip() or party.group(1)
        labels[party.group(1)] = label
    return labels


def parse_trainers() -> list[dict]:
    """Per-trainer records: {label, cls, group, species:[const,...]} from trainers.h."""
    text = TRAINERS.read_text()
    party_species: dict[str, list[str]] = {p: s for p, s in parse_rosters()}
    out: list[dict] = []
    seen: set[tuple] = set()
    for block in re.split(r"\[TRAINER_", text)[1:]:
        party = re.search(r"\(sParty_(\w+)\)", block)
        if not party:
            continue
        species = party_species.get(party.group(1))
        if not species:
            continue
        tname = re.search(r"\.trainerName\s*=\s*_\(\"([^\"]*)\"\)", block)
        tclass = re.search(r"\.trainerClass\s*=\s*TRAINER_CLASS_([A-Z0-9_]+)", block)
        cls_raw = tclass.group(1) if tclass else ""
        name = tname.group(1).strip() if tname else ""
        cls = cls_raw.replace("_", " ").title()
        label = (cls + " " + name).strip() or party.group(1)
        if cls_raw == "LEADER":
            group = "leaders"
        elif cls_raw in ("ELITE_FOUR", "CHAMPION"):
            group = "e4"
        elif cls_raw in ("TEAM_MAGMA", "MAGMA_ADMIN", "MAGMA_LEADER"):
            group = "magma"
        elif cls_raw in ("TEAM_AQUA", "AQUA_ADMIN", "AQUA_LEADER"):
            group = "aqua"
        else:
            group = ""
        key = (label, tuple(species))
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "cls": cls, "group": group, "species": species})
    out.sort(key=lambda t: (t["cls"], t["label"]))
    return out


def main() -> None:
    names = load_species_names()
    rosters = parse_rosters()
    labels = parse_trainer_labels()
    trainers = parse_trainers()

    # --- frequency stats -------------------------------------------------
    trainer_count = Counter()       # species -> # trainers using it
    individual_count = Counter()    # species -> total individuals across all teams
    for _name, species in rosters:
        for s in species:
            individual_count[s] += 1
        for s in set(species):
            trainer_count[s] += 1

    # --- co-occurrence edges --------------------------------------------
    edge_weight: Counter = Counter()
    pair_trainers: dict[frozenset, list[str]] = defaultdict(list)
    for name, species in rosters:
        distinct = sorted(set(species))
        for a, b in itertools.combinations(distinct, 2):
            edge_weight[frozenset((a, b))] += 1
            pair_trainers[frozenset((a, b))].append(name)

    # --- build graph -----------------------------------------------------
    G = nx.Graph()
    for s, c in trainer_count.items():
        G.add_node(
            s,
            label=names.get(s, slug_for(s).title()),
            slug=slug_for(s),
            trainers=c,
            individuals=individual_count[s],
        )
    for pair, w in edge_weight.items():
        a, b = tuple(pair)
        G.add_edge(a, b, weight=w)

    print(f"nodes={G.number_of_nodes()} edges={G.number_of_edges()} rosters={len(rosters)}")

    # --- Louvain communities --------------------------------------------
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    nx.set_node_attributes(G, partition, "community")
    modularity = community_louvain.modularity(partition, G, weight="weight")
    communities: dict[int, list[str]] = defaultdict(list)
    for node, comm in partition.items():
        communities[comm].append(node)

    # --- centralities ----------------------------------------------------
    wdeg = dict(G.degree(weight="weight"))   # weighted degree (total shared appearances)
    deg = dict(G.degree())                    # distinct partners
    betw = nx.betweenness_centrality(G, weight=None)
    try:
        eig = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        eig = {n: 0.0 for n in G}

    # species -> trainers that field it (deduped, by usage order of appearance)
    species_to_trainers: dict[str, list[str]] = defaultdict(list)
    for name, species in rosters:
        label = labels.get(name, name)
        for s in set(species):
            species_to_trainers[s].append(label)

    colors = community_palette(max(partition.values()) + 1)

    write_visualization(G, partition, names, species_to_trainers, colors, trainers)
    write_community_board(communities, names, trainer_count, individual_count, colors, trainers)
    write_report(
        G, names, labels, rosters, trainer_count, individual_count,
        edge_weight, pair_trainers, communities, modularity,
        wdeg, deg, betw, eig,
    )
    write_plots(trainer_count, names, communities)
    dump_json(G, partition)


def community_palette(n: int) -> list[str]:
    cmap = plt.get_cmap("tab20")
    return [matplotlib.colors.to_hex(cmap(i % 20)) for i in range(n)]


def write_visualization(G, partition, names, species_to_trainers, colors, trainers) -> None:
    net = Network(
        height="100vh", width="100%", bgcolor="#11151c", font_color="#e8eef5",
        notebook=False, cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120, spring_strength=0.02)
    # Skip the upfront stabilization pass so the graph appears immediately and
    # you can watch the force-directed layout settle live.
    net.options.physics.toggle_stabilization(False)
    maxt = max(d["trainers"] for _, d in G.nodes(data=True))
    for node, d in G.nodes(data=True):
        size = 18 + 42 * (d["trainers"] / maxt)
        net.add_node(
            node,
            label=d["label"],
            shape="image",
            image=SPRITE_URL.format(slug=d["slug"]),
            size=size,
            color=colors[partition[node]],
            borderWidth=3,
            title=(f"{d['label']}<br>community {partition[node]}<br>"
                   f"{d['trainers']} trainers, {d['individuals']} individuals<br>"
                   f"{G.degree(node)} distinct teammates"),
        )
    maxw = max(d["weight"] for *_e, d in G.edges(data=True))
    for a, b, d in G.edges(data=True):
        net.add_edge(a, b, value=d["weight"], width=1 + 7 * d["weight"] / maxw,
                     color="rgba(160,180,210,0.35)",
                     title=f"shares {d['weight']} rosters")
    net.toggle_physics(True)
    out = OUT / "cooccurrence_graph.html"
    net.save_graph(str(out))

    # Per-node payload for the click-to-open sidebar.
    node_info = {}
    for node, d in G.nodes(data=True):
        conns = sorted(G[node].items(), key=lambda kv: kv[1]["weight"], reverse=True)
        node_info[node] = {
            "name": d["label"],
            "slug": d["slug"],
            "color": colors[partition[node]],
            "community": int(partition[node]),
            "trainers": d["trainers"],
            "individuals": d["individuals"],
            "degree": G.degree(node),
            "wdegree": int(sum(w["weight"] for w in G[node].values())),
            "connections": [
                {"id": nb, "name": G.nodes[nb]["label"], "slug": G.nodes[nb]["slug"],
                 "weight": w["weight"]}
                for nb, w in conns
            ],
            "topTrainers": list(dict.fromkeys(species_to_trainers.get(node, [])))[:10],
        }

    # Per-community payload for the legend / isolate filter.
    comm_members: dict[int, list[str]] = defaultdict(list)
    for node in G:
        comm_members[int(partition[node])].append(node)
    comm_info = {}
    for comm, members in comm_members.items():
        members.sort(key=lambda s: G.nodes[s]["trainers"], reverse=True)
        comm_info[comm] = {
            "color": colors[comm],
            "size": len(members),
            "members": members,
            "headliners": [G.nodes[s]["label"] for s in members[:3]],
        }

    fullscreen_css = (
        "<style>html,body{margin:0;padding:0;height:100%;overflow:hidden;"
        "background:#11151c;font-family:Verdana,Geneva,sans-serif;}"
        ".card{border:none!important;width:100%!important;"
        "height:100vh!important;margin:0!important;}#mynetwork{height:100vh!important;"
        "border:none!important;}#loadingBar{display:none!important;}"
        "center{display:none!important;}"
        "#pkSidebar{position:fixed;top:0;right:0;height:100vh;width:330px;"
        "background:#171c26;color:#e8eef5;box-shadow:-4px 0 18px rgba(0,0,0,.5);"
        "transform:translateX(100%);transition:transform .25s ease;z-index:1000;"
        "overflow-y:auto;box-sizing:border-box;padding:18px;}"
        "#pkSidebar.open{transform:translateX(0);}"
        "#pkSidebar .close{position:absolute;top:10px;right:14px;cursor:pointer;"
        "font-size:22px;color:#8aa0bd;border:none;background:none;}"
        "#pkSidebar h2{margin:6px 0 2px;font-size:22px;}"
        "#pkSidebar .sub{color:#8aa0bd;font-size:12px;margin-bottom:12px;}"
        "#pkSidebar .stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0;}"
        "#pkSidebar .stat{background:#202736;border-radius:8px;padding:8px 10px;}"
        "#pkSidebar .stat b{display:block;font-size:20px;}"
        "#pkSidebar .stat span{font-size:11px;color:#8aa0bd;}"
        "#pkSidebar h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;"
        "color:#8aa0bd;margin:18px 0 6px;border-bottom:1px solid #2a3344;padding-bottom:4px;}"
        "#pkSidebar .conn{display:flex;align-items:center;gap:8px;padding:4px 6px;"
        "border-radius:6px;cursor:pointer;}"
        "#pkSidebar .conn:hover{background:#202736;}"
        "#pkSidebar .conn img{width:40px;height:30px;object-fit:contain;image-rendering:pixelated;}"
        "#pkSidebar .conn .n{flex:1;font-size:13px;}"
        "#pkSidebar .conn .w{font-size:12px;color:#7fd1ff;font-weight:bold;}"
        "#pkSidebar .tr{font-size:12px;color:#cdd8e6;padding:2px 0;}"
        "#pkHero{display:flex;align-items:center;gap:12px;}"
        "#pkHero img{width:96px;height:72px;object-fit:contain;image-rendering:pixelated;}"
        "#pkPanel{position:fixed;top:0;left:0;height:100vh;width:264px;"
        "background:rgba(23,28,38,.95);color:#e8eef5;z-index:900;display:flex;"
        "flex-direction:column;box-sizing:border-box;font-size:12px;}"
        "#pkTabs{display:flex;gap:4px;padding:8px 8px 0;}"
        "#pkTabs button{flex:1;background:#1c2330;color:#8aa0bd;border:1px solid #2a3344;"
        "border-bottom:none;border-radius:8px 8px 0 0;padding:8px;cursor:pointer;font-size:12px;}"
        "#pkTabs button.on{background:#2a3344;color:#e8eef5;}"
        "#pkPanel .pbody{flex:1;overflow-y:auto;padding:10px 12px;}"
        "#pkLegend h4{margin:2px 0 8px;font-size:13px;color:#8aa0bd;"
        "text-transform:uppercase;letter-spacing:.04em;}"
        ".lg{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:6px;cursor:pointer;}"
        ".lg:hover{background:#202736;}.lg.active{background:#2a3344;}"
        ".lg .sw{width:14px;height:14px;border-radius:3px;flex:none;}"
        ".lg .t{flex:1;}.lg .c{color:#8aa0bd;}"
        ".all{margin-bottom:8px;font-weight:bold;color:#7fd1ff;}"
        ".qbtns{display:flex;flex-direction:column;gap:6px;margin-bottom:10px;}"
        ".qbtns button{background:#223049;color:#e8eef5;border:1px solid #314056;"
        "border-radius:8px;padding:8px 10px;font-size:12px;cursor:pointer;text-align:left;"
        "display:flex;justify-content:space-between;align-items:center;}"
        ".qbtns button:hover{background:#2c3e5c;}"
        ".qbtns button b{background:#11151c;border-radius:10px;padding:1px 7px;color:#9fb4d0;}"
        ".qbtns button.clear{background:#3a2330;border-color:#56313f;}"
        "#pkTrSearch{width:100%;box-sizing:border-box;background:#11151c;color:#e8eef5;"
        "border:1px solid #314056;border-radius:8px;padding:7px 9px;margin-bottom:6px;}"
        ".trmeta{color:#8aa0bd;margin-bottom:6px;}"
        "#pkTrList{display:flex;flex-direction:column;gap:1px;}"
        ".tr{display:flex;gap:7px;align-items:center;padding:3px 5px;border-radius:6px;cursor:pointer;}"
        ".tr:hover{background:#1f2735;}.tr input{accent-color:#4c8bf5;}"
        "</style>"
    )

    # Trainer filter data for the graph (species are node ids).
    tr_graph = json.dumps([
        {"l": t["label"], "g": t["group"], "s": list(dict.fromkeys(t["species"]))}
        for t in trainers
    ])
    tr_items = "".join(
        f'<label class="tr" data-l="{t["label"].lower()}">'
        f'<input type="checkbox" value="{i}" onchange="pkTrApply()">'
        f'<span>{t["label"]}</span></label>'
        for i, t in enumerate(trainers)
    )
    g_counts = Counter(t["group"] for t in trainers)

    panel_html = (
        '<div id="pkPanel">'
        '<div id="pkTabs">'
        '<button id="tabLegend" class="on" onclick="pkTab(\'legend\')">Communities</button>'
        '<button id="tabTr" onclick="pkTab(\'trainers\')">Trainers</button></div>'
        '<div class="pbody">'
        '<div id="pkLegend"></div>'
        '<div id="pkTrainers" style="display:none">'
        '<div class="qbtns">'
        f'<button onclick="pkTrGroup(\'leaders\')">Gym Leaders <b>{g_counts["leaders"]}</b></button>'
        f'<button onclick="pkTrGroup(\'e4\')">Elite Four + Champion <b>{g_counts["e4"]}</b></button>'
        f'<button onclick="pkTrGroup(\'magma\')">Team Magma <b>{g_counts["magma"]}</b></button>'
        f'<button onclick="pkTrGroup(\'aqua\')">Team Aqua <b>{g_counts["aqua"]}</b></button>'
        '<button class="clear" onclick="pkTrGroup(\'none\')">Clear / show all</button>'
        '</div>'
        '<input id="pkTrSearch" placeholder="Filter trainers\u2026" oninput="pkTrFilter()">'
        '<div class="trmeta"><span id="pkTrCount">0 selected</span></div>'
        f'<div id="pkTrList">{tr_items}</div>'
        '</div></div></div>'
    )

    sidebar_html = (
        '<div id="pkSidebar">'
        '<button class="close" onclick="document.getElementById(\'pkSidebar\').'
        'classList.remove(\'open\')">&times;</button>'
        '<div id="pkBody"></div></div>'
        + panel_html +
        '<script>const POKE_INFO=' + json.dumps(node_info) + ';</script>'
        '<script>const COMM_INFO=' + json.dumps(comm_info) + ';</script>'
        '<script>const TR_GRAPH=' + tr_graph + ';</script>'
        '<script>' + _SIDEBAR_JS + '</script>'
        '<script>' + _LEGEND_JS + '</script>'
        '<script>' + _TRAINER_GRAPH_JS + '</script>'
    )

    html = out.read_text().replace("</head>", fullscreen_css + "</head>", 1)
    html = html.replace("</body>", sidebar_html + "</body>", 1)
    out.write_text(html)
    print("wrote", out)


def write_community_board(communities, names, trainer_count, individual_count, colors, trainers) -> None:
    maxt = max(trainer_count.values())
    ordered = sorted(communities.items(), key=lambda kv: len(kv[1]), reverse=True)
    cards = []
    for comm, members in ordered:
        members = sorted(members, key=lambda s: trainer_count[s], reverse=True)
        color = colors[comm]
        total_tr = sum(trainer_count[s] for s in members)
        headliners = ", ".join(names.get(s, s) for s in members[:3])
        chips = []
        for s in members:
            slug = slug_for(s)
            t = trainer_count[s]
            size = 56 + int(64 * (t / maxt))
            chips.append(
                f'<figure class="chip" title="{names.get(s, s)} — {t} trainers, '
                f'{individual_count[s]} individuals">'
                f'<img src="{SPRITE_URL.format(slug=slug)}" style="width:{size}px;height:{int(size*0.75)}px">'
                f'<figcaption>{names.get(s, s)}</figcaption></figure>'
            )
        cards.append(
            f'<section class="cluster" style="--c:{color}">'
            f'<header><span class="dot"></span>'
            f'<div><h2>Cluster {comm}</h2>'
            f'<div class="meta">{len(members)} species · {total_tr} total trainer slots</div>'
            f'<div class="head">{headliners}</div></div></header>'
            f'<div class="chips">{"".join(chips)}</div></section>'
        )

    # --- trainer browser data -------------------------------------------
    tr_payload = json.dumps([
        {"l": t["label"], "g": t["group"],
         "s": [[slug_for(s), names.get(s, s)] for s in t["species"]]}
        for t in trainers
    ])
    tr_items = "".join(
        f'<label class="tr" data-g="{t["group"]}" data-l="{t["label"].lower()}">'
        f'<input type="checkbox" value="{i}" onchange="trRender()">'
        f'<span>{t["label"]}</span></label>'
        for i, t in enumerate(trainers)
    )
    n_leaders = sum(1 for t in trainers if t["group"] == "leaders")
    n_e4 = sum(1 for t in trainers if t["group"] == "e4")
    n_magma = sum(1 for t in trainers if t["group"] == "magma")
    n_aqua = sum(1 for t in trainers if t["group"] == "aqua")

    tjs = (
        "var SP='" + _SPRITE_JS + "';\n"
        "function trRender(){\n"
        "  var box=document.getElementById('trOut');var checked=[];\n"
        "  document.querySelectorAll('#trList input:checked').forEach(function(c){checked.push(+c.value);});\n"
        "  document.getElementById('trCount').textContent=checked.length+' selected';\n"
        "  if(!checked.length){box.innerHTML='<div class=\"empty\">Tick trainers on the left \u2014 or hit a quick group \u2014 to show their Pok\u00e9mon.</div>';return;}\n"
        "  var h='';\n"
        "  checked.forEach(function(i){var t=TR[i];\n"
        "    h+='<section class=\"tcard\"><h3>'+t.l+' <small>'+t.s.length+'</small></h3><div class=\"trow\">';\n"
        "    t.s.forEach(function(p){h+='<figure class=\"chip\"><img src=\"'+SP+p[0]+'.png\"><figcaption>'+p[1]+'</figcaption></figure>';});\n"
        "    h+='</div></section>';});\n"
        "  box.innerHTML=h;\n"
        "}\n"
        "function trGroup(g){\n"
        "  document.querySelectorAll('#trList input').forEach(function(c){\n"
        "    if(g==='all'){c.checked=true;}else if(g==='none'){c.checked=false;}\n"
        "    else{c.checked=(TR[+c.value].g===g);}\n"
        "  });\n"
        "  trRender();\n"
        "}\n"
        "function trFilter(){var q=document.getElementById('trSearch').value.toLowerCase();\n"
        "  document.querySelectorAll('#trList .tr').forEach(function(e){\n"
        "    e.style.display=(!q||e.dataset.l.indexOf(q)>=0)?'':'none';});\n"
        "}\n"
        "trRender();\n"
    )

    browser = (
        '<h1 style="margin-top:40px">Trainer browser</h1>'
        '<div class="sub">Pick one or more trainers to see exactly which Pok\u00e9mon they field. '
        'Use the quick buttons to load a whole roster group.</div>'
        '<div class="tbrowse">'
        '<div class="tpanel">'
        '<div class="qbtns">'
        f'<button onclick="trGroup(\'leaders\')">Gym Leaders <b>{n_leaders}</b></button>'
        f'<button onclick="trGroup(\'e4\')">Elite Four + Champion <b>{n_e4}</b></button>'
        f'<button onclick="trGroup(\'magma\')">Team Magma <b>{n_magma}</b></button>'
        f'<button onclick="trGroup(\'aqua\')">Team Aqua <b>{n_aqua}</b></button>'
        '<button class="clear" onclick="trGroup(\'none\')">Clear</button>'
        '</div>'
        '<input id="trSearch" placeholder="Filter trainers\u2026" oninput="trFilter()">'
        f'<div id="trList">{tr_items}</div>'
        '</div>'
        '<div class="tresult"><div class="rhead"><span id="trCount">0 selected</span></div>'
        '<div id="trOut"></div></div>'
        '</div>'
        f'<script>var TR={tr_payload};</script><script>{tjs}</script>'
    )

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Trainer Pokemon communities</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#11151c;color:#e8eef5;font-family:Verdana,Geneva,sans-serif;padding:24px}}
h1{{margin:0 0 4px}} .sub{{color:#8aa0bd;margin-bottom:22px;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:18px;align-items:start}}
.cluster{{background:#171c26;border-radius:12px;overflow:hidden;border:1px solid #232c3b;
  border-top:4px solid var(--c)}}
.cluster header{{display:flex;gap:12px;align-items:flex-start;padding:14px 16px 8px}}
.cluster .dot{{width:16px;height:16px;border-radius:50%;background:var(--c);margin-top:4px;flex:none}}
.cluster h2{{margin:0;font-size:18px}}
.cluster .meta{{color:#8aa0bd;font-size:12px}}
.cluster .head{{color:#cdd8e6;font-size:13px;margin-top:4px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;padding:6px 14px 16px}}
.chip{{margin:0;display:flex;flex-direction:column;align-items:center;width:124px}}
.chip img{{object-fit:contain;image-rendering:pixelated;width:96px;height:72px}}
.chip figcaption{{font-size:10px;color:#aab6c6;text-align:center;line-height:1.1;margin-top:2px}}
.tbrowse{{display:grid;grid-template-columns:320px 1fr;gap:18px;align-items:start}}
.tpanel{{background:#171c26;border:1px solid #232c3b;border-radius:12px;padding:14px;position:sticky;top:16px}}
.qbtns{{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}}
.qbtns button{{background:#223049;color:#e8eef5;border:1px solid #314056;border-radius:8px;
  padding:9px 12px;font-size:13px;cursor:pointer;text-align:left;
  display:flex;justify-content:space-between;align-items:center}}
.qbtns button:hover{{background:#2c3e5c}}
.qbtns button b{{background:#11151c;border-radius:10px;padding:1px 8px;font-size:11px;color:#9fb4d0}}
.qbtns button.clear{{background:#3a2330;border-color:#56313f}}
#trSearch{{width:100%;box-sizing:border-box;background:#11151c;color:#e8eef5;border:1px solid #314056;
  border-radius:8px;padding:8px 10px;margin-bottom:10px}}
#trList{{max-height:62vh;overflow:auto;display:flex;flex-direction:column;gap:2px}}
.tr{{display:flex;gap:8px;align-items:center;font-size:12px;padding:3px 6px;border-radius:6px;cursor:pointer}}
.tr:hover{{background:#1f2735}} .tr input{{accent-color:#4c8bf5}}
.tresult .rhead{{color:#8aa0bd;font-size:12px;margin-bottom:8px}}
.tcard{{background:#171c26;border:1px solid #232c3b;border-radius:10px;padding:10px 12px;margin-bottom:12px}}
.tcard h3{{margin:0 0 8px;font-size:15px}} .tcard h3 small{{color:#8aa0bd;font-weight:normal}}
.trow{{display:flex;flex-wrap:wrap;gap:6px}}
.empty{{color:#7e93b0;font-size:13px;padding:30px;text-align:center;border:1px dashed #2a3647;border-radius:10px}}
</style></head><body>
<h1>Trainer-roster Pokémon communities</h1>
<div class="sub">{len(ordered)} Louvain communities. Sprite size ∝ how many trainers field that species. Sorted by community size.</div>
<div class="grid">{"".join(cards)}</div>
{browser}
</body></html>"""
    out = OUT / "communities.html"
    out.write_text(html)
    print("wrote", out)


def write_plots(trainer_count, names, communities) -> None:
    # Top species by trainer count.
    top = trainer_count.most_common(25)
    fig, ax = plt.subplots(figsize=(10, 8))
    labels = [names.get(s, s) for s, _ in top][::-1]
    vals = [c for _, c in top][::-1]
    ax.barh(labels, vals, color="#4c8bf5")
    ax.set_title("Top 25 Pokemon by number of trainers fielding them")
    ax.set_xlabel("# trainers")
    fig.tight_layout()
    fig.savefig(OUT / "top_species.png", dpi=110)
    plt.close(fig)

    # Community sizes.
    sizes = sorted((len(v) for v in communities.values()), reverse=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(range(len(sizes)), sizes, color="#f5a04c")
    ax.set_title("Louvain community sizes")
    ax.set_xlabel("community rank")
    ax.set_ylabel("# species")
    fig.tight_layout()
    fig.savefig(OUT / "community_sizes.png", dpi=110)
    plt.close(fig)
    print("wrote top_species.png, community_sizes.png")


def dump_json(G, partition) -> None:
    data = {
        "nodes": [
            {"id": n, **{k: v for k, v in d.items()}} for n, d in G.nodes(data=True)
        ],
        "edges": [
            {"source": a, "target": b, "weight": d["weight"]}
            for a, b, d in G.edges(data=True)
        ],
    }
    (OUT / "graph_data.json").write_text(json.dumps(data, indent=2))
    print("wrote graph_data.json")


def _table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def write_report(G, names, labels, rosters, trainer_count, individual_count,
                 edge_weight, pair_trainers, communities, modularity,
                 wdeg, deg, betw, eig) -> None:
    nm = lambda s: names.get(s, s)
    L = []
    L.append("# Trainer-roster Pokemon co-occurrence analysis\n")
    L.append(f"Source: `randomizer/trainer_parties.h` (canonical, non-randomized rosters).\n")
    L.append(f"- **{len(rosters)}** trainer rosters parsed")
    L.append(f"- **{G.number_of_nodes()}** distinct species fielded by trainers")
    L.append(f"- **{G.number_of_edges()}** co-occurrence edges "
             f"(species pairs that share at least one roster)")
    L.append(f"- Graph density **{nx.density(G):.3f}**, "
             f"Louvain modularity **{modularity:.3f}**, "
             f"**{len(communities)}** communities\n")

    L.append("## Most-used Pokemon (by number of trainers)\n")
    rows = [(i + 1, nm(s), c, individual_count[s], G.degree(s))
            for i, (s, c) in enumerate(trainer_count.most_common(20))]
    L.append(_table(["#", "Pokemon", "Trainers", "Individuals", "Distinct teammates"], rows))
    L.append("")

    L.append("## Most-used Pokemon (by total individuals across all teams)\n")
    rows = [(i + 1, nm(s), c, trainer_count[s])
            for i, (s, c) in enumerate(individual_count.most_common(20))]
    L.append(_table(["#", "Pokemon", "Individuals", "Trainers"], rows))
    L.append("")

    L.append("## Strongest pairings (species that share the most rosters)\n")
    L.append("These are the iconic duos a trainer is most likely to field together.\n")
    top_edges = sorted(edge_weight.items(), key=lambda kv: kv[1], reverse=True)[:25]
    rows = []
    for i, (pair, w) in enumerate(top_edges):
        a, b = tuple(pair)
        example = labels.get(pair_trainers[pair][0], pair_trainers[pair][0])
        rows.append((i + 1, f"{nm(a)} + {nm(b)}", w, example))
    L.append(_table(["#", "Pair", "Shared rosters", "e.g. trainer"], rows))
    L.append("")

    L.append("## Most connected Pokemon (weighted degree)\n")
    L.append("Weighted degree = total co-appearances with all teammates; the social "
             "'hubs' of the trainer metagame.\n")
    rows = [(i + 1, nm(s), int(w), deg[s])
            for i, (s, w) in enumerate(sorted(wdeg.items(), key=lambda kv: kv[1], reverse=True)[:15])]
    L.append(_table(["#", "Pokemon", "Weighted degree", "Distinct teammates"], rows))
    L.append("")

    L.append("## Bridge Pokemon (betweenness centrality)\n")
    L.append("High betweenness = species that link otherwise-separate groups; remove "
             "them and the metagame fragments.\n")
    rows = [(i + 1, nm(s), f"{b:.3f}")
            for i, (s, b) in enumerate(sorted(betw.items(), key=lambda kv: kv[1], reverse=True)[:15])]
    L.append(_table(["#", "Pokemon", "Betweenness"], rows))
    L.append("")

    L.append("## Most central Pokemon (eigenvector centrality)\n")
    L.append("High eigenvector centrality = teammates of other well-connected species; "
             "the 'in crowd'.\n")
    rows = [(i + 1, nm(s), f"{e:.3f}")
            for i, (s, e) in enumerate(sorted(eig.items(), key=lambda kv: kv[1], reverse=True)[:15])]
    L.append(_table(["#", "Pokemon", "Eigenvector"], rows))
    L.append("")

    L.append("## Louvain communities\n")
    L.append("Clusters of Pokemon that tend to be fielded together. Each is summarised "
             "by its most-used members.\n")
    ordered = sorted(communities.items(), key=lambda kv: len(kv[1]), reverse=True)
    for comm, members in ordered:
        members_sorted = sorted(members, key=lambda s: trainer_count[s], reverse=True)
        head = ", ".join(nm(s) for s in members_sorted[:12])
        more = f" (+{len(members) - 12} more)" if len(members) > 12 else ""
        L.append(f"**Cluster {comm}** — {len(members)} species: {head}{more}")
        L.append("")

    (OUT / "trainer_pokemon_analysis.md").write_text("\n".join(L))
    print("wrote trainer_pokemon_analysis.md")


if __name__ == "__main__":
    main()
