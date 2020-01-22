import json

import psycopg2
import select
import time
import os

from psycopg2.pool import ThreadedConnectionPool

from constants import WASON_INITIAL
from message import Room, Message
from utils import generate_wason_cards


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
        
        self.pool = self.create_pool()
    
    def create_pool(self):
        pool = ThreadedConnectionPool(15, 50, user=self.creds['user'],
                                      database=self.creds['database'],
                                      password=self.creds['password'],
                                      host=self.creds['host'])
        # connection = psycopg2.connect(user=self.creds['user'],
        #                               database=self.creds['database'],
        #                               password=self.creds['password'],
        #                               host=self.creds['host'])
        
        return pool
        
    def get_cursor(self):
        connection = self.pool.getconn()
        connection.set_session(autocommit=True)
        cursor = connection.cursor()
        return connection, cursor
    
    def __execute(self, query, params=()):
        try:
            conn, cursor = self.get_cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            self.pool.putconn(conn)
            return results
        except psycopg2.OperationalError as err:
            print(err)
            print("Query: {}; Params: {}".format(query, params))
            # Try a single retry after 3 secs
            time.sleep(3)
            self.pool = self.create_pool()
            conn, cursor = self.get_cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            self.pool.putconn(conn)
            return results
        except Exception as e:
            print("Query: {}; Params: {}".format(query, params))
            print(e)
    

    def create_room(self, room):
        self.__execute("INSERT INTO room (id, name, is_done, campaign_id) VALUES (%s, %s, %s, %s) RETURNING ID", (room.room_id, room.name, room.is_done, room.campaign))
        wason_game = generate_wason_cards()
        m = Message(origin_name='SYSTEM', message_type=WASON_INITIAL, room_id=room.room_id,
                    origin_id='-1', content=json.dumps(wason_game))
        self.insert_message(m)
    
    def get_active_rooms(self):
        db_rooms = self.__execute("SELECT id, name, is_done FROM room WHERE is_done=false")
        rooms = []
        for r in db_rooms:
            rooms.append(Room(room_id=r[0], name=r[1], is_done=r[2]))
        return rooms
    
    def get_single_room(self, room_id):
        room = self.__execute("SELECT id, name, is_done, campaign_id FROM room WHERE id=%s", (room_id,))
        if len(room) != 0:
            room = room[0]
            return Room(room_id=room[0], name=room[1], is_done=room[2], campaign=room[3])
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

    def get_campaign(self, campaign_id):
        campaign = self.__execute("SELECT id, start_threshold, start_time, close_threshold FROM campaign WHERE id=%s AND is_active=true", (campaign_id,))
        if len(campaign) > 0:
            campaign = campaign[0]
        else:
            return None
        
        return {'id': campaign[0], 'start_threhold': campaign[1], 'start_time': campaign[2], 'close_threshold': campaign[3]}

    def get_create_campaign_room(self, campaign_id):
        get_room_sql = """
            SELECT r.id FROM message m
            JOIN room r on m.room_id = r.id
            JOIN campaign c on c.id = r.campaign_id
            WHERE m.room_id NOT IN (
                SELECT room_id
                from message
                WHERE message_type ='FINISHED_ONBOARDING')
            AND r.is_done = false
            AND r.campaign_id = %s
            AND c.is_active = true
            GROUP BY r.id
            ORDER BY MAX(m.timestamp) DESC"""
        
        rooms = self.__execute(get_room_sql, (campaign_id,))
        
        if len(rooms) == 0:
            room_name = "{}_{}".format(time.time(), campaign_id)
            r = Room(room_name, campaign=campaign_id)
            self.create_room(r)
            return r.room_id
        else:
            return rooms[0]
        
        


#pg = PostgreConnection('creds.json', True)



class PostgreMock:
    def __init__(self, path_to_credentials=None):
        print("Init PostgreMock")

    def create_room(self, room):
        pass

    def get_active_rooms(self):
        return []

    def get_single_room(self, room_id):
        return Room(name='Test')

    def insert_message(self, message):
        pass

    def get_messages(self, room_id):
        return []

    def mark_room_done(self, room_id):
        pass