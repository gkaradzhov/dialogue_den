import datetime
import json
import signal
from os import path

import flask_socketio
from flask import Flask, request, render_template, redirect
from flask_socketio import join_room, leave_room
from flask_socketio import send

from constants import JOIN_ROOM, CHAT_MESSAGE, LEAVE_ROOM, WASON_INITIAL, WASON_AGREE, WASON_GAME, WASON_FINISHED, \
    USR_ONBOARDING, USR_PLAYING, FINISHED_ONBOARDING
from data_persistency_utils import read_rooms_from_file, write_rooms_to_file, sync_everything, save_file
from message import Room, Message
from postgre_utils import PostgreConnection
from sys_config import DIALOGUES_STABLE, ROOM_PATH
from utils import generate_user, generate_wason_cards


app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

PG = PostgreConnection('aws_creds.json')


def trigger_finish(room_data):
    room_id = room_data[0].room_id
    
    PG.mark_room_done(room_id)
    
    # 1. Save the dialogue to dialogues_stable
    filepath = path.join(DIALOGUES_STABLE, room_id)
    with open(filepath, 'w') as wf:
        for item in room_data:
            wf.writelines(item.to_json() + '\n')
            
    #Sync file to Amazon
    save_file(filepath)
    
    # 2. Mark room as closed
    existing_rooms = read_rooms_from_file()
    for room in existing_rooms:
        if room.room_id == room_id:
            room.is_done = True
    write_rooms_to_file(existing_rooms)
    
    # Sync rooms to amazon
    save_file(ROOM_PATH)

# A welcome message to test our server
@app.route('/')
def index():
    existing_rooms = PG.get_active_rooms()
    return render_template('home.html', chat_rooms=existing_rooms)


@app.route('/room/<room_id>')
def chatroom(room_id):
    room_name = PG.get_single_room(room_id).name
    running_dialogue = PG.get_messages(room_id)
    
    messages = [d for d in running_dialogue if d.message_type == CHAT_MESSAGE]
    logged_users = set()
    for item in running_dialogue:
        if item.message_type == JOIN_ROOM:
            logged_users.add((item.origin, item.origin_id))
        elif item.message_type == LEAVE_ROOM and (item.origin, item.origin_id) in logged_users:
            logged_users.remove((item.origin, item.origin_id))
    
    current_user = generate_user([d[0] for d in logged_users])
    
    m = Message(origin_name=current_user['user_name'], message_type=JOIN_ROOM, room_id=room_id,
                origin_id=current_user['user_id'], user_status=USR_ONBOARDING)
    PG.insert_message(m)
    socketio.emit('response', m.to_json(), room=room_id)
    
    wason_initial = [d.content for d in running_dialogue if d.message_type == WASON_INITIAL][0]
    
    return render_template("room.html", room_data={'id': room_id, 'name': room_name, 'game': json.loads(wason_initial),
                                                   'messages': messages, 'existing_users': logged_users,
                                                   'current_user': current_user['user_name'],
                                                   'current_user_id': current_user['user_id'],
                                                   'current_user_status': USR_ONBOARDING})




@app.route('/create_room', methods=('GET', 'POST'))
def create_room():
    room_name = request.form.get('room_name', None)
    if room_name is None:
        return render_template("create_room.html")
    else:
        room = Room(room_name)
        
        PG.create_room(room)
        
        existing_rooms = read_rooms_from_file()
        existing_rooms.append(room)
        write_rooms_to_file(existing_rooms)
        wason_game = generate_wason_cards()
        m = Message(origin_name='SYSTEM', message_type=WASON_INITIAL, room_id=room.room_id,
                    origin_id='-1', content=json.dumps(wason_game))
        PG.insert_message(m)
        return redirect('/')


@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    send(data['user_name'] + ' has entered the room.', room=room)


@socketio.on('leave')
def on_leave(data):
    username = data['user_name']
    user_id = data['user_id']
    room = data['room']
    leave_room(room)
    m = Message(origin_name=username, message_type=LEAVE_ROOM, room_id=room, origin_id=user_id)
    PG.insert_message(m)
    print("User {} has left the room {}".format(username, room))
    socketio.emit('response', m.to_json(), room=room)


def check_finished(room_history, usr_status):
    logged_users = {}
    for item in room_history:
        if usr_status == USR_ONBOARDING and item.message_type == FINISHED_ONBOARDING:
            # No need to check, already finished onboarding
            return False
        if item.message_type == LEAVE_ROOM and item.origin_id in logged_users:
            del logged_users[item.origin_id]
        elif item.message_type == WASON_AGREE and item.user_status == usr_status:
            logged_users[item.origin_id] = True
        elif item.message_type == WASON_GAME or item.message_type == JOIN_ROOM:
            logged_users[item.origin_id] = False
    
    for user, outcome in logged_users.items():
        if not outcome:
            return False
    return True


@socketio.on('response')
def handle_response(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room,
                content=json['message'], user_status=json['user_status'])
    
    socketio.emit('response', m.to_json(), room=room)
    PG.insert_message(m)
    
    all_messages = PG.get_messages(room)
    finished_onboarding = check_finished(all_messages, USR_ONBOARDING)
    
    if finished_onboarding:
        after_5mins = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        date_str = after_5mins.isoformat()
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type=FINISHED_ONBOARDING, room_id=room,
                    content=date_str)
        socketio.emit('response', m.to_json(), room=room)
        PG.insert_message(m)
    
    finished_game = check_finished(all_messages, USR_PLAYING)
    if finished_game:
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type=WASON_FINISHED, room_id=room)
        trigger_finish(all_messages)
        socketio.emit('response', m.to_json(), room=room)
        PG.insert_message(m)


def receiveSignal(signal_num, frame):
    print("Exiting signally")
    sync_everything()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, receiveSignal)
    try:
        socketio.run(host='localhost', port=8898, app=app, threaded=False, processes=3)
    finally:
        print("Exiting gracefully")
        sync_everything()
    
    # Threaded option to enable multiple instances for multiple user access support
    # app.run(threaded=True, port=5000)
