# open species.txt and read all pokemon

with open('randomizer/species.txt', 'r') as f:
    species = [line.strip() for line in f.readlines()]

with open('randomizer/wild_encounters.json', 'r') as f:
    encounters = f.read()

# replace all pokemon species in encounters with random species
import random

# for all patterns like "SPECIES_<POKEMON>" in encounters, replace with random species
# first find all patterns in encounters, then for each pattern, replace with random species from species list
import re
patterns = re.findall(r'SPECIES_[A-Z_]+', encounters)
unique_patterns = set(patterns)
for pattern in unique_patterns:
    random_species = random.choice(species)
    encounters = encounters.replace(pattern, random_species)

with open('src/data/wild_encounters.json', 'w') as f:
    f.write(encounters)