import json

import psycopg2
import select
import time
import os

from message import Room, Message


class PostgreConnection:
    def __init__(self, path_to_credentials):
        if os.path.exists(path_to_credentials):
            with open(path_to_credentials, 'r') as rf:
                creds = json.load(rf)
        else:
            creds = {
                'user': os.environ.get('DB_USER'),
                'database': os.environ.get('DB_NAME'),
                'password': os.environ.get('DB_PASS'),
                'host': os.environ.get('DB_HOST')
            }

        self.creds = creds
        
        self.connection, self.cursor = self.create_cursor()

    def wait(self):
        while True:
            state = self.connection.poll()
            if state == psycopg2.extensions.POLL_OK:
                break
            elif state == psycopg2.extensions.POLL_WRITE:
                select.select([], [self.connection.fileno()], [])
            elif state == psycopg2.extensions.POLL_READ:
                select.select([self.connection.fileno()], [], [])
            else:
                raise psycopg2.OperationalError("poll() returned %s" % state)
    
    def create_cursor(self):
        connection = psycopg2.connect(user=self.creds['user'],
                                      database=self.creds['database'],
                                      password=self.creds['password'],
                                      host=self.creds['host'])
        connection.set_session(autocommit=True)
        cursor = connection.cursor()
        return connection, cursor
    
    def __execute(self, query, params=()):
        try:
            self.wait()
            self.cursor.execute(query, params)

            results = self.cursor.fetchall()
            return results
        except psycopg2.OperationalError as err:
            print(err)
            # Try a single retry after 3 secs
            time.sleep(3)
            self.connection, self.cursor = self.create_cursor()
            self.cursor.execute(query, params)

            results = self.cursor.fetchall()
            return results
        except Exception as e:
            print("Query: {}; Params: {}".format(query, params))
            print(e)
    

    def create_room(self, room):
        self.__execute("INSERT INTO room (id, name, is_done) VALUES (%s, %s, %s) RETURNING ID", (room.room_id, room.name, room.is_done))
    
    def get_active_rooms(self):
        db_rooms = self.__execute("SELECT id, name, is_done FROM room WHERE is_done=false")
        rooms = []
        for r in db_rooms:
            rooms.append(Room(room_id=r[0], name=r[1], is_done=r[2]))
        return rooms
    
    def get_single_room(self, room_id):
        room = self.__execute("SELECT id, name, is_done FROM room WHERE id=%s", (room_id,))
        if len(room) != 0:
            room = room[0]
            return Room(room_id=room[0], name=room[1], is_done=room[2])
        else:
            raise ValueError('No room with that ID')
            
    def insert_message(self, message):
        self.__execute("INSERT INTO message (id, origin, origin_id, message_type, content, timestamp, room_id, user_status) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID",
                       (message.unique_id, message.origin, message.origin_id, message.message_type, str(message.content),
                        message.timestamp, message.room_id, message.user_status))

    def get_messages(self, room_id):
        db_messages = self.__execute("SELECT id, origin, origin_id, message_type, content, timestamp, room_id, user_status "
                                " FROM message"
                                " WHERE room_id = %s"
                                " ORDER BY timestamp", (room_id,))
        messages = []
        for r in db_messages:
            messages.append(Message(unique_id=r[0], origin_name=r[1], origin_id=r[2], message_type=r[3], content=r[4],
                                    timestamp=r[5], room_id=r[6], user_status=r[7]))
        return messages
    
    def mark_room_done(self, room_id):
        self.__execute("UPDATE room SET is_done=True WHERE id=%s RETURNING ID", (room_id,))

#pg = PostgreConnection('creds.json', True)

