import csv
import os
import uuid

from message import Room
import random

ANIMALS = {"Cat", "Guinea pig", "Alpaca", "Bat", "Beaver", "Bee", "Chipmunk", "Dolphin", "Duck", "Falcon", "Kiwi",
           "Lobster", "Ox", "Leopard", "Zebra", "Llama", "Narwhal"}
COLOURS = {"Red", "Orange", "Purple", "Yellow", "Green", "Blue", "Pink", "Cyan", "Black", "White"}

def write_rooms_to_file(rooms, filepath):
    with open(filepath, 'w') as wf:
        csv_writer = csv.writer(wf, delimiter='\t')
        for room in rooms:
            csv_writer.writerow(room.get_file_representation())
          
            
def read_rooms_to_file(filepath):
    result = []
    if os.path.isfile(filepath):
        with open(filepath, 'r') as rf:
            csv_reader = csv.reader(rf, delimiter='\t')
            for row in csv_reader:
                result.append(Room.from_text_representation(row))
    return result


def generate_user(exclude_list):
    exclude_colours = set([a.split()[0] for a in exclude_list])
    exclude_animals = set([a.split()[1] for a in exclude_list])

    colours = list(COLOURS.difference(exclude_colours))
    animals = list(ANIMALS.difference(exclude_animals))
    user_name = "{} {}".format(random.choice(colours), random.choice(animals))
    return {'username': user_name, 'uid': uuid.uuid4().hex}


def generate_wason_cards():
    even_numbers = [2, 4, 6, 8]
    odd_numbers = [1, 3, 5, 7, 9]
    vowels = ['A', 'I', 'E', 'O', 'U']
    consonants = ['B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'X', 'Z']
    cards_array = [random.choice(even_numbers), random.choice(odd_numbers), random.choice(consonants), random.choice(vowels)]
    random.shuffle(cards_array)
    
    return cards_array
