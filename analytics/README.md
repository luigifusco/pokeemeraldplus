# Trainer-roster Pokémon co-occurrence analytics

Builds an undirected weighted graph of every Pokémon that appears on a trainer's
team, with edge weight = number of trainers whose roster contains **both**
species, then runs Louvain community detection and several network analyses.

## Regenerate

```bash
pip install --break-system-packages networkx python-louvain pyvis matplotlib
python3 analytics/build_graph.py
```

Rosters are read from `randomizer/trainer_parties.h` (the canonical,
non-randomized teams). Sprites are pulled from the Pokémon Showdown CDN
(`gen5`) and embedded inline, so the HTML works offline once generated.

## Outputs

- `cooccurrence_graph.html` — interactive graph (open in a browser). Node = a
  species with its sprite + name; node size = how many trainers field it; node
  colour = Louvain community; edge width = shared-roster count. Hover for stats.
- `trainer_pokemon_analysis.md` — full report: usage rankings, strongest
  pairings, weighted-degree hubs, bridge (betweenness) and central (eigenvector)
  Pokémon, and the Louvain community breakdown.
- `top_species.png`, `community_sizes.png` — static charts.
- `graph_data.json` — raw nodes/edges for any further analysis.
