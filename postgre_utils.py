import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta

import psycopg2
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
        pool = ThreadedConnectionPool(15, 150, user=self.creds['user'],
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
        except:
            print("Connection not available. Trying again")
            time.sleep(3)
            self.pool = self.create_pool()
            conn, cursor = self.get_cursor()

        try:
            cursor.execute(query, params)
            results = cursor.fetchall()
            return results
        except psycopg2.OperationalError as err:
            print(err)
            print("[Inner Exception] Query: {}; Params: {}".format(query, params))
            time.sleep(3)
            cursor.execute(query, params)
            results = cursor.fetchall()
            return results
        except Exception as e:
            print("[Outer Exception] Query: {}; Params: {}".format(query, params))
            print(e)
        finally:
            cursor.close()
            self.pool.putconn(conn)

    def create_room(self, room, optional_type='chat', game_object=None):
        if not room.campaign:
            campaign_id = self.__execute("SELECT id FROM campaign WHERE name LIKE 'local_beta'")
            if len(campaign_id) > 0:
                room.campaign = campaign_id[0]
        self.__execute(
            "INSERT INTO room (id, name, is_done, campaign_id, status) VALUES (%s, %s, %s, %s, 'RECRUITING') RETURNING ID",
            (room.room_id, room.name, room.is_done, room.campaign))
        if game_object:
            game = game_object
        else:
            game = generate_wason_cards()
        m = Message(origin_name='SYSTEM', message_type=WASON_INITIAL, room_id=room.room_id,
                    origin_id='-1', content=json.dumps(game))
        self.insert_message(m)

        m = Message(origin_name='SYSTEM', message_type='ROOM_TYPE', room_id=room.room_id,
                    origin_id='-1', content=optional_type)
        self.insert_message(m)

        return room.room_id

    def get_active_rooms(self):
        db_rooms = self.__execute("SELECT id, name, is_done FROM room WHERE is_done=false")
        rooms = []
        for r in db_rooms:
            rooms.append(Room(room_id=r[0], name=r[1], is_done=r[2]))
        return rooms

    def get_single_room(self, room_id):
        # TODO: Remove is done
        room = self.__execute("SELECT id, name, is_done, campaign_id, status FROM room WHERE id=%s", (room_id,))
        if len(room) != 0:
            room = room[0]
            return Room(room_id=room[0], name=room[1], is_done=room[2], campaign=room[3], status=room[4])
        else:
            raise ValueError('No room with that ID')

    def insert_message(self, message):
        self.__execute(
            "INSERT INTO message (id, origin, origin_id, message_type, content, timestamp, room_id, user_status, origin_type) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID",
            (message.unique_id, message.origin, message.origin_id, message.message_type, str(message.content),
             message.timestamp, message.room_id, message.user_status, message.user_type))

    def get_messages(self, room_id):
        db_messages = self.__execute(
            "SELECT id, origin, origin_id, message_type, content, timestamp, room_id, user_status, origin_type "
            " FROM message"
            " WHERE room_id = %s"
            " ORDER BY timestamp", (room_id,))
        messages = []
        for r in db_messages:
            messages.append(Message(unique_id=r[0], origin_name=r[1], origin_id=r[2], message_type=r[3], content=r[4],
                                    timestamp=r[5], room_id=r[6], user_status=r[7], user_type=r[8]))
        return messages

    def mark_room_done(self, room_id):
        self.__execute("UPDATE room SET is_done=True WHERE id=%s RETURNING ID", (room_id,))

    def get_campaign(self, campaign_id):
        campaign = self.__execute(
            "SELECT id, start_threshold, start_time, close_threshold, user_moderator_chance, name FROM campaign WHERE id=%s AND is_active=true",
            (campaign_id,))
        if len(campaign) > 0:
            campaign = campaign[0]
        else:
            return None

        return {'id': campaign[0], 'start_threshold': campaign[1], 'start_time': campaign[2],
                'close_threshold': campaign[3], 'user_moderator_chance': campaign[4], 'name': campaign[5]}

    def get_campaigns(self):
        campaigns = self.__execute("SELECT id, name FROM campaign")
        return campaigns

    def get_create_campaign_room(self, campaign_id):

        campaign_data = self.get_campaign(campaign_id)

        before_start_time = datetime.utcnow() - timedelta(minutes=(campaign_data['start_time'] + 2))
        before_1_hour = datetime.utcnow() - timedelta(hours=1)

        get_room_sql = """
            SELECT r.id FROM message m
            JOIN room r on m.room_id = r.id
            JOIN campaign c on c.id = r.campaign_id
            WHERE m.room_id NOT IN (
                SELECT room_id
                from message
                WHERE message_type = 'FINISHED_ONBOARDING'
                OR (message_type = 'ROUTING_TIMER_STARTED' AND timestamp < '{0}')
                )
            AND m.room_id NOT IN (
                SELECT room_id
                FROM message
                GROUP BY room_id
                HAVING MAX(timestamp) < '{1}'
                )
            AND r.is_done = false
            AND r.campaign_id = %s
            AND c.is_active = true
            AND r.status IN ('RECRUITING', 'ROUTING_TIMER_STARTED')
            GROUP BY r.id
            ORDER BY MAX(m.timestamp) DESC""".format(before_start_time.isoformat(), before_1_hour.isoformat())

        rooms = self.__execute(get_room_sql, (campaign_id,))

        if len(rooms) == 0:
            room_name = "{}_{}".format(time.time(), campaign_id)
            ch = random.choice(['data/games/chess/chess_run_1.json'])
            with open(ch, 'r') as rf:
                games = json.load(rf)
                random.shuffle(games)
                for g in games:
                    random.shuffle(g['moves'])

            r = Room(room_name, campaign=campaign_id)
            # type = random.choice(
            #     ['delibot', 'delibot2'])
            type = "NA"
            self.create_room(r, game_object=games)
            return r.room_id, type
        else:
            type = self.__execute(
                "SELECT content FROM message WHERE room_id=%s and message_type='ROOM_TYPE'", (rooms[0],))
            if type is None or len(type) == 0:
                type = 'chat'
            else:
                print('here', type)
                type = type[0][0]
            return rooms[0], type

    def set_room_status(self, room_id, status):
        self.__execute("UPDATE room SET status=%s WHERE id=%s RETURNING ID", (status, room_id))

    def add_initial_mturk_info(self, assignment_id, hit_id, turk_id, campaign_id, return_url):
        mturk_info_id = str(uuid.uuid4())

        self.__execute(
            "INSERT INTO mturk_info (id, assignment_id, campaign_id, hit_id, worker_id, redirect_url) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING ID",
            (mturk_info_id, assignment_id, campaign_id, hit_id, turk_id, return_url))

        return mturk_info_id

    def update_mturk_user_id(self, mturk_info_id, user_id):
        if mturk_info_id and mturk_info_id != '0':
            self.__execute("UPDATE mturk_info SET user_id = %s WHERE id= %s RETURNING ID", (user_id, mturk_info_id))

    def get_mturk_info(self, mturk_info_id):
        if mturk_info_id and mturk_info_id != '0':
            return_url = self.__execute("SELECT assignment_id, redirect_url, worker_id FROM mturk_info WHERE id=%s",
                                        (mturk_info_id,))
            if return_url:
                return return_url[0]
            else:
                return None
        else:
            return None

    def check_for_user(self, mturk_info_id):
        if mturk_info_id and mturk_info_id != '0':
            worker_id = self.__execute("SELECT worker_id FROM mturk_info WHERE id=%s", (mturk_info_id,))
            print("WId", str(worker_id))
            if worker_id:
                has_user = self.__execute("SELECT worker_id FROM mturk_info WHERE worker_id=%s AND user_id IS NOT NULL and campaign_id=%s",
                                          (worker_id[0], "0d957f51-702c-4882-8475-921d4e4f041d")) #Special UUID token for the chess recruiting
                print("Has Us Internal", str(has_user))
                if has_user:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False

    def record_feedback(self, room_id, user_id, feedback):
        self.__execute(
            "INSERT INTO room_feedback (id, room_id, origin_id, feedback) "
            "VALUES (%s, %s, %s, %s) RETURNING ID",
            (str(uuid.uuid4()), room_id, user_id, feedback))


# pg = PostgreConnection('creds.json', True)


class PostgresMock:
    def __init__(self, path_to_credentials=None):
        print("Init PostgresMock")

    def create_room(self, room):
        pass

    def get_active_rooms(self):
        return []

    def get_single(self, room_id):
        return Room(name='Test')

    def insert_message(self, message):
        pass

    def get_messages(self, room_id):
        return []

    def mark_room_done(self, room_id):
        pass
