import flask_socketio
from flask import Flask, request, render_template, redirect
from flask_socketio import join_room, leave_room
from flask_socketio import send
from gunicorn.app.wsgiapp import WSGIApplication
import os
import boto3, json


from message import Room, Message
from utils import read_rooms_to_file, write_rooms_to_file, generate_user, generate_wason_cards

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')
ROOM_PATH = "data/rooms.tsv"


# A welcome message to test our server
@app.route('/')
def index():
    existing_rooms = read_rooms_to_file(ROOM_PATH)
    return render_template('home.html', chat_rooms=existing_rooms)


@app.route('/room/<room_id>')
def chatroom(room_id):
    existing_rooms = read_rooms_to_file(ROOM_PATH)
    name = [n.name for n in existing_rooms][0]
    user = generate_user([])
    wason_game = generate_wason_cards()
    
    return render_template("room.html", room_data={'id': room_id, 'name': name, 'user_id': user['uid'],
                                                   'username': user['username'], 'game': wason_game})


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
    m = Message(origin_name=username, message_type='JOIN_ROOM', room_id=room)
    print("User {} joined the room {}".format(username, room))
    send(username + ' has entered the room.', room=room)
    
    
@socketio.on('leave')
def on_leave(data):
    username = data['username']
    room = data['room']
    leave_room(room)
    m = Message(origin_name=username, message_type='LEAVE_ROOM', room_id=room)
    print("User {} has left the room {}".format(username, room))
    send(username + ' has left the room.', room=room)


@socketio.on('response')
def handle_my_custom_event(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type='MESSAGE', room_id=room)

    socketio.emit('response', m.to_json(), room=room)
    



if __name__ == '__main__':
    socketio.run(host='localhost', port=8898, app=app)
    # Threaded option to enable multiple instances for multiple user access support
    # app.run(threaded=True, port=5000)
