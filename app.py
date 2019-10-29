from flask import Flask, request, jsonify, render_template, redirect
import flask_socketio
from flask_socketio import join_room, leave_room
from flask_socketio import send, emit

from message import Room
from utils import read_rooms_to_file, write_rooms_to_file
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = flask_socketio.SocketIO(app)
ROOM_PATH = "data/rooms.tsv"

CHAT_ROOMS_DATA = {'123dasdq34radc': "First Room",
                   'das3dasdasdas': "Second Room",
                   "dasd3rfsdcfs3aczzzzz": 'Third Room'
                   }

USERNAMES = [{'username': 'Pink', 'uid': 1234},
             {'username': 'Blue', 'uid': 567},
             {'username': 'Green', 'uid': 123123123123123123}
             ]

# A welcome message to test our server
@app.route('/')
def index():
    existing_rooms = read_rooms_to_file(ROOM_PATH)
    return render_template('home.html', chat_rooms=existing_rooms)


@app.route('/room/<room_id>')
def chatroom(room_id):
    existing_rooms = read_rooms_to_file(ROOM_PATH)
    name = [n.name for n in existing_rooms][0]
    user = random.choice(USERNAMES)
    print(user)
    return render_template("room.html", room_data={'id': room_id, 'name': name, 'user_id': user['uid'],
                                                   'username': user['username']})


@app.route('/create_room', methods=('GET', 'POST'))
def create_room():
    room_name = request.form.get('room_name', None)
    if room_name is None:
        return render_template("create_room.html")
    else:
        room = Room(room_name)
        existing_rooms = read_rooms_to_file(ROOM_PATH)
        existing_rooms.append(room)
        write_rooms_to_file(existing_rooms, ROOM_PATH)
        return redirect('/')
    
@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    print("User {} joined the room {}".format(username, room))
    send(username + ' has entered the room.', room=room)


def messageReceived(methods=('GET', 'POST')):
    print('message was received!!!')


@socketio.on('response')
def handle_my_custom_event(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room = json['room']
    socketio.emit('response', json, room=room)


if __name__ == '__main__':
    socketio.run(app)
    # Threaded option to enable multiple instances for multiple user access support
    # app.run(threaded=True, port=5000)
