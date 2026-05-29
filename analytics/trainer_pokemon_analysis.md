# Trainer-roster Pokemon co-occurrence analysis

Source: `randomizer/trainer_parties.h` (canonical, non-randomized rosters).

- **854** trainer rosters parsed
- **208** distinct species fielded by trainers
- **759** co-occurrence edges (species pairs that share at least one roster)
- Graph density **0.035**, Louvain modularity **0.583**, **26** communities

## Most-used Pokemon (by number of trainers)

| # | Pokemon | Trainers | Individuals | Distinct teammates |
| --- | --- | --- | --- | --- |
| 1 | Pelipper | 39 | 39 | 37 |
| 2 | Roselia | 39 | 40 | 22 |
| 3 | Wingull | 38 | 38 | 26 |
| 4 | Numel | 35 | 36 | 21 |
| 5 | Hariyama | 31 | 31 | 16 |
| 6 | Linoone | 31 | 31 | 21 |
| 7 | Carvanha | 30 | 31 | 12 |
| 8 | Marill | 30 | 33 | 18 |
| 9 | Wailmer | 29 | 30 | 20 |
| 10 | Mightyena | 28 | 29 | 27 |
| 11 | Tentacool | 28 | 33 | 12 |
| 12 | Lombre | 27 | 27 | 20 |
| 13 | Manectric | 26 | 30 | 22 |
| 14 | Shroomish | 26 | 26 | 20 |
| 15 | Swellow | 25 | 25 | 26 |
| 16 | Makuhita | 24 | 24 | 18 |
| 17 | Zubat | 23 | 23 | 7 |
| 18 | Zigzagoon | 23 | 24 | 15 |
| 19 | Machoke | 23 | 28 | 11 |
| 20 | Meditite | 23 | 24 | 9 |

## Most-used Pokemon (by total individuals across all teams)

| # | Pokemon | Individuals | Trainers |
| --- | --- | --- | --- |
| 1 | Roselia | 40 | 39 |
| 2 | Pelipper | 39 | 39 |
| 3 | Wingull | 38 | 38 |
| 4 | Numel | 36 | 35 |
| 5 | Marill | 33 | 30 |
| 6 | Tentacool | 33 | 28 |
| 7 | Carvanha | 31 | 30 |
| 8 | Hariyama | 31 | 31 |
| 9 | Linoone | 31 | 31 |
| 10 | Manectric | 30 | 26 |
| 11 | Wailmer | 30 | 29 |
| 12 | Mightyena | 29 | 28 |
| 13 | Machoke | 28 | 23 |
| 14 | Geodude | 27 | 17 |
| 15 | Lombre | 27 | 27 |
| 16 | Shroomish | 26 | 26 |
| 17 | Swellow | 25 | 25 |
| 18 | Staryu | 25 | 20 |
| 19 | Altaria | 25 | 20 |
| 20 | Koffing | 25 | 11 |

## Strongest pairings (species that share the most rosters)

These are the iconic duos a trainer is most likely to field together.

| # | Pair | Shared rosters | e.g. trainer |
| --- | --- | --- | --- |
| 1 | Hariyama + Medicham | 13 | Expert SHELBY |
| 2 | Plusle + Minun | 12 | Pokefan ISABEL |
| 3 | Swellow + Linoone | 11 | Camper ETHAN |
| 4 | Pelipper + Tropius | 9 | Leader WINONA |
| 5 | Swellow + Mightyena | 9 | Youngster CALVIN |
| 6 | Mightyena + Linoone | 9 | Youngster CALVIN |
| 7 | Shroomish + Roselia | 8 | Aroma Lady DAISY |
| 8 | Gloom + Roselia | 8 | Aroma Lady VIOLET |
| 9 | Meditite + Makuhita | 8 | Leader BRAWLY |
| 10 | Nuzleaf + Lombre | 8 | Collector EDWIN |
| 11 | Roselia + Delcatty | 8 | Rival WALLY |
| 12 | Taillow + Zigzagoon | 7 | Pkmn Breeder GABRIELLE |
| 13 | Pelipper + Roselia | 7 | Cooltrainer WENDY |
| 14 | Wingull + Tentacool | 7 | Swimmer M DARRIN |
| 15 | Spinda + Slaking | 7 | Leader NORMAN |
| 16 | Volbeat + Illumise | 7 | Bug Catcher GREG |
| 17 | Poochyena + Zubat | 6 | Team Aqua GRUNT |
| 18 | Machoke + Machop | 6 | Black Belt HITOSHI |
| 19 | Skarmory + Tropius | 6 | Leader WINONA |
| 20 | Solrock + Lunatone | 6 | Leader TATE&LIZA |
| 21 | Shroomish + Marill | 6 | Picnicker IRENE |
| 22 | Slugma + Grovyle | 6 | Rival BRENDAN |
| 23 | Slugma + Marshtomp | 6 | Rival BRENDAN |
| 24 | Roselia + Numel | 5 | Cooltrainer BROOKE |
| 25 | Kecleon + Seviper | 5 | Beauty JESSICA |

## Most connected Pokemon (weighted degree)

Weighted degree = total co-appearances with all teammates; the social 'hubs' of the trainer metagame.

| # | Pokemon | Weighted degree | Distinct teammates |
| --- | --- | --- | --- |
| 1 | Pelipper | 91 | 37 |
| 2 | Roselia | 79 | 22 |
| 3 | Mightyena | 67 | 27 |
| 4 | Wingull | 60 | 26 |
| 5 | Swellow | 57 | 26 |
| 6 | Linoone | 54 | 21 |
| 7 | Altaria | 54 | 22 |
| 8 | Tropius | 52 | 23 |
| 9 | Magneton | 50 | 21 |
| 10 | Lombre | 48 | 20 |
| 11 | Hariyama | 47 | 16 |
| 12 | Delcatty | 47 | 19 |
| 13 | Shroomish | 40 | 20 |
| 14 | Loudred | 40 | 16 |
| 15 | Marill | 40 | 18 |

## Bridge Pokemon (betweenness centrality)

High betweenness = species that link otherwise-separate groups; remove them and the metagame fragments.

| # | Pokemon | Betweenness |
| --- | --- | --- |
| 1 | Pelipper | 0.100 |
| 2 | Shroomish | 0.084 |
| 3 | Altaria | 0.068 |
| 4 | Mightyena | 0.064 |
| 5 | Swellow | 0.062 |
| 6 | Roselia | 0.051 |
| 7 | Skarmory | 0.049 |
| 8 | Beautifly | 0.049 |
| 9 | Camerupt | 0.047 |
| 10 | Linoone | 0.046 |
| 11 | Magneton | 0.046 |
| 12 | Shiftry | 0.044 |
| 13 | Xatu | 0.044 |
| 14 | Nosepass | 0.041 |
| 15 | Loudred | 0.040 |

## Most central Pokemon (eigenvector centrality)

High eigenvector centrality = teammates of other well-connected species; the 'in crowd'.

| # | Pokemon | Eigenvector |
| --- | --- | --- |
| 1 | Roselia | 0.356 |
| 2 | Pelipper | 0.330 |
| 3 | Delcatty | 0.253 |
| 4 | Altaria | 0.229 |
| 5 | Swellow | 0.208 |
| 6 | Mightyena | 0.203 |
| 7 | Tropius | 0.200 |
| 8 | Linoone | 0.195 |
| 9 | Wingull | 0.191 |
| 10 | Magneton | 0.175 |
| 11 | Marill | 0.167 |
| 12 | Lombre | 0.164 |
| 13 | Shroomish | 0.164 |
| 14 | Numel | 0.153 |
| 15 | Breloom | 0.150 |

## Louvain communities

Clusters of Pokemon that tend to be fielded together. Each is summarised by its most-used members.

**Cluster 20** — 21 species: Kadabra, Xatu, Lunatone, Solrock, Claydol, Kirlia, Ralts, Natu, Banette, Wobbuffet, Mawile, Slowpoke (+9 more)

**Cluster 2** — 20 species: Wingull, Carvanha, Wailmer, Tentacool, Machoke, Machop, Staryu, Sharpedo, Tentacruel, Gyarados, Starmie, Magikarp (+8 more)

**Cluster 9** — 20 species: Hariyama, Linoone, Mightyena, Swellow, Loudred, Medicham, Aron, Shiftry, Machamp, Vigoroth, Lairon, Hitmontop (+8 more)

**Cluster 6** — 20 species: Pelipper, Lombre, Slugma, Altaria, Tropius, Skarmory, Nuzleaf, Doduo, Ludicolo, Grovyle, Combusken, Marshtomp (+8 more)

**Cluster 0** — 18 species: Geodude, Sandshrew, Sandslash, Baltoy, Kecleon, Graveler, Nosepass, Seviper, Golem, Zangoose, Onix, Kabutops (+6 more)

**Cluster 3** — 17 species: Roselia, Numel, Marill, Shroomish, Breloom, Goldeen, Delcatty, Gloom, Skitty, Swablu, Azumarill, Seaking (+5 more)

**Cluster 24** — 16 species: Luvdisc, Whiscash, Kingdra, Crawdaunt, Walrein, Wailord, Sealeo, Shelgon, Poliwhirl, Lapras, Glalie, Flygon (+4 more)

**Cluster 12** — 14 species: Makuhita, Zubat, Zigzagoon, Meditite, Poochyena, Magnemite, Electrike, Taillow, Lotad, Voltorb, Seedot, Whismur (+2 more)

**Cluster 5** — 13 species: Manectric, Magneton, Dodrio, Exploud, Electrode, Pikachu, Raichu, Ampharos, Muk, Golduck, Mareep, Flaaffy (+1 more)

**Cluster 10** — 12 species: Spinda, Sableye, Slaking, Spoink, Duskull, Shuppet, Kangaskhan, Dusclops, Chansey, Blissey, Grumpig, Tauros

**Cluster 21** — 11 species: Ninjask, Koffing, Dustox, Surskit, Beautifly, Wurmple, Nincada, Masquerain, Silcoon, Cascoon, Weezing

**Cluster 17** — 10 species: Camerupt, Torkoal, Magcargo, Mudkip, Ponyta, Growlithe, Rapidash, Houndour, Arcanine, Houndoom

**Cluster 11** — 2 species: Plusle, Minun

**Cluster 18** — 2 species: Illumise, Volbeat

**Cluster 14** — 1 species: Slakoth

**Cluster 16** — 1 species: Wigglytuff

**Cluster 22** — 1 species: Abra

**Cluster 23** — 1 species: Girafarig

**Cluster 13** — 1 species: Castform

**Cluster 15** — 1 species: Pinsir

**Cluster 19** — 1 species: Beldum

**Cluster 25** — 1 species: Chimecho

**Cluster 1** — 1 species: Charmander

**Cluster 4** — 1 species: Bulbasaur

**Cluster 7** — 1 species: Groudon

**Cluster 8** — 1 species: Kyogre
