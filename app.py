import datetime
import hashlib
import json
import os
import pickle
import random
from collections import defaultdict
from datetime import timezone
from os import path
from time import sleep
from sklearn.base import BaseEstimator, TransformerMixin
import uuid
import flask_login
import flask_socketio
import requests
import spacy as spacy
from flask import Flask, request, render_template, redirect, make_response, url_for
from flask_socketio import join_room, leave_room
from flask_socketio import send
from flask_talisman import Talisman

from constants import JOIN_ROOM, CHAT_MESSAGE, LEAVE_ROOM, WASON_INITIAL, WASON_AGREE, WASON_GAME, USR_ONBOARDING, \
    USR_PLAYING, FINISHED_ONBOARDING, USR_MODERATING, ROUTING_TIMER_STARTED, SYSTEM_USER, SYSTEM_ID, \
    ROUTING_TIMER_ELAPSED, ROOM_READY_TO_START
from data_persistency_utils import read_rooms_from_file, write_rooms_to_file
from message import Room, Message
from postgre_utils import PostgreConnection
from sys_config import DIALOGUES_STABLE
from utils import generate_user, MTurkManagement
from wason_message_processing import get_context_solutions_users

# import eventlet
# eventlet.monkey_patch()


login_manager = flask_login.LoginManager()

app = Flask(__name__, static_url_path='/static')
app.config['SECRET_KEY'] = 'this_secret_key_potato_21_kaxvhsdferfx3d34'
from delitrigger import ChangeOfMindPredictor, Selector
s = Selector('aa')
app.config.update(dict(
    PREFERRED_URL_SCHEME='https'
))

talisman = Talisman(app, content_security_policy=None)
socketio = flask_socketio.SocketIO(app, cors_allowed_origins='*', async_mode='eventlet', logger=True,
                                   engineio_logger=True, always_connect=True)

nlp = spacy.load('en_core_web_sm')

login_manager.init_app(app)


class Selector(BaseEstimator, TransformerMixin):
    """
    Transformer to select a single column from the data frame to perform additional transformations on
    Use on numeric columns in the data
    """

    def __init__(self, key):
        self.key = key

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        transformed = []
        for x in X:
            transformed.append(x[self.key])
        return transformed

class CustomUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == '__main__':
            module = 'delitrigger'
        return super().find_class(module, name)

with open('models/bow.model', 'rb') as f:
    unpickler = CustomUnpickler(f)
    model = unpickler.load()
    CHANGEOFMIND = ChangeOfMindPredictor(model=model)

PG = PostgreConnection('localadasdda_cred.json')
MTURK_MANAGEMENT = MTurkManagement('local_creddadasasd.json')
admin_pass = os.environ.get('ADMIN')
salt = os.environ.get('SALT')

ROOM_STATE_TRACKER = defaultdict()


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
        mturk_info_id = PG.add_initial_mturk_info(assignment, hit, worker, "0d957f51-702c-4882-8475-921d4e4f041d", return_url)
    else:
        mturk_info_id = 0
    ###
    if assignment == 'ASSIGNMENT_ID_NOT_AVAILABLE':
        return render_template("preview.html")

    if wait_room == 'True':
        return render_template('waiting_room.html', data={'ssttmm': start_time,
                                                          'assignment_id': assignment,
                                                          'hit_id': hit,
                                                          'worker_id': worker,
                                                          'turk_submit': return_url,
                                                          'campaign_id': campaign_id})
        # return render_template('onboarding.html', data={
        #                                                 'assignment_id': assignment,
        #                                                 'hit_id': hit,
        #                                                 'worker_id': worker,
        #                                                 'turk_submit': return_url,
        #                                                 'campaign_id': campaign_id})

    active_room_id, type = PG.get_create_campaign_room(campaign_id)
    #
    # print(type)
    # if type == 'chat':
    #     resp = make_response(redirect(
    #         url_for('chatroom', room_id=active_room_id, mturk_info=mturk_info_id, _scheme='https',
    #                 _external=True)))
    # elif type == 'delibot':
    #     resp = make_response(redirect(
    #         url_for('delibot', room_id=active_room_id, mturk_info=mturk_info_id, _scheme='https',
    #                 _external=True)))
    # else:
    #     resp = make_response(redirect(
    #         url_for('delibot2', room_id=active_room_id, mturk_info=mturk_info_id, _scheme='https',
    #                 _external=True)))

    resp = make_response(redirect(url_for('chess_room', room_id=active_room_id, mturk_info=mturk_info_id, _scheme='https',
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
@talisman(

    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def delibot():
    sl = random.randint(0, 2) + random.random()
    sleep(sl)
    room_id = request.args.get('room_id')
    mturk_info_id = request.args.get('mturk_info', None)

    has_user = PG.check_for_user(mturk_info_id=mturk_info_id)
    print("Has user chat room", str(has_user))
    if has_user:
        return render_template('unsuccessful_onboarding.html')

    is_moderator = request.args.get('moderator', False)
    ROOM_STATE_TRACKER[room_id] = {"sol_tracker": [], "current_run": [], 'last_com': 0, 'last_intervention': 0}
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

    return render_template("delibot.html",
                           room_data={'id': room_id, 'name': room.name, 'game': json.loads(wason_initial),
                                      'messages': messages, 'existing_users': logged_users,
                                      'current_user': current_user['user_name'],
                                      'current_user_id': current_user['user_id'],
                                      'current_user_type': user_type,
                                      'current_user_status': status, 'room_status': room.status,
                                      'mturk_return_url': formated_return_url,
                                      # 'mturk_return_url': 'test_post',
                                      "start_time": campaign['start_time']})


@app.route('/delibot2')
@talisman(

    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def delibot2():
    sl = random.randint(0, 2) + random.random()
    sleep(sl)
    room_id = request.args.get('room_id')
    mturk_info_id = request.args.get('mturk_info', None)

    has_user = PG.check_for_user(mturk_info_id=mturk_info_id)
    print("Has user chat room", str(has_user))
    if has_user:
        return render_template('unsuccessful_onboarding.html')

    is_moderator = request.args.get('moderator', False)
    ROOM_STATE_TRACKER[room_id] = {"sol_tracker": [], "current_run": [], 'last_com': 0, 'last_intervention': 0}
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

    return render_template("delibot2.html",
                           room_data={'id': room_id, 'name': room.name, 'game': json.loads(wason_initial),
                                      'messages': messages, 'existing_users': logged_users,
                                      'current_user': current_user['user_name'],
                                      'current_user_id': current_user['user_id'],
                                      'current_user_type': user_type,
                                      'current_user_status': status, 'room_status': room.status,
                                      'mturk_return_url': formated_return_url,
                                      # 'mturk_return_url': 'test_post',
                                      "start_time": campaign['start_time']})


@app.route('/chess_room')
@talisman(
    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def chess_room():

    sl = random.randint(0, 2) + random.random()
    sleep(sl)
    room_id = request.args.get('room_id')
    mturk_info_id = request.args.get('mturk_info', None)

    # has_user = PG.check_for_user(mturk_info_id=mturk_info_id)
    # print("Has user chat room", str(has_user))
    # if has_user:
    #     return render_template('unsuccessful_onboarding.html')

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
    handle_routing(running_dialogue, logged_users, campaign['start_threshold'], campaign['start_time'],
                   campaign['close_threshold'], room.room_id)

    # Have to get the room again, in case the status changed
    room = PG.get_single_room(room_id)
    games = [d.content for d in running_dialogue if d.message_type == WASON_INITIAL][0]
    games = json.loads(games)

    return render_template("generic_room.html", room_data={'id': room_id, 'name': room.name, 'game': games,
                                      'messages': messages, 'existing_users': logged_users,
                                      'current_user': current_user['user_name'],
                                      'current_user_id': current_user['user_id'],
                                      'current_user_type': user_type,
                                      'current_user_status': status, 'room_status': room.status,
                                      'mturk_return_url': formated_return_url,
                                      # 'mturk_return_url': 'test_post',
                                      "start_time": campaign['start_time']})

@app.route('/chess_recruiting')
@talisman(

    frame_options='ALLOW-FROM',
    frame_options_allow_from='https://mturk.com',
)
def chess_recruiting():

    sl = random.randint(0, 2) + random.random()
    sleep(sl)
    mturk_info_id = request.args.get('mturk_info', None)

    has_user = PG.check_for_user(mturk_info_id=mturk_info_id)
    print("Has user chat room", str(has_user))
    if has_user:
        return render_template('unsuccessful_onboarding.html')


    r = Room('recruit'+ uuid.uuid4().hex, campaign='884c71e1-d32b-4403-b46a-be450ec8e693')

    ch = random.choice(['data/games/chess/newpilot.json', 'data/games/chess/pilot.json'])
    with open(ch, 'r') as rf:
        games = json.load(rf)
        random.shuffle(games)
        for g in games:
            random.shuffle(g['moves'])

    PG.create_room(r, game_object=games)

    room = PG.get_single_room(r.room_id)
    room_id = room.room_id
    running_dialogue = PG.get_messages(room.room_id)
    messages = [d for d in running_dialogue if d.message_type == CHAT_MESSAGE]


    campaign = PG.get_campaign(room.campaign)

    current_user = generate_user([], 'recruiting')

    status = USR_ONBOARDING
    m = Message(origin_name=current_user['user_name'], message_type=JOIN_ROOM, room_id=room_id,
                origin_id=current_user['user_id'], user_status=status, user_type='recruiting')
    create_broadcast_message(m)

    formated_return_url = None
    if mturk_info_id:
        PG.update_mturk_user_id(mturk_info_id, current_user['user_id'])
        mturk_info = PG.get_mturk_info(mturk_info_id)
        if mturk_info:
            formated_return_url = '{}/mturk/externalSubmit?assignmentId={}&user_id={}'.format(mturk_info[1],
                                                                                              mturk_info[0],
                                                                                              current_user['user_id'])
    # handle_routing(running_dialogue, logged_users, campaign['start_threshold'], campaign['start_time'],
    #                campaign['close_threshold'], room.room_id)

    # Have to get the room again, in case the status changed
    room = PG.get_single_room(room_id)
    games = [d.content for d in running_dialogue if d.message_type == WASON_INITIAL][0]
    games = json.loads(games)

    return render_template("chess_recruiting.html", room_data={'id': room_id, 'name': room.name, 'game': games,
                                      'messages': messages,
                                      'current_user': current_user['user_name'],
                                      'current_user_id': current_user['user_id'],
                                      'current_user_type': 'recruit',
                                      'current_user_status': status, 'room_status': room.status,
                                      'mturk_return_url': formated_return_url,
                                      # 'mturk_return_url': 'test_post',
                                      "start_time": campaign['start_time']})

@socketio.on('delibot')
def delibot(json):
    room_id = json.get('room_id', None)
    delitype = json.get('delitype', None)

    messages = PG.get_messages(room_id)

    context, solution, users, tracker = get_context_solutions_users(messages, nlp)
    normalised_delitype = delitype.split('_')[1]
    print(normalised_delitype)
    url = 'http://delibot.cl.cam.ac.uk/delibot'
    myobj = {"delitype": normalised_delitype,
             "context": context[-2:],
             "cards": solution,
             "users": users,
             "skip": context}

    print(myobj)

    x = requests.post(url, json=myobj)

    print(x.text)

    m = Message(origin_id=990, origin_name='DEliBot', message_type='CHAT_MESSAGE', room_id=room_id,
                content={'message': x.text}, user_status=USR_PLAYING, user_type='DELIBOT_SIMILARITY')
    create_broadcast_message(m)


def test_callback():
    print("Called")


def create_broadcast_message(message):
    print("Broadcasting", message.content, message.message_type)
    PG.insert_message(message)
    socketio.emit('response', message.to_json(), room=message.room_id, callback=test_callback)


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
        campaign_name = PG.get_campaign(camp)['name']
        room = Room(room_name, campaign=camp)
        with open('data/games/chess/newpilot.json', 'r') as rf:
            games = json.load(rf)
            random.shuffle(games)
            for g in games:
                random.shuffle(g['moves'])
        if 'chess' in campaign_name:
            PG.create_room(room, game_object=games)
        else:
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
    print("redirected to JOIN")
    room = data['room']
    print(room)
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
    # ROOM_READY_TO_START indicates that the routing timer has elapsed
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
        elif (item.message_type == WASON_AGREE or item.message_type == "SUBMITTED_ALL") and item.user_status == usr_status:
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
        elif item.message_type == WASON_AGREE or item.message_type == "GAME_SUBMIT":
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
            user_activity[user] = difference.total_seconds() <= 240

    if routing_threshold is not None and routing_threshold is True:
        for user, activity in user_activity.items():
            if not activity:
                # m = Message(origin_name='AUTO_KICKED', message_type=LEAVE_ROOM, room_id=room_id, origin_id=user,
                #             user_status='AUTO_KICKED')
                # create_broadcast_message(m)
                # TODO: Re-enable user kicking
                pass
                # all_messages = PG.get_messages(room_id)
                # validate_finish_game(all_messages, room_id)

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
def handle_response(json):
    print('redirected to response')
    print('received my event: ' + str(json))
    room_id = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
                content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))

    create_broadcast_message(m)
    all_messages = PG.get_messages(room_id)

    handle_room_events(all_messages, room_id, m)

    validate_finish_game(all_messages, room_id)


def check_if_can_speak(all_messages):
    can_delibot_speak = True
    time_since_delitrigger = 0
    for item in all_messages:
        if item.message_type == 'DELIBOT_TRIGGER':
            can_delibot_speak = False
            time_since_delitrigger = 0

        if item.origin == 'DEliBot':
            can_delibot_speak = True
        if can_delibot_speak is False:
            time_since_delitrigger += 1
        if time_since_delitrigger >= 6:
            can_delibot_speak = True
            time_since_delitrigger = 0

    return can_delibot_speak


@socketio.on('deliresponse_old')
def handle_response_old(json):
    print('redirected to response')
    print('received my event: ' + str(json))
    room_id = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
                content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))

    create_broadcast_message(m)
    all_messages = PG.get_messages(room_id)
    handle_room_events(all_messages, room_id, m)
    validate_finish_game(all_messages, room_id)

    context, solution, users, tracker = get_context_solutions_users(all_messages, nlp)

    print("Tracker: ", str(tracker))
    print("Users: ", str(users))

    check = check_if_can_speak(all_messages)
    if 'delibot' not in set(users[-3:]) and len(tracker) >= 4 and check:
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type='DELIBOT_TRIGGER', room_id=room_id,
                    content={'message': None}, user_status=None, user_type='SYSTEM')
        create_broadcast_message(m)

        url = 'http://delibot.cl.cam.ac.uk/delibot2'
        myobj = {
            "context": context[-2:],
            "cards": solution,
            "users": users,
            "skip": context}

        print(myobj)
        x = requests.post(url, json=myobj)
        print(x.text)

        # Second check before uttering to make sure that nothing changed since the last time
        all_messages = PG.get_messages(room_id)
        context, solution, users, tracker = get_context_solutions_users(all_messages, nlp)
        if 'delibot' not in set(users[-3:]) and len(tracker) >= 4:
            m = Message(origin_id=990, origin_name='DEliBot', message_type='CHAT_MESSAGE', room_id=room_id,
                        content={'message': x.text}, user_status=USR_PLAYING, user_type='DELIBOT_SIMILARITY')
            create_broadcast_message(m)


@socketio.on("post_feedback")
def handle_feedback(json):
    PG.record_feedback(json['room'], json['user_id'], json['content'])
    # user_id: global_user_id,
    # user_name: user_name,
    # content: answersJson,
    # room: room_id

    pass


@socketio.on('deliresponse2')
def handle_response_2(json):

    print('redirected to response @ DELIBOT 2')
    print('received my event: ' + str(json))
    room_id = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
                content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))

    create_broadcast_message(m)
    all_messages = PG.get_messages(room_id)
    handle_room_events(all_messages, room_id, m)
    validate_finish_game(all_messages, room_id)

    context, solution, users, tracker, participation = get_context_solutions_users(all_messages, nlp)
    ROOM_STATE_TRACKER[room_id]["sol_tracker"] = tracker
    ROOM_STATE_TRACKER[room_id]["current_run"].append(tracker[-1])
    has_com, meta_obj = CHANGEOFMIND.predict_change_of_mind(context, ROOM_STATE_TRACKER[room_id]["current_run"],
                                                            len(context), participation)

    if has_com == 1:
        ROOM_STATE_TRACKER[room_id]["current_run"] = []
        ROOM_STATE_TRACKER[room_id]["last_com"] = 0
    else:
        ROOM_STATE_TRACKER[room_id]["last_com"] += 1

    check = check_if_can_speak(all_messages)
    if check and (
            (ROOM_STATE_TRACKER[room_id]["last_intervention"] >= 3 and ROOM_STATE_TRACKER[room_id]["last_com"] >= 2) or
            ROOM_STATE_TRACKER[room_id]["last_intervention"] >= 5 or len(context) == 3):
        ROOM_STATE_TRACKER[room_id]["last_intervention"] = 0
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type='DELIBOT_TRIGGER', room_id=room_id,
                    content=meta_obj, user_status=None, user_type='SYSTEM')
        create_broadcast_message(m)

        url = 'http://delibot.cl.cam.ac.uk/delibot4'
        myobj = {
            "context": context,
            "cards": solution,
            "users": users,
            "skip": context,
            "participation_feats": participation}

        print(myobj)
        x = requests.post(url, json=myobj)
        print(x)

        m = Message(origin_id=990, origin_name='DEliBot', message_type='CHAT_MESSAGE', room_id=room_id,
                    content={'message': x.json()['text'], 'meta': x.json()['meta']}, user_status=USR_PLAYING,
                    user_type='DELIBOT_2')
        create_broadcast_message(m)

    else:
        ROOM_STATE_TRACKER[room_id]["last_intervention"] += 1


@socketio.on('deliresponse')
def handle_response(json):
    print('redirected to response @ DELIBOT 1')
    print('received my event: ' + str(json))
    room_id = json['room']
    m = Message(origin_id=json['user_id'], origin_name=json['user_name'], message_type=json['type'], room_id=room_id,
                content=json['message'], user_status=json['user_status'], user_type=json.get('user_type', None))

    create_broadcast_message(m)
    all_messages = PG.get_messages(room_id)
    handle_room_events(all_messages, room_id, m)
    validate_finish_game(all_messages, room_id)

    context, solution, users, tracker, participation = get_context_solutions_users(all_messages, nlp)
    ROOM_STATE_TRACKER[room_id]["sol_tracker"] = tracker
    ROOM_STATE_TRACKER[room_id]["current_run"].append(tracker[-1])
    # has_com, meta_obj = CHANGEOFMIND.predict_change_of_mind(context, ROOM_STATE_TRACKER[room_id]["current_run"],
    #                                                         len(context))
    has_com = 0
    meta_obj = {"type": "hardcoded_every3utterances"}
    if has_com == 1:
        ROOM_STATE_TRACKER[room_id]["current_run"] = []
        ROOM_STATE_TRACKER[room_id]["last_com"] = 0
    else:
        ROOM_STATE_TRACKER[room_id]["last_com"] += 1

    check = check_if_can_speak(all_messages)
    if check and ROOM_STATE_TRACKER[room_id]["last_intervention"] >= 2:
        # ((ROOM_STATE_TRACKER[room_id]["last_intervention"] >= 5 and ROOM_STATE_TRACKER[room_id]["last_com"] >= 5) or
        #  ROOM_STATE_TRACKER[room_id]["last_intervention"] >= 10):
        ROOM_STATE_TRACKER[room_id]["last_intervention"] = 0
        m = Message(origin_id=-1, origin_name='SYSTEM', message_type='DELIBOT_TRIGGER', room_id=room_id,
                    content=meta_obj, user_status=None, user_type='SYSTEM')
        create_broadcast_message(m)

        url = 'http://delibot.cl.cam.ac.uk/delibot3'
        myobj = {
            "context": context,
            "cards": solution,
            "users": users,
            "skip": context,
            "participation_feats": participation}

        print(myobj)
        x = requests.post(url, json=myobj)
        print(x)

        m = Message(origin_id=990, origin_name='DEliBot', message_type='CHAT_MESSAGE', room_id=room_id,
                    content={'message': x.json()['text'], 'meta': x.json()['meta']}, user_status=USR_PLAYING,
                    user_type='DELIBOT_RC1')
        create_broadcast_message(m)

    else:
        ROOM_STATE_TRACKER[room_id]["last_intervention"] += 1

def validate_finish_game(all_messages, room_id):
    room = PG.get_single_room(room_id)
    finished_onboarding = check_finished(all_messages, USR_ONBOARDING, room.status)
    if finished_onboarding:
        m = Message(origin_id=SYSTEM_ID, origin_name=SYSTEM_USER, message_type=FINISHED_ONBOARDING, room_id=room_id,
                    content=30)
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
    from delitrigger import ChangeOfMindPredictor, Selector

    from sklearn.base import BaseEstimator, TransformerMixin


    class Selector(BaseEstimator, TransformerMixin):
        """
        Transformer to select a single column from the data frame to perform additional transformations on
        Use on numeric columns in the data
        """

        def __init__(self, key):
            self.key = key

        def fit(self, X, y=None):
            return self

        def transform(self, X):
            transformed = []
            for x in X:
                transformed.append(x[self.key])
            return transformed
    s = Selector('aa')
    with open('models/bow_full_delidata_withparticipation.model', 'rb') as f:
        CHANGEOFMIND = pickle.load(f, fix_imports=True)
    app.run(port=8898, ssl_context='adhoc')
    try:
        socketio.run(host='localhost', port=8898, app=app, log_output=True)
    finally:
        print("Exiting gracefully")
        # save_state()
