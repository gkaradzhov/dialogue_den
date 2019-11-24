import csv
import json
from os import listdir
from os.path import isfile, join

import boto3

import sys_config
from message import Room
from sys_config import DIALOGUES_STABLE


def write_rooms_to_file(rooms):
    filepath = sys_config.ROOM_PATH
    with open(filepath, 'w') as wf:
        csv_writer = csv.writer(wf, delimiter='\t')
        for room in rooms:
            csv_writer.writerow(room.get_file_representation())


def read_rooms_from_file():
    result = []
    filepath = sys_config.ROOM_PATH
    if os.path.isfile(filepath):
        with open(filepath, 'r') as rf:
            csv_reader = csv.reader(rf, delimiter='\t')
            for row in csv_reader:
                result.append(Room.from_text_representation(row))
    return result


def get_dialogue(room_id):
    dialogue = []
    filepath = os.path.join(sys_config.DIALOGUES_RUNNING, room_id)
    if os.path.isfile(filepath):
        with open(filepath, 'r') as rf:
            for row in rf.readlines():
                dialogue.append(json.loads(row))
    return dialogue


import os
import zipfile
import datetime


def add_new_archive():
    os.rename(sys_config.LAST_STABLE, "{}_{}".format(datetime.datetime.utcnow(), sys_config.LAST_STABLE))
    
    zipf = zipfile.ZipFile(sys_config.LAST_STABLE, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(sys_config.DATA_FOLDER):
        for file in files:
            zipf.write(os.path.join(root, file))


def save_file(file_name):
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')
    try:
        s3 = boto3.client('s3')
        s3.upload_file(Bucket=S3_BUCKET, Key=file_name, Filename=file_name)
    except Exception as e:
        print(e)


def sync_rooms():
    file_name = "data/rooms.tsv"
    save_file(file_name)


def sync_everything():
    rooms_file = "data/rooms.tsv"
    save_file(rooms_file)
    stable_files = [join(DIALOGUES_STABLE, f) for f in listdir(DIALOGUES_STABLE) if isfile(join(DIALOGUES_STABLE, f))]
    print(stable_files)
    for file in stable_files:
        save_file(file)
