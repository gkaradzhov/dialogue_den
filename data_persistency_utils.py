import csv
import os

import boto3

from message import Room
from sys_config import ROOM_PATH


def write_rooms_to_file(rooms):
    filepath = ROOM_PATH
    with open(filepath, 'w') as wf:
        csv_writer = csv.writer(wf, delimiter='\t')
        for room in rooms:
            csv_writer.writerow(room.get_file_representation())


def read_rooms_from_file():
    result = []
    filepath = ROOM_PATH
    if os.path.isfile(filepath):
        with open(filepath, 'r') as rf:
            csv_reader = csv.reader(rf, delimiter='\t')
            for row in csv_reader:
                result.append(Room.from_text_representation(row))
    return result


def save_file(file_name):
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')
    try:
        s3 = boto3.client('s3')
        s3.upload_file(Bucket=S3_BUCKET, Key=file_name, Filename=file_name)
    except:
        pass


def sync_rooms():
    file_name = "data/rooms.tsv"
    save_file(file_name)


def sync_dialogue():
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')
    
    file_name = "data/rooms.tsv"
    
    try:
        s3 = boto3.client('s3')
        s3.upload_file(Bucket=S3_BUCKET, Key=file_name, Filename=file_name)
    except:
        pass
