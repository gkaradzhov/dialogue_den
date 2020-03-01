import random
import uuid

ANIMALS = {"Cat", "Guinea pig", "Alpaca", "Bat", "Beaver", "Bee", "Chipmunk", "Dolphin", "Duck", "Falcon", "Kiwi",
           "Lobster", "Ox", "Leopard", "Zebra", "Llama", "Narwhal", 'Lion', 'Tiger', "Hedgehog", "Giraffe"}
# COLOURS = {"Red", "Orange", "Purple", "Yellow", "Green", "Blue", "Pink", "Cyan", "Black", "White"}


def generate_user(exclude_list, is_moderator=False):
    if is_moderator:
        user_name = "Moderating Owl"
    else:
        exclude_animals = set([a for a in exclude_list])
        animals = list(ANIMALS.difference(exclude_animals))
        user_name = "{}".format(random.choice(animals))
    return {'user_name': user_name, 'user_id': uuid.uuid4().hex}


def generate_wason_cards():
    even_numbers = [2, 4, 6, 8]
    odd_numbers = [1, 3, 5, 7, 9]
    vowels = ['A', 'I', 'E', 'U']
    consonants = ['B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'X', 'Z']
    cards_array = [random.choice(even_numbers), random.choice(odd_numbers), random.choice(consonants),
                   random.choice(vowels)]
    random.shuffle(cards_array)
    cards_obj = [{'value': str(a), 'checked': False} for a in cards_array]
    return cards_obj


