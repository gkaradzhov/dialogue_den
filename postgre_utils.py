import json

import psycopg2
import select
import time

from message import Room, Message


class PostgreConnection:
    def __init__(self, path_to_credentials, async_=False):
        with open(path_to_credentials, 'r') as rf:
            creds = json.load(rf)
        self.creds = creds
        self.async_ = async_
        
        self.connection, self.cursor = self.create_cursor()
    
    def create_cursor(self):
        connection = psycopg2.connect(user=self.creds['user'],
                                      database=self.creds['database'],
                                      password=self.creds['password'],
                                      host=self.creds['host'], async_=self.async_)
        if self.async_:
            self.wait(connection)
        
        cursor = connection.cursor()
        return connection, cursor
    
    @staticmethod
    def wait(conn):
        while True:
            state = conn.poll()
            if state == psycopg2.extensions.POLL_OK:
                break
            elif state == psycopg2.extensions.POLL_WRITE:
                select.select([], [conn.fileno()], [])
            elif state == psycopg2.extensions.POLL_READ:
                select.select([conn.fileno()], [], [])
            else:
                raise psycopg2.OperationalError("poll() returned %s" % state)
    
    def __execute(self, query, params=(), await=True):
        try:
            if self.async_:
                self.wait(self.cursor.connection)
            
            self.cursor.execute(query, params)
            
            if await:
                if self.async_:
                    self.wait(self.cursor.connection)
                results = self.cursor.fetchall()
                return results
        except psycopg2.OperationalError as err:
            print(err)
            # Try a single retry after 3 secs
            time.sleep(3)
            self.connection, self.cursor = self.create_cursor()
            self.cursor.execute(query, params)
            if await:
                if self.async_:
                    self.wait(self.cursor.connection)
                results = self.cursor.fetchall()
                return results
        except Exception as e:
            print(e)
    

    def create_room(self, room):
        self.__execute("INSERT INTO room (id, name, is_done) VALUES (%s, %s, %s) RETURNING ID", (room.room_id, room.name, room.is_done))
    
    
    def get_all_rooms(self):
        db_rooms = pg.__execute("SELECT id, name, is_done FROM room")
        rooms = []
        for r in db_rooms:
            rooms.append(Room(room_id=r[0], name=r[1], is_done=r[2]))
        return rooms

    def insert_message(self, message):
        self.__execute("INSERT INTO message (id, origin, origin_id, message_type, content, timestamp, room_id, user_status) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID",
                       (message.unique_id, message.origin, message.origin_id, message.message_type, message.content,
                        message.timestamp, message.room_id, message.user_status), False)

    def get_messages(self, room_id):
        db_messages = pg.__execute("SELECT id, origin, origin_id, message_type, content, timestamp, room_id, user_status "
                                "FROM message"
                                "WHERE room_id = %s"
                                "ORDER BY timestamp", (room_id,))
        messages = []
        for r in db_messages:
            messages.append(Message(unique_id=r[0], origin_name=r[1], origin_id=r[2], message_type=r[3], content=r[4],
                                    timestamp=r[5], room_id=r[6], user_status=r[7]))
        return messages

pg = PostgreConnection('creds.json', True)

