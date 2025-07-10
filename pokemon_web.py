import requests, json
import pokebase as pb
from pokebase import loaders

# print(pb.__dict__.keys())

# with open("resource.json", "w") as f:
#     json.dump(requests.get(pb.pokemon_shape("ball").url).json(), f)
# with open("resource.json", "r") as f:
#     print(json.load(f)["moves"])