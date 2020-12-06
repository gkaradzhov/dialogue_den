import json
import os
import random
import uuid

import boto3

ANIMALS = {"Cat", "Guinea pig", "Alpaca", "Bat", "Beaver", "Bee", "Chipmunk", "Dolphin", "Duck", "Falcon",
           "Kiwi", "Lobster", "Ox", "Leopard", "Zebra", "Llama", "Narwhal", 'Lion', 'Tiger', "Hedgehog",
           "Giraffe", 'Puffin', 'Unicorn', 'Koala', 'Raven', 'Emu', 'Butterfly', 'Hamster', 'Panda'}


# COLOURS = {"Red", "Orange", "Purple", "Yellow", "Green", "Blue", "Pink", "Cyan", "Black", "White"}


def generate_user(exclude_list, user_type):
    if user_type == 'moderator':
        user_name = "Moderating Owl"
    else:
        exclude_animals = set([a for a in exclude_list])
        animals = list(ANIMALS.difference(exclude_animals))
        user_name = "{}".format(random.choice(animals))
    return {'user_name': user_name, 'user_id': uuid.uuid4().hex}


def generate_wason_cards():
    even_numbers = [2, 4, 6, 8]
    odd_numbers = [3, 5, 7, 9]
    vowels = ['A', 'E', 'U']
    consonants = ['B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'X', 'Z']
    cards_array = [random.choice(even_numbers), random.choice(odd_numbers), random.choice(consonants),
                   random.choice(vowels)]
    random.shuffle(cards_array)
    cards_obj = [{'value': str(a), 'checked': False} for a in cards_array]
    return cards_obj


class MTurkManagement():
    def __init__(self, path_to_credentials):
        if os.path.exists(path_to_credentials):
            with open(path_to_credentials, 'r') as rf:
                creds = json.load(rf)
        else:
            creds = {
                'mturk_access': os.environ.get('MTURK_ACCESS'),
                'mturk_secret': os.environ.get('MTURK_SECRET'),
                'qualification': os.environ.get('DelibotDataCollectionRestrict'),
            }
        
        MTURK_URL = 'https://mturk-requester.us-east-1.amazonaws.com'
        
        self.creds = creds
        self.mturk_client = boto3.client('mturk',
                                         aws_access_key_id=creds['mturk_access'],
                                         aws_secret_access_key=creds['mturk_secret'],
                                         region_name='us-east-1',
                                         endpoint_url=MTURK_URL
                                         )
    
    def grant_qualification(self, worker_id):
        self.mturk_client.associate_qualification_with_worker(QualificationTypeId=self.creds['qualification'],
                                                              WorkerId=worker_id)
