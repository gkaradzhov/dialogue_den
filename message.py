import datetime
import json
import os
import uuid

from sys_config import DIALOGUES_RUNNING


class Room:
    def __init__(self, name, room_id=None, is_done=False):
        self.name = name
        
        if room_id is None:
            self.room_id = uuid.uuid4().hex
        else:
            self.room_id = room_id
        self.is_done = is_done == 'True'
    
    @classmethod
    def from_text_representation(cls, data_tuple):
        return cls(*data_tuple)
    
    def get_file_representation(self):
        return (self.name, self.room_id, self.is_done)


class Message:
    def __init__(self, origin_name, room_id, message_type, content='', origin_id=None):
        self.origin = origin_name
        self.origin_id = origin_id
        self.message_type = message_type
        self.content = content
        self.timestamp = datetime.datetime.now()
        self.unique_id = uuid.uuid4().hex
        self.room_id = room_id
        
        filename = os.path.join(DIALOGUES_RUNNING, room_id)
        if os.path.exists(filename):
            append_write = 'a'  # append if already exists
        else:
            append_write = 'w'  # make a new file if not
        
        with open(filename, append_write) as wf:
            wf.writelines(self.to_json() + '\n')
    
    def to_json(self):
        output_dict = {
            'user_id': self.origin_id,
            'user_name': self.origin,
            'type': self.message_type,
            'message': self.content,
            'timestamp': str(self.timestamp),
            'room_id': self.room_id,
            'message_id': self.unique_id
        }
        return json.dumps(output_dict)
