import datetime
import operator
import uuid
import json

class Room:
    def __init__(self, name, room_id=None, is_done=False):
        self.name = name
        
        if room_id is None:
            self.room_id = uuid.uuid4().hex
        else:
            self.room_id = room_id
        self.is_done = is_done
        
    @classmethod
    def from_text_representation(cls, data_tuple):
        return cls(*data_tuple)
        
    def get_file_representation(self):
        return (self.name, self.room_id, self.is_done)
        
        
class Message:
    def __init__(self, origin_name, origin_id, room_id, message_type, content=''):
        self.origin = origin_name
        self.origin_id = origin_id
        self.message_type = message_type
        self.content = content
        self.timestamp = datetime.datetime.now()
        self.unique_id = uuid.uuid4().hex
        self.room_id = room_id
        
        with open('data/dialogues/{}'.format(room_id), 'a') as wf:
            wf.writelines(self.to_json())

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)