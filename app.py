import json
from collections import defaultdict

import flask_socketio
from flask import Flask, request, render_template, redirect
from flask_socketio import join_room, leave_room
from flask_socketio import send

from data_persistency_utils import read_rooms_from_file, write_rooms_to_file, get_dialogue, add_new_archive
from message import Room, Message
from utils import generate_user, generate_wason_cards
from sys_config import DIALOGUES_STABLE
from os import path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

CONVERSATION_LOGS = defaultdict(list)

def trigger_finish(room_data):
    
    room_id = room_data[0]['room']
    
    # 1. Save the dialogue to dialogues_stable
    filepath = path.join(DIALOGUES_STABLE, room_id)
    with open(filepath, 'w') as wf:
        for item in room_data:
            wf.writelines(item.to_json() + '\n')
            
    # 2. Mark room as closed
    existing_rooms = read_rooms_from_file()
    for room in existing_rooms:
        if room[1] == room_id:
            room[2] = True
    write_rooms_to_file(existing_rooms)
    
    # 3. Archive data folder
    add_new_archive()
    
    # 4. Sync with amazon s3
    
    
    # 5. Send via email ?
    
    pass

# A welcome message to test our server
@app.route('/')
def index():
    existing_rooms = read_rooms_from_file()
    return render_template('home.html', chat_rooms=existing_rooms)


@app.route('/room/<room_id>')
def chatroom(room_id):
    existing_rooms = read_rooms_from_file()
    room_name = [n.name for n in existing_rooms][0]
    
    running_dialogue = get_dialogue(room_id)
    
    messages = [d for d in running_dialogue if d['type'] == 'CHAT_MESSAGE']
    logged_users = set()
    for item in running_dialogue:
        if item['type'] == 'JOIN_ROOM':
            logged_users.add((item['user_name'], item['user_id']))
        elif item['type'] == 'LEAVE_ROOM' and (item['user_name'], item['user_id']) in logged_users:
            logged_users.remove((item['user_name'], item['user_id']))
    
    current_user = generate_user([d[0] for d in logged_users])
    m = Message(origin_name=current_user['user_name'], message_type='JOIN_ROOM', room_id=room_id,
                origin_id=current_user['user_id'])
    CONVERSATION_LOGS[room_id].append(m)
    socketio.emit('response', m.to_json(), room=room_id)
    
    wason_initial = [d['message'] for d in running_dialogue if d['type'] == 'WASON_INITIAL']
    if len(wason_initial) > 0:
        wason_initial = wason_initial[0]
        wason_final_state = [d['message'] for d in running_dialogue if d['type'] == 'WASON_GAME']
        if len(wason_final_state) > 0:
            wason_initial = wason_final_state[-1]
    
    if len(wason_initial) == 0:
        wason_game = generate_wason_cards()
        m = Message(origin_name='SYSTEM', message_type='WASON_INITIAL', room_id=room_id,
                    origin_id='-1', content=wason_game)
        CONVERSATION_LOGS[room_id].append(m)
    else:
        wason_game = wason_initial
    
    return render_template("room.html", room_data={'id': room_id, 'name': room_name, 'game': wason_game,
                                                   'messages': messages, 'existing_users': logged_users,
                                                   'current_user': current_user['user_name'],
                                                   'current_user_id': current_user['user_id']})


@app.route('/create_room', methods=('GET', 'POST'))
def create_room():
    room_name = request.form.get('room_name', None)
    if room_name is None:
        return render_template("create_room.html")
    else:
        room = Room(room_name)
        existing_rooms = read_rooms_from_file()
        existing_rooms.append(room)
        write_rooms_to_file(existing_rooms)
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
    m = Message(origin_name=username, message_type='LEAVE_ROOM', room_id=room, origin_id=user_id)
    CONVERSATION_LOGS[room].append(m)
    
    print("User {} has left the room {}".format(username, room))
    socketio.emit('response', m.to_json(), room=room)


def check_finished(room_history):
    logged_users = {}
    for item in room_history:
        if item.message_type == 'JOIN_ROOM' or item.message_type == 'DISAGREE_WASON_GAME':
            logged_users[item.origin_id] = False
        elif item.message_type == 'LEAVE_ROOM' and item.origin_id in logged_users:
            del logged_users[item.origin_id]
        elif item.message_type == 'AGREE_WASON_GAME':
            logged_users[item.origin_id] = True
        elif item.message_type == 'WASON_GAME':
            for key in logged_users.keys():
                logged_users[key] = False
    
    for user, outcome in logged_users.items():
        if not outcome:
            return False
    return True

@socketio.on('response')
def handle_response(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room,
                content=json['message'])

    CONVERSATION_LOGS[room].append(m)
    socketio.emit('response', m.to_json(), room=room)

    is_finished = check_finished(CONVERSATION_LOGS[room])
    
    if is_finished:
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type='WASON_FINISHED', room_id=room,
                    content=json['message'])
        triger_finish(CONVERSATION_LOGS[room])
        socketio.emit('response', m.to_json(), room=room)


if __name__ == '__main__':
    socketio.run(host='localhost', port=8898, app=app)
    # Threaded option to enable multiple instances for multiple user access support
    # app.run(threaded=True, port=5000)
