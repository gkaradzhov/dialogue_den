import datetime
import hashlib
import json
import os
import random
import signal
from datetime import timezone
from os import path
import requests
import flask_login
import flask_socketio
from flask import Flask, request, render_template, redirect, make_response, url_for
from flask_socketio import join_room, leave_room
from flask_socketio import send
from flask_talisman import Talisman

from constants import JOIN_ROOM, CHAT_MESSAGE, LEAVE_ROOM, WASON_INITIAL, WASON_AGREE, WASON_GAME, WASON_FINISHED, \
    USR_ONBOARDING, USR_PLAYING, FINISHED_ONBOARDING, USR_MODERATING, ROUTING_TIMER_STARTED, SYSTEM_USER, SYSTEM_ID, \
    ROUTING_TIMER_ELAPSED, ROOM_READY_TO_START
from data_persistency_utils import read_rooms_from_file, write_rooms_to_file
from message import Room, Message
from postgre_utils import PostgreConnection
from sys_config import DIALOGUES_STABLE
from utils import generate_user, MTurkManagement
from time import sleep
import random


login_manager = flask_login.LoginManager()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'this_secret_key_potato_21_kaxvhsdferfx3d34'

app.config.update(dict(
    PREFERRED_URL_SCHEME='https'
))

talisman = Talisman(app, content_security_policy=None)
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

login_manager.init_app(app)

PG = PostgreConnection('localadasdda_cred.json')
MTURK_MANAGEMENT = MTurkManagement('local_creddadasasd.json')
admin_pass = os.environ.get('ADMIN')
salt = os.environ.get('SALT')


class User(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(email):
    user = User()
    user.id = 'moderator'
    return user


@login_manager.request_loader
def request_loader(request):
    user = request.form.get('user')
    if user != 'moderator':
        return

    user = User()
    user.id = 'moderator'

    form_pass = request.form['password']
    adm = hashlib.sha512((admin_pass + salt).encode())
    user.is_authenticated = hashlib.sha512(form_pass + salt).hexdigest() == adm.hexdigest()

    return user


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return '''
               <form action='login' method='POST'>
                <input type='text' name='user' id='user' placeholder='user'/>
                <input type='password' name='password' id='password' placeholder='password'/>
                <input type='submit' name='submit'/>
               </form>
               '''

    email = request.form['user']
    form_pass = request.form['password']
    adm = hashlib.sha512((admin_pass + salt).encode())
    if hashlib.sha512((form_pass + salt).encode()).hexdigest() == adm.hexdigest():
        user = User()
        user.id = email
        flask_login.login_user(user)
        return redirect('/rooms')

    return 'Bad login'


def trigger_finish(room_data):
    room_id = room_data[0].room_id

    PG.mark_room_done(room_id)

    # 1. Save the dialogue to dialogues_stable
    filepath = path.join(DIALOGUES_STABLE, room_id)
    with open(filepath, 'w') as wf:
        for item in room_data:
            wf.writelines(item.to_json() + '\n')

    # 2. Mark room as closed
    existing_rooms = read_rooms_from_file()
    for room in existing_rooms:
        if room.room_id == room_id:
            room.is_done = True
    write_rooms_to_file(existing_rooms)


# A welcome message to test our server
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/route', methods=['GET', 'POST'])
@talisman(
    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def route_to_room():
    sl = random.randint(0, 2) + random.random()
    sleep(sl)

    # Route room options
    wait_room = request.args.get("hw", None)  # HW = has waiting room
    start_time = request.args.get('ssttmm', None)

    # Get Mturk data
    assignment = request.args.get('assignmentId', 0)
    campaign_id = request.args.get('campaign', None)
    hit = request.args.get('hitId', None)
    worker = request.args.get('workerId', None)
    return_url = request.args.get('turkSubmitTo', None)

    if assignment != '0' and assignment != 0:
        mturk_info_id = PG.add_initial_mturk_info(assignment, hit, worker, campaign_id, return_url)
    else:
        mturk_info_id = 0
    ###
    if assignment == 'ASSIGNMENT_ID_NOT_AVAILABLE':
        return render_template("preview.html")

    if wait_room == 'True':
        # return render_template('waiting_room.html', data={'ssttmm': start_time,
        #                                                   'assignment_id': assignment,
        #                                                   'hit_id': hit,
        #                                                   'worker_id': worker,
        #                                                   'turk_submit': return_url,
        #                                                   'campaign_id': campaign_id})
        return render_template('onboarding.html', data={ 'assignment_id': assignment,
                                                          'hit_id': hit,
                                                          'worker_id': worker,
                                                          'turk_submit': return_url,
                                                          'campaign_id': campaign_id})

    active_room_id = PG.get_create_campaign_room(campaign_id)

    resp = make_response(redirect(
        url_for('chatroom', room_id=active_room_id, mturk_info=mturk_info_id, _scheme='https',
                _external=True)))
    return resp

@app.route('/unsuccessful_onboarding')
@talisman(
    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def unsuccessful_onboarding():
    return render_template('unsuccessful_onboarding.html')


@app.route('/rooms')
@flask_login.login_required
def list_rooms():
    existing_rooms = PG.get_active_rooms()
    return render_template('home.html', chat_rooms=existing_rooms)


def handle_routing(messages, logged_users, start_threshold, start_time, close_threshold, room_id):
    timer_started = False
    for m in messages:
        if m.message_type == ROUTING_TIMER_STARTED:
            timer_started = True
    if timer_started is False and (len(logged_users) + 1) >= start_threshold:
        PG.set_room_status(room_id, ROUTING_TIMER_STARTED)

        m = Message(origin_name=SYSTEM_USER, message_type=ROUTING_TIMER_STARTED, room_id=room_id,
                    origin_id=SYSTEM_ID, content=start_time)
        create_broadcast_message(m)

    if (len(logged_users) + 1) >= close_threshold:
        PG.set_room_status(room_id, ROOM_READY_TO_START)


@app.route('/room')
@talisman(

    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def chatroom():
    sl = random.randint(0, 2) + random.random()
    sleep(sl)
    room_id = request.args.get('room_id')
    mturk_info_id = request.args.get('mturk_info', None)

    has_user = PG.check_for_user(mturk_info_id=mturk_info_id)
    print("Has user chat room", str(has_user))
    if has_user:
        return render_template('unsuccessful_onboarding.html')

    is_moderator = request.args.get('moderator', False)

    room = PG.get_single_room(room_id)
    running_dialogue = PG.get_messages(room.room_id)
    messages = [d for d in running_dialogue if d.message_type == CHAT_MESSAGE]

    logged_users = set()
    for item in running_dialogue:
        if item.message_type == JOIN_ROOM:
            logged_users.add((item.origin, item.origin_id))
        elif item.message_type == LEAVE_ROOM and (item.origin, item.origin_id) in logged_users:
            logged_users.remove((item.origin, item.origin_id))

    user_type = 'participant'
    if is_moderator == "True":
        user_type = 'moderator'

    campaign = PG.get_campaign(room.campaign)

    if len(logged_users) == 0:
        random_float = random.random()
        if random_float < campaign['user_moderator_chance']:
            user_type = 'human_delibot'

    current_user = generate_user([d[0] for d in logged_users], user_type)

    if is_moderator:
        status = USR_MODERATING
    else:
        status = USR_ONBOARDING
    m = Message(origin_name=current_user['user_name'], message_type=JOIN_ROOM, room_id=room_id,
                origin_id=current_user['user_id'], user_status=status, user_type=user_type)
    create_broadcast_message(m)

    formated_return_url = None
    if mturk_info_id:
        PG.update_mturk_user_id(mturk_info_id, current_user['user_id'])
        mturk_info = PG.get_mturk_info(mturk_info_id)
        if mturk_info:
            formated_return_url = '{}/mturk/externalSubmit?assignmentId={}&user_id={}'.format(mturk_info[1],
                                                                                              mturk_info[0],
                                                                                              current_user['user_id'])


    wason_initial = [d.content for d in running_dialogue if d.message_type == WASON_INITIAL][0]

    handle_routing(running_dialogue, logged_users, campaign['start_threshold'], campaign['start_time'],
                   campaign['close_threshold'], room.room_id)

    # Have to get the room again, in case the status changed
    room = PG.get_single_room(room_id)

    return render_template("room.html", room_data={'id': room_id, 'name': room.name, 'game': json.loads(wason_initial),
                                                   'messages': messages, 'existing_users': logged_users,
                                                   'current_user': current_user['user_name'],
                                                   'current_user_id': current_user['user_id'],
                                                   'current_user_type': user_type,
                                                   'current_user_status': status, 'room_status': room.status,
                                                   'mturk_return_url': formated_return_url,
                                                   # 'mturk_return_url': 'test_post',
                                                   "start_time": campaign['start_time']})


@app.route('/delibot')
# @talisman(
#     frame_options='ALLOW-FROM',
#     frame_options_allow_from='https://mturk.com',
# )
def delibot():
    room_id = request.args.get('room_id', None)
    delitype = request.args.get('delitype', None)

    normalised_delitype = delitype.split('_')[1]
    print(normalised_delitype)
    url = 'http://delibot.cl.cam.ac.uk/delibot'
    myobj = {"delitype": normalised_delitype,
             "context": ["hey", "maybe turning A"],
             "cards": ["A", "3", "4"], "users": ["Narwhal"]}


    x = requests.post(url, json=myobj)

    print(x.text)
    # s = speak_similarity('Moderation', ['Hey how are you', 'I am well thanks'], cards=['A', 'A', '3'],
    #                      users=['Dolphin'], all_utterances=processed, processor=dialogue)

    # room_id = json['room']
    # m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
    #             content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))
    #
    # create_broadcast_message(m)
    # return s
    return None

def create_broadcast_message(message):
    PG.insert_message(message)
    socketio.emit('response', message.to_json(), room=message.room_id)


@app.route('/create_room', methods=('GET', 'POST'))
@flask_login.login_required
def create_room():
    room_name = request.form.get('room_name', None)
    if room_name is None:
        campaigns = PG.get_campaigns()

        return render_template("create_room.html", data={'campaigns': campaigns})
    else:
        camp = request.form.get('campaign', None)
        print(camp)
        room = Room(room_name, campaign=camp)

        PG.create_room(room)
        return redirect('/rooms')


@app.route('/compensation', methods=['GET', 'POST'])
@talisman(
    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def compensation_page():
    assignment = request.args.get('assignmentId', None)
    hit = request.args.get('hitId', None)
    worker = request.args.get('workerId', None)
    return_url = request.args.get('turkSubmitTo', None)
    formated_return_url = '{}/mturk/externalSubmit?assignmentId={}&user_id={}'.format(return_url, assignment, worker)

    return render_template("compensation.html", room_data={'mturk_return_url': formated_return_url})


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
    status = data['user_status']
    type = data.get('user_type', None)

    leave_room(room)

    m = Message(origin_name=username, message_type=LEAVE_ROOM, room_id=room, origin_id=user_id, user_status=status,
                user_type=type)
    create_broadcast_message(m)

    all_messages = PG.get_messages(room)
    validate_finish_game(all_messages, room)
    print("User {} has left the room {}".format(username, room))


def check_finished(room_history, usr_status, room_status):
    if usr_status == USR_ONBOARDING and room_status != ROOM_READY_TO_START:
        return False
    logged_users = {}
    for item in room_history:
        if item.user_status == USR_MODERATING or item.user_type == 'human_delibot':
            continue
        if usr_status == USR_ONBOARDING and item.message_type == FINISHED_ONBOARDING:
            # No need to check, already finished onboarding
            return False
        if item.message_type == LEAVE_ROOM and item.origin_id in logged_users:
            if item.origin_id in logged_users:
                del logged_users[item.origin_id]
        elif item.message_type == WASON_AGREE and item.user_status == usr_status:
            logged_users[item.origin_id] = True
        elif item.message_type == WASON_GAME or item.message_type == JOIN_ROOM:
            logged_users[item.origin_id] = False
    for user, outcome in logged_users.items():
        if not outcome:
            return False
    return True


def handle_room_events(room_messages, room_id, last_message):
    room = PG.get_single_room(room_id)
    campaign = PG.get_campaign(room.campaign)

    logged_users = {}
    submitted_users = {}
    room_status = None
    routing_timer_timestamp = None
    timer_ended = False
    timer_ended_timestamp = None
    for item in room_messages:
        if item.user_status == USR_MODERATING or item.user_type == 'human_delibot':
            continue
        if item.message_type == JOIN_ROOM:
            logged_users[item.origin_id] = item.timestamp
        elif item.message_type == LEAVE_ROOM:
            if item.origin_id in logged_users:
                del logged_users[item.origin_id]
        elif item.message_type == ROUTING_TIMER_STARTED:
            routing_timer_timestamp = item.timestamp
        elif item.message_type == ROUTING_TIMER_ELAPSED:
            timer_ended = True
            timer_ended_timestamp = item.timestamp
        elif item.message_type == WASON_AGREE:
            submitted_users[item.origin_id] = True
            if item.origin_id in logged_users:
                logged_users[item.origin_id] = item.timestamp
        else:
            if item.origin_id in logged_users:
                logged_users[item.origin_id] = item.timestamp

    # Kick inactive:
    user_activity = {}
    now = datetime.datetime.now(timezone.utc)
    if routing_timer_timestamp:
        routing_threshold = now - routing_timer_timestamp
        routing_threshold = routing_threshold.total_seconds() >= 120
    else:
        routing_threshold = None

    for user, last_active in logged_users.items():
        if user in submitted_users:
            difference = now - last_active
            user_activity[user] = difference.total_seconds() <= 545
        else:
            difference = now - last_active
            user_activity[user] = difference.total_seconds() <= 120

    if routing_threshold is not None and routing_threshold is True:
        for user, activity in user_activity.items():
            if not activity:
                m = Message(origin_name='AUTO_KICKED', message_type=LEAVE_ROOM, room_id=room_id, origin_id=user,
                            user_status='AUTO_KICKED')
                create_broadcast_message(m)

                all_messages = PG.get_messages(room_id)
                validate_finish_game(all_messages, room_id)

    if routing_timer_timestamp and not timer_ended:
        time_since_start = now - routing_timer_timestamp
        auto_ellapse = time_since_start.total_seconds() >= (campaign['start_threshold'] * 60 + 10)
        if auto_ellapse:
            m = Message(origin_id=-1, origin_name="SYSTEM", message_type=ROUTING_TIMER_ELAPSED, room_id=room_id,
                        user_status='SYSTEM')
            create_broadcast_message(m)
    else:
        auto_ellapse = False

    if last_message.message_type == ROUTING_TIMER_ELAPSED or auto_ellapse:
        PG.set_room_status(room_id, 'READY_TO_START')
    return room_status


@socketio.on('response')
def handle_response(json, methods=('GET', 'POST')):
    print('received my event: ' + str(json))
    room_id = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
                content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))

    create_broadcast_message(m)
    all_messages = PG.get_messages(room_id)

    handle_room_events(all_messages, room_id, m)

    validate_finish_game(all_messages, room_id)


def validate_finish_game(all_messages, room_id):
    room = PG.get_single_room(room_id)
    finished_onboarding = check_finished(all_messages, USR_ONBOARDING, room.status)
    if finished_onboarding:
        m = Message(origin_id=SYSTEM_ID, origin_name=SYSTEM_USER, message_type=FINISHED_ONBOARDING, room_id=room_id,
                    content=7)
        create_broadcast_message(m)
        PG.set_room_status(room_id, 'FINISHED_ONBOARDING')

    finished_game = check_finished(all_messages, USR_PLAYING, room.status)

    if finished_game and room.status != "FINISHED_GAME":
        pass
        # m = Message(origin_id=SYSTEM_ID, origin_name=SYSTEM_USER, message_type=WASON_FINISHED, room_id=room_id)
        # create_broadcast_message(m)
        # all_messages.append(m)
        #
        # outro_content = "Thank you for your participation! Please fill " \
        #                 "<a target='_blank' href='https://sheffieldpsychology.eu.qualtrics.com/jfe/form/SV_0ibJOwF7AiNXFfT?roomid={0}'>this questionnaire</a>".format(
        #     room_id)
        # outro_message = Message(origin_id=SYSTEM_ID, origin_name=SYSTEM_USER, message_type=CHAT_MESSAGE,
        #                         room_id=room_id, content={'annotation': 'no_annotation', 'message': outro_content})
        #
        # create_broadcast_message(outro_message)
        # all_messages.append(m)
        # PG.set_room_status(room_id, 'FINISHED_GAME')


def handle_signals():
    print("Handling Signal")
    # save_state()


if __name__ == '__main__':
    app.run()
    try:
        socketio.run(host='localhost', port=8898, app=app)
    finally:
        print("Exiting gracefully")
        # save_state()
