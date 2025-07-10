import pokebase as pb
from pokebase import type_

ATTR_QUERY_KEYS = {
    "have the type": (type_, ['normal', 'fighting', 'flying', 'poison', 'ground', 'rock',
        'bug', 'ghost', 'steel', 'fire', 'water', 'grass',
        'electric', 'psychic', 'ice', 'dragon', 'dark', 'fairy',
        'unknown', 'shadow']),
    "lives in habitat": (pb.pokemon_habitat, ['cave', 'forest', 'grassland', 'mountain', 'rare',
        'rough-terrain', 'sea', 'urban', 'waters-edge']),
    "have color": (pb.pokemon_color, ['black', 'blue', 'brown', 'gray', 'green', 'pink',
        'purple', 'red', 'white', 'yellow']),
    "belong to egg group": (pb.egg_group, ['monster', 'water1', 'bug', 'flying', 'field',
        'fairy', 'grass', 'human-like', 'water3', 'mineral',
        'amorphous', 'water2', 'ditto', 'dragon', 'undiscovered']),
    "have shape": (pb.pokemon_shape, ['ball', 'squiggle', 'fish', 'arms', 'blob', 'upright',
        'legs', 'quadruped', 'wings', 'tentacles',
        'heads', 'humanoid', 'bug-wings', 'armor']),
    "with growth rate": (pb.growth_rate, ['slow', 'medium', 'fast', 'medium-slow', 'slow-then-very-fast', 'fast-then-very-slow']),
    "have the ability": (pb.ability, ['levitate', 'blaze', 'torrent', 'overgrow', 'pressure',
        'intimidate', 'static', 'inner-focus', 'synchronize',
        'poison-point', 'chlorophyll', 'huge-power']),
    "learn the move": (pb.move, ['tackle', 'ember', 'water-gun', 'psychic', 'thunderbolt',
        'earthquake', 'ice-beam', 'protect', 'rest'])
}

class QueryTool:
    def __init__(self):
        pass
    def all_keys(self):
        return [r.name for r in self.query_func("").results]    

class PokemonAttributeQuery(QueryTool):
    def __init__(self, attr, keys=[]):
        self.query_func = ATTR_QUERY_KEYS[attr][0]
        self.keys = keys

    def find_pokemon(self):            
        return {key: [value.name for value in self.query_func(key).pokemon_species] for key in self.keys}
    
class PokemonTypeQuery(PokemonAttributeQuery):
    def __init__(self, keys=[]):
        self.query_func = type_
        super().__init__("have the type", keys)
    def find_pokemon(self):
        return {key: [value.pokemon.name for value in type_(key).pokemon] for key in self.keys}
    
    @staticmethod
    def _dr_info(damage_relations):
        return {drk: [drv.name for drv in drvs] for drk, drvs in damage_relations.__dict__.items()}
        
    def damage_relations(self):
        return {key: PokemonTypeQuery._dr_info(type_(key).damage_relations) for key in self.keys}
    def game_indices(self):
        return {key: [{"game_index": gi.game_index, "generation": gi.generation.name} for gi in type_(key).game_indices] for key in self.keys}
    def generation(self):
        return {key: type_(key).generation.name for key in self.keys}
    def find_moves(self):
        return {key: [value.name for value in type_(key).moves] for key in self.keys}
    def move_damage_class(self):
        return {key: type_(key).move_damage_class.name for key in self.keys}
    def past_damage_relations(self):
        return {key: [{"damage_relations": PokemonTypeQuery._dr_info(pdr.damage_relations), "generation": pdr.generation.name} for pdr in type_(key).past_damage_relations] for key in self.keys}

class MoveQuery(PokemonAttributeQuery):
    def __init__(self, keys=[]):
        self.query_func = pb.move
        super().__init__("learn the move", keys)
    def find_pokemon(self):
        return {key: [value.name for value in pb.move(key).learned_by_pokemon] for key in self.keys}
        
if __name__ == "__main__":
    # print(pokemon_and_query([("type", ["grass"]), ("move", ["tackle"])]))
    # print(pokemon_single_query("learn the move", ["tackle"]))
    # print(pb.pokemon_habitat("").results)
    # pqr = MoveQuery(["tackle"])
    pqr = PokemonTypeQuery(["fire"])
    print(pqr.past_damage_relations())
