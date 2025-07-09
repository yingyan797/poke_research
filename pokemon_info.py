import pokebase as pb

ATTR_QUERY_KEYS = {
    pb.type_: ['normal', 'fighting', 'flying', 'poison', 'ground', 'rock',
        'bug', 'ghost', 'steel', 'fire', 'water', 'grass',
        'electric', 'psychic', 'ice', 'dragon', 'dark', 'fairy',
        'unknown', 'shadow'],
    pb.pokemon_habitat: ['cave', 'forest', 'grassland', 'mountain', 'rare',
        'rough-terrain', 'sea', 'urban', 'waters-edge'],
    pb.pokemon_color: ['black', 'blue', 'brown', 'gray', 'green', 'pink',
        'purple', 'red', 'white', 'yellow'],
    pb.egg_group: ['monster', 'water1', 'bug', 'flying', 'field',
        'fairy', 'grass', 'human-like', 'water3', 'mineral',
        'amorphous', 'water2', 'ditto', 'dragon', 'undiscovered'],
    pb.pokemon_shape: ['ball', 'squiggle', 'fish', 'arms', 'blob', 'upright',
        'legs', 'quadruped', 'wings', 'tentacles',
        'heads', 'humanoid', 'bug-wings', 'armor'],
    pb.growth_rate: ['slow', 'medium', 'fast', 'medium-slow', 'slow-then-very-fast', 'fast-then-very-slow']
}

def pokemon_single_query(query_func, keys):
    values = set()
    for k in keys:
        names = [p.pokemon.name for p in query_func(k).pokemon] if query_func is pb.type_ else [p.name for p in query_func(k).pokemon_species]
        values = values.union(names)
    return values

def pokemon_cross_query(query_list):
    values = None
    for query_func, keys in query_list:
        if values is not None:
            values = values.intersection(pokemon_single_query(query_func, keys))
        else:
            values = pokemon_single_query(query_func, keys)
    return values
        
if __name__ == "__main__":
    print(pokemon_cross_query([(pb.pokemon_shape, ["ball"]), (pb.type_, ["grass"])]))
    # print(pokemon_single_query(pb.type_, ["water"]))
