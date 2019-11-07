import json
from collections import defaultdict

import flask_socketio
from flask import Flask, request, render_template, redirect
from flask_socketio import join_room, leave_room
from flask_socketio import send

from data_persistency_utils import read_rooms_from_file, write_rooms_to_file
from message import Room, Message
from utils import generate_user, generate_wason_cards

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

CONVERSATION_LOGS = defaultdict(list)


# A welcome message to test our server
@app.route('/')
def index():
    existing_rooms = read_rooms_from_file()
    return render_template('home.html', chat_rooms=existing_rooms)


@app.route('/room/<room_id>')
def chatroom(room_id):
    existing_rooms = read_rooms_from_file()
    room_name = [n.name for n in existing_rooms][0]
    
    # TODO: 1. Get messages from memory
    # TODO: 2. Generate user if you have to (??)
    # TODO: 3. Generate game if you have to. Get latest game state
    # TODO: 4. Display logged in users (provide a way to login into the game)
    
    wason_game = generate_wason_cards()
    
    return render_template("room.html", room_data={'id': room_id, 'name': room_name, 'game': wason_game})


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


@app.route('/request_join', methods=('GET', 'POST'))
def request_join():
    data = request.args.get('existing_users', None)

    if data:
        data = data.split(',')
    else:
        data = []
    user = generate_user(data)
    return json.dumps(user)


@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    print(data)
    m = Message(origin_name=data['user_name'], message_type='JOIN_ROOM', room_id=room, origin_id=data['user_id'])
    
    CONVERSATION_LOGS[room].append(m)
    
    print("User {} joined the room {}".format(data['user_name'], room))
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
    send(username + ' has left the room.', room=room)


@socketio.on('response')
def handle_response(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room)
    
    socketio.emit('response', m.to_json(), room=room)


if __name__ == '__main__':
    socketio.run(host='localhost', port=8898, app=app)
    # Threaded option to enable multiple instances for multiple user access support
    # app.run(threaded=True, port=5000)
