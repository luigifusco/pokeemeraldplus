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


def main() -> None:
    names = load_species_names()
    rosters = parse_rosters()
    labels = parse_trainer_labels()

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

    write_visualization(G, partition, names)
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


def write_visualization(G, partition, names) -> None:
    ncomm = max(partition.values()) + 1
    colors = community_palette(ncomm)
    net = Network(
        height="100vh", width="100%", bgcolor="#11151c", font_color="#e8eef5",
        notebook=False, cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120, spring_strength=0.02)
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
    # Make the canvas truly fullscreen: drop default margins, the bootstrap card
    # border, and the empty header pyvis injects so #mynetwork fills the viewport.
    fullscreen_css = (
        "<style>html,body{margin:0;padding:0;height:100%;overflow:hidden;"
        "background:#11151c;}.card{border:none!important;width:100%!important;"
        "height:100vh!important;margin:0!important;}#mynetwork{height:100vh!important;"
        "border:none!important;}#loadingBar{height:100vh!important;}"
        "center{display:none!important;}</style>"
    )
    html = out.read_text().replace("</head>", fullscreen_css + "</head>", 1)
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
