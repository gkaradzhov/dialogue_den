import datetime
import operator
import uuid

class Chat:
    def __init__(self, chat_room):
        self.chat_room = chat_room
        self.is_done = False
        self._messages = []
        
    def get_messages(self):
        return sorted(self._messages, key=operator.attrgetter('timestamp'))
    
    def append_message(self, message):
        self._messages.append(message)
        
        
class Message:
    def __init__(self, origin, text):
        self.origin = origin
        self.text = text
        self.timestamp = datetime.datetime.now()
        self.unique_id = uuid.uuid4().hex