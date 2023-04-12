import ast
import traceback

from nltk.tokenize import TweetTokenizer
import copy
import string
import pandas as pd
import os, csv
from collections import Counter, defaultdict

allowed = {
    'vowels': {'A', 'O', 'U', 'E', 'I', 'Y'},
    'consonants': {'B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'X', 'Z', 'W'},
    'odds': {'1', '3', '5', '7', '9'},
    'evens': {'0', '2', '4', '6', '8'}
}


# all cards with vowels on one side have even numbers on the other
# To prove the rule, one should turn the vowel and the odd number
def is_solution_absolute(state):
    for item in state:
        if (item['value'] in allowed['vowels'] or item['value'] in allowed['odds']):
            if item['checked'] is False:
                return (0, 'WRONG')
            else:
                continue
        elif item['checked'] is True:
            return (0, 'WRONG')
    return (1, 'CORRECT')


def is_solution_fine_grained(state):
    checked_dict = {'vowels': False, 'consonants': False, 'odds': False, 'evens': False}

    if isinstance(state, list):
        for item in state:
            for checked in checked_dict.keys():
                if item['value'] in allowed[checked] and item['checked'] is True:
                    checked_dict[checked] = True
    else:
        for item in state:
            for checked in checked_dict.keys():
                if item in allowed[checked]:
                    checked_dict[checked] = True

    score = 0
    classification = 'OTHER_ERROR'
    for key, item in checked_dict.items():
        if key == 'vowels' and item:
            score += 0.25
        elif key == 'odds' and item:
            score += 0.25
        elif key == 'consonants' and not item:
            score += 0.25
        elif key == 'evens' and not item:
            score += 0.25

    if score == 1:
        classification = 'CORRECT'
    elif score == 0:
        classification = 'ALL_INCORRECT'

    if checked_dict['vowels'] and checked_dict['evens']:
        if checked_dict['odds']:
            classification = 'BIASED + ODDS'
        elif checked_dict['consonants']:
            classification = 'BIASED + CONST'
        else:
            classification = 'BIASED'

    if all(value for value in checked_dict.values()):
        classification = 'ALL_CHECKED'

    if all(value is False for value in checked_dict.values()):
        classification = 'NONE_CHECKED'

    return score, classification


class WasonMessage:
    def __init__(self, origin, content, annotation_obj, identifier, type='MESSAGE'):
        self.identifier = identifier
        self.origin = origin
        self.content = content
        self.annotation = annotation_obj
        self.content_tokenised = []
        self.content_pos = []
        self.clean_text = ""
        self.type = type

    def merge_annotations(self, external_annotation_object):
        new_ann_dict = {**self.annotation, **external_annotation_object}
        self.annotation = new_ann_dict


class WasonConversation:
    def __init__(self, identifier):
        self.raw_db_conversation = []
        self.wason_messages = []
        self.identifier = identifier
        self.tknzr = TweetTokenizer()

    def preprocess_everything(self, tagger):
        for item in self.wason_messages:
            content = item.content
            for raw in self.raw_db_conversation:
                if item.identifier == raw['message_id']:
                    content = raw['content']['message']
            doc = tagger(content)
            item.content_pos = [a.pos_ for a in doc]
            item.content_tokenised = self.tknzr.tokenize(content)

    def clean_special_tokens(self):
        initial_cards = self.get_initial_cards()
        users = self.get_users()
        users_upper = [u.upper() for u in users if u != 'SYSTEM']
        for item in self.wason_messages:
            clean_tokens = []
            for token in item.content_tokenised:
                if token.upper() in initial_cards:
                    clean_tokens.append('<CARD>')
                elif token.upper().replace('@', '') in users_upper:
                    clean_tokens.append('<MENTION>')
                else:
                    clean_tokens.append(token)

            item.clean_text = " ".join(clean_tokens)

    def get_initial_cards(self):
        cards = set()
        for rm in self.raw_db_conversation:
            if rm['message_type'] == "WASON_INITIAL":
                cards.update([l['value'] for l in rm['content']])
                break
        return cards

    def get_users(self):
        users = set()
        for item in self.wason_messages:
            users.add(item.origin)
        return users

    def wason_messages_from_raw(self):
        self.wason_messages = []
        for m in self.raw_db_conversation:
            if m['message_type'] == 'CHAT_MESSAGE':
                self.wason_messages.append(WasonMessage(origin=m['user_name'],
                                                        content=m['content'],
                                                        identifier=m['message_id'],
                                                        annotation_obj={}))

    def to_street_crowd_format(self):
        data = []
        for count, item in enumerate(self.wason_messages):
            data.append((item.origin, " ".join(item.content_tokenised), " ".join(item.content_pos), count))

        return data

    def get_wason_from_raw(self, raw_message):
        processed_message = [m for m in self.wason_messages if m.identifier == raw_message['message_id']]
        if len(processed_message) == 0:
            return None
        return processed_message[0]

    def merge_all_annotations(self, external_conversation):
        for internal, external in zip(self.wason_messages, external_conversation.wason_messages):
            if internal.identifier == external.identifier:
                internal.merge_annotations(external.annotation)
            else:
                print("Internal != External: {} {}".format(internal.identifier, external.identifier))


allowed = {
    'vowels': {'A', 'O', 'U', 'E', 'I', 'Y'},
    'consonants': {'B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'X', 'Z', 'W'},
    'odds': {'1', '3', '5', '7', '9'},
    'evens': {'0', '2', '4', '6', '8'}
}


def extract_from_message(wason_message: WasonMessage, initial_cards, annotations=None):
    mentioned_cards = set()
    for token, pos in zip(wason_message.content_tokenised, wason_message.content_pos):
        stripped = token.translate(str.maketrans('', '', string.punctuation))

        if stripped.upper() in initial_cards:
            mentioned_cards.add(stripped.upper())
        elif stripped == 'all':
            mentioned_cards.update(initial_cards)

    if mentioned_cards:
        return "RAW_MENTION", mentioned_cards
    else:
        return 'NotFound', {'0'}


def is_solution_fine_grained(state):
    checked_dict = {'vowels': False, 'consonants': False, 'odds': False, 'evens': False}

    if isinstance(state, list):
        for item in state:
            for checked in checked_dict.keys():
                if item['value'] in allowed[checked] and item['checked'] is True:
                    checked_dict[checked] = True
    else:
        for item in state:
            for checked in checked_dict.keys():
                if item in allowed[checked]:
                    checked_dict[checked] = True

    score = 0
    classification = 'OTHER_ERROR'
    for key, item in checked_dict.items():
        if key == 'vowels' and item:
            score += 0.25
        elif key == 'odds' and item:
            score += 0.25
        elif key == 'consonants' and not item:
            score += 0.25
        elif key == 'evens' and not item:
            score += 0.25

    if score == 1:
        classification = 'CORRECT'
    elif score == 0:
        classification = 'ALL_INCORRECT'

    if checked_dict['vowels'] and checked_dict['evens']:
        if checked_dict['odds']:
            classification = 'BIASED + ODDS'
        elif checked_dict['consonants']:
            classification = 'BIASED + CONST'
        else:
            classification = 'BIASED'

    if all(value for value in checked_dict.values()):
        classification = 'ALL_CHECKED'

    if all(value is False for value in checked_dict.values()):
        classification = 'NONE_CHECKED'

    return score, classification


def solution_tracker(wason_conversation, include_annotations=True, agreement_classifier=None):
    solution_tracker = []
    initial_submissions = {}
    initial_cards = set()

    last_solution = set('0')
    is_solution_proposed_last = False
    last_partial = False
    message_count = 0
    total_length = len(wason_conversation.wason_messages)

    for rm in wason_conversation.raw_db_conversation:
        if rm['message_type'] == "WASON_INITIAL":
            initial_cards.update([l['value'] for l in rm['content']])

        if rm['message_type'] == 'WASON_SUBMIT':
            initial_submissions[rm['user_name']] = set([l['value'] for l in rm['content'] if l['checked']])

        if rm['message_type'] == 'FINISHED_ONBOARDING':
            break

    # Populate initial submissions
    for user, item in initial_submissions.items():
        solution_tracker.append({'type': "INITIAL",
                                 'content': "INITIAL",
                                 'user': user,
                                 'value': item,
                                 'id': -1
                                 })

    # Start tracking conversation

    for item in wason_conversation.raw_db_conversation:
        if item['user_status'] != 'USR_PLAYING':
            continue

        if item['message_type'] == 'WASON_SUBMIT':
            solution_tracker.append({'type': "SUBMIT",
                                     'content': "SUBMIT",
                                     'user': item['user_name'],
                                     'value': set([l['value'] for l in item['content'] if l['checked']]),
                                     'id': item['message_id']
                                     })

        if item['message_type'] == 'CHAT_MESSAGE':
            message_count += 1
            wason_message = wason_conversation.get_wason_from_raw(item)
            if not wason_message:
                continue

            if include_annotations:
                if not wason_message.annotation:
                    continue
                if (wason_message.annotation['target'] in ['Reasoning', 'Disagree', 'Moderation']
                    or wason_message.annotation['type'] == 'Probing') \
                        and len({'partial_solution', 'complete_solution', 'solution_summary'}.intersection(
                    wason_message.annotation['additional'])) == 0:
                    is_solution_proposed_last = False

                cards = {'0'}
                if len({'partial_solution', 'complete_solution', 'solution_summary'}.intersection(
                        wason_message.annotation['additional'])) >= 1:
                    type, cards = extract_from_message(wason_message, initial_cards)

                    if cards != {'0'}:
                        if 'partial_solution' in wason_message.annotation['additional'] and last_solution != {'0'}:
                            if last_partial:
                                last_solution.update(cards)
                                cards = last_solution
                            else:
                                last_partial = True
                                last_solution = cards
                        else:
                            last_solution = cards
                            last_partial = False
                        is_solution_proposed_last = True

                # if cards == {'0'} and wason_message.annotation['target'] == 'Agree' and is_solution_proposed_last:
                #     cards = last_solution

                if len({'partial_solution', 'complete_solution', 'solution_summary'}.intersection(
                        wason_message.annotation['additional'])) >= 1:
                    # or wason_message.annotation['target'] == 'Agree':

                    if cards != {'0'}:
                        solution_tracker.append({'type': "MENTION",
                                                 'content': wason_message.content,
                                                 'user': item['user_name'],
                                                 'value': cards,
                                                 'id': item['message_id'],
                                                 'pos': message_count / total_length
                                                 })
            else:
                type, cards = extract_from_message(wason_message, initial_cards)
                # print(cards)
                if cards != {'0'}:
                    solution_tracker.append({'type': "MENTION",
                                             'content': wason_message.content,
                                             'user': item['user_name'],
                                             'value': cards,
                                             'id': item['message_id'],
                                             'pos': message_count / total_length
                                             })

                    last_solution = cards

                else:
                    continue
                    agreement = agreement_classifier.predict(wason_message.content)
                    if agreement == 1:
                        solution_tracker.append({'type': "AGREEMENT",
                                                 'content': wason_message.content,
                                                 'user': item['user_name'],
                                                 'value': last_solution,
                                                 'id': item['message_id'],
                                                 'pos': message_count / total_length
                                                 })

    return solution_tracker


def calculate_team_performance(latest_solutions):
    score = 0
    for u, solution in latest_solutions.items():
        local_score, _ = is_solution_fine_grained(solution)
        score += local_score

    return round(score / len(latest_solutions), 3)


def merge_with_solution_raw(conversation_external, supervised=False):
    conversation = copy.deepcopy(conversation_external)
    if not supervised:
        # agreement_predictor = Predictor('models/agreement.pkl')
        agreement_predictor = None
        sol_tracker = solution_tracker(conversation, supervised, agreement_predictor)
    else:
        sol_tracker = solution_tracker(conversation, supervised)

    # print(sol_tracker)
    with_solutions = []

    latest_sol = {}

    for item in sol_tracker:
        if item['type'] == 'INITIAL':
            latest_sol[item['user']] = item['value']
        else:
            if item['user'] not in latest_sol:
                latest_sol[item['user']] = 'N/A'

    team_performance = calculate_team_performance(latest_sol)

    latest_score = team_performance

    team_performance = calculate_team_performance(latest_sol)
    display_dict = copy.copy(latest_sol)
    display_dict['team_performance'] = team_performance
    display_dict['performance_change'] = team_performance - latest_score
    display_dict['change_type'] = 'INITIAL'

    wm = WasonMessage(identifier=-1, origin='SYSTEM', content='SYSTEM',
                      annotation_obj=display_dict, type='INITIAL')
    with_solutions.append(wm)

    for raw in conversation.raw_db_conversation:
        real_local_sol = {}
        real_local_sol['value'] = None
        if raw['user_status'] != 'USR_PLAYING':
            continue

        if raw['message_type'] == 'WASON_SUBMIT':
            change_type = 'SUBMIT'
            local_sol = [s for s in sol_tracker if s['id'] == raw['message_id']][0]
        elif raw['message_type'] == 'CHAT_MESSAGE':
            local_sol = [s for s in sol_tracker if s['id'] == raw['message_id']]
            change_type = 'CHAT'
            if len(local_sol) == 0:
                if raw['user_name'] not in latest_sol:
                    latest_sol[raw['user_name']] = 'UKN'
                local_sol = {'user': raw['user_name'], 'value': latest_sol[raw['user_name']]}
                real_local_sol['value'] = None
            else:
                local_sol = local_sol[0]
                real_local_sol = local_sol
                change_type = 'OTHER'

        else:
            continue

        latest_sol[local_sol['user']] = local_sol['value']
        team_performance = calculate_team_performance(latest_sol)
        display_dict = copy.copy(latest_sol)
        display_dict['sol_tracker'] = real_local_sol['value']
        display_dict['team_performance'] = team_performance
        display_dict['performance_change'] = team_performance - latest_score
        display_dict['change_type'] = change_type
        latest_score = team_performance

        annotation_wason_conv = None

        for index, item in enumerate(conversation.wason_messages):
            if item.identifier == raw['message_id']:
                annotation_wason_conv = item
                last_index = index
        if annotation_wason_conv is not None:
            annotation_wason_conv.annotation.update(display_dict)
            with_solutions.append(annotation_wason_conv)
        else:
            wm = WasonMessage(identifier=raw['message_id'], origin=raw['user_name'], content='SYSTEM',
                              annotation_obj=display_dict, type='SUBMIT')
            with_solutions.append(wm)

    return with_solutions


def featurise_solution_participation(raw_conv):
    features = {}

    participation_tracker = defaultdict(lambda: 0)
    participation_normalised = {}
    messages = 0
    participation_at_10 = {'0': 0}
    participation_at_20 = {'0': 0}

    for raw in raw_conv:
        if raw['message_type'] == 'CHAT_MESSAGE':
            messages += 1
            participation_tracker[raw['user_name']] += 1
            for k_abs, v_abs in participation_tracker.items():
                participation_normalised[k_abs + '_participation'] = v_abs / messages
                if messages == 10:
                    participation_at_10 = participation_normalised
                if messages == 20:
                    participation_at_20 = participation_normalised
        else:
            if raw['user_name'] not in participation_tracker:
                participation_tracker[raw['user_name']] = 0

        return [*create_participation_feats(participation_at_10),
                *create_participation_feats(participation_at_20),
                *create_participation_feats(participation_normalised),
                ]


def create_participation_feats(participation):
    if len(participation) == 0:
        return [0, 0, 0, 0]

    dominating_50 = 0
    dominating_40 = 0
    completely_silent_participant = 0
    moderatly_silent = 0

    for us, part in participation.items():
        if part >= 0.5:
            dominating_50 = 1
        elif part >= 0.4:
            dominating_40 = 1
        elif part == 0:
            completely_silent_participant = 1
        elif part >= 0 and part <= 0.2:
            moderatly_silent = 1

    return [dominating_50, dominating_40, completely_silent_participant, moderatly_silent]


def get_context_solutions_users(postgre_messages, nlp):
    wason_conversation = WasonConversation(postgre_messages[0].room_id)
    for pm in postgre_messages:
        if pm.message_type in ['WASON_INITIAL', 'WASON_GAME', 'WASON_SUBMIT']:
            pm.content = pm.content.replace('false', 'False').replace('true', 'True')

        if pm.message_type in ['JOIN_ROOM', 'ROUTING_TIMER_ELAPSED', 'LEAVE_ROOM']:
            continue
        # print(pm.message_type)
        # print(pm.content)
        wason_conversation.raw_db_conversation.append({'message_type': pm.message_type,
                                                       'content': ast.literal_eval(pm.content),
                                                       'user_name': pm.origin,
                                                       'message_id': pm.unique_id,
                                                       'user_status': pm.user_status})
    participation_features = featurise_solution_participation(wason_conversation.raw_db_conversation)
    wason_conversation.wason_messages_from_raw()
    wason_conversation.preprocess_everything(nlp)
    messages = merge_with_solution_raw(wason_conversation, False)
    wason_conversation.wason_messages = messages
    wason_conversation.clean_special_tokens()

    context = []
    cards = []
    users = []
    tracker = [0]
    for m in wason_conversation.wason_messages:
        # print(m.origin)
        if m.origin != 'SYSTEM':
            users.append(m.origin.lower())
            context.append(m.clean_text)
            if 'sol_tracker' in m.annotation and m.annotation['sol_tracker'] is not None:
                tracker.append(m.annotation['performance_change'])
            else:
                tracker.append(tracker[-1])

        if 'sol_tracker' in m.annotation and m.annotation['sol_tracker'] is not None:
            cards.extend(list(m.annotation['sol_tracker']))

    return context, cards, users, tracker, participation_features


def read_wason_dump(dump_path):
    files = os.listdir(dump_path)
    conversations = []
    for f in files:
        conv = WasonConversation(identifier=f.split('.')[0])

        try:
            with open(dump_path + f, 'r') as rf:
                csv_reader = csv.reader(rf, delimiter='\t')
                next(csv_reader)  # Skip header row
                for item in csv_reader:
                    if item[3] in ['WASON_INITIAL', 'WASON_GAME', 'WASON_SUBMIT']:
                        item[4] = item[4].replace('false', 'False').replace('true', 'True')

                    content = item[4]
                    if item[3] in ['WASON_INITIAL', 'WASON_GAME', 'WASON_SUBMIT']:
                        content = ast.literal_eval(item[4])
                    else:
                        try:
                            content = ast.literal_eval(item[4])['message']
                        except Exception as e:
                            pass
                    if len(item) < 7:
                        conv.raw_db_conversation.append({
                            'message_id': item[0],
                            'user_name': item[1],
                            'user_id': item[2],
                            'message_type': item[3],
                            'content': content,
                            'user_status': item[5],
                            'timestamp': item[6],
                            'user_type': 'participant'

                        })
                    else:
                        conv.raw_db_conversation.append({
                            'message_id': item[0],
                            'user_name': item[1],
                            'user_id': item[2],
                            'message_type': item[3],
                            'content': content,
                            'user_status': item[5],
                            'timestamp': item[6],
                            'user_type': item[7] if len(item[7]) > 0 else 'participant'
                        })

        except Exception as e:
            traceback.print_exc()
            print(e)
            print(f)

        conversations.append(conv)

    return conversations


def read_3_lvl_annotation_file(ann_path):
    solutions_df = pd.read_csv(ann_path, delimiter='\t')
    solutions_df = solutions_df.fillna('0')

    processed_dialogue_annotations = []
    current_dialogue = []
    last_room_id = '0'
    for item in solutions_df.iterrows():
        if item[1]['room_id'] == '0' and len(current_dialogue) > 0 and last_room_id != '0':
            wason_conversation = WasonConversation(last_room_id)
            wason_conversation.wason_messages = current_dialogue
            processed_dialogue_annotations.append(wason_conversation)
            current_dialogue = []
        last_room_id = item[1]['room_id']
        message = WasonMessage(origin=item[1]['Origin'], content=item[1]['Content'],
                               annotation_obj=
                               {
                                   'additional': set([b.strip() for b in item[1]['Additional'].split(',')]),
                                   'type': item[1]['Type'],
                                   'target': item[1]['Target']
                               },
                               identifier=item[1]['Message_id'])
        current_dialogue.append(message)

    wason_conversation = WasonConversation(last_room_id)
    wason_conversation.wason_messages = current_dialogue
    processed_dialogue_annotations.append(wason_conversation)

    return processed_dialogue_annotations


def preprocess_conversation_dump(raw_data):
    user_performance = defaultdict(
        lambda: {'user_name': '', 'ONBOARDING_CLICK': [], 'ONBOARDING_CLICK_COARSE': [], 'ONBOARDING_SUBMIT': [],
                 'ONBOARDING_SUBMIT_COARSE': [], 'GAME_CLICK': [], 'GAME_CLICK_COARSE': [],
                 'GAME_SUBMIT': [], 'GAME_SUBMIT_COARSE': [], 'ONBOARDING_FINAL': '',
                 'SUBMIT_FINAL': '', 'MESSAGES_TOKENIZED': [], 'user_type': ''})

    for item in raw_data:
        user_performance[item['user_id']]['user_name'] = item['user_name']
        user_performance[item['user_id']]['user_type'] = item['user_type']
        if item['user_status'] == 'USR_ONBOARDING' and item['message_type'] == 'WASON_GAME':
            user_performance[item['user_id']]['ONBOARDING_CLICK'].append(is_solution_fine_grained(item['content']))
            user_performance[item['user_id']]['ONBOARDING_CLICK_COARSE'].append(is_solution_absolute(item['content']))
        elif item['user_status'] == 'USR_ONBOARDING' and item['message_type'] == 'WASON_SUBMIT':
            user_performance[item['user_id']]['ONBOARDING_SUBMIT'].append(is_solution_fine_grained(item['content']))
            user_performance[item['user_id']]['ONBOARDING_SUBMIT_COARSE'].append(is_solution_absolute(item['content']))
            user_performance[item['user_id']]['ONBOARDING_FINAL'] = item['content']
        elif item['user_status'] == 'USR_PLAYING' and item['message_type'] == 'WASON_GAME':
            user_performance[item['user_id']]['GAME_CLICK'].append(is_solution_fine_grained(item['content']))
            user_performance[item['user_id']]['GAME_CLICK_COARSE'].append(is_solution_absolute(item['content']))

        elif item['user_status'] == 'USR_PLAYING' and item['message_type'] == 'WASON_SUBMIT':
            user_performance[item['user_id']]['GAME_SUBMIT'].append(is_solution_fine_grained(item['content']))
            user_performance[item['user_id']]['GAME_SUBMIT_COARSE'].append(is_solution_absolute(item['content']))

            user_performance[item['user_id']]['SUBMIT_FINAL'] = item['content']
        elif item['message_type'] == 'CHAT_MESSAGE':
            user_performance[item['user_id']]['MESSAGES_TOKENIZED'].append(item['content'].lower().split(' '))

    to_del = set()

    #     print(user_performance)

    for key, values in user_performance.items():
        if len(values['MESSAGES_TOKENIZED']) < 2 or values['user_name'] == 'Moderating Owl':
            to_del.add(key)

        if len(values['ONBOARDING_CLICK']) == 0:
            values['ONBOARDING_CLICK'] = [(0, 'None')]
            values['ONBOARDING_CLICK_COARSE'] = [(0, 'None')]

        if len(values['ONBOARDING_SUBMIT']) == 0:
            values['ONBOARDING_SUBMIT'] = [values['ONBOARDING_CLICK'][-1]]
            values['ONBOARDING_SUBMIT_COARSE'] = [values['ONBOARDING_CLICK_COARSE'][-1]]

        if len(values['GAME_CLICK']) == 0:
            values['GAME_CLICK'] = [values['ONBOARDING_SUBMIT'][-1]]
            values['GAME_CLICK_COARSE'] = [values['ONBOARDING_SUBMIT_COARSE'][-1]]

        if len(values['GAME_SUBMIT']) == 0:
            values['GAME_SUBMIT'] = [values['GAME_CLICK'][-1]]
            values['GAME_SUBMIT_COARSE'] = [values['GAME_CLICK_COARSE'][-1]]

    for td in to_del:
        del user_performance[td]

    return user_performance


def calculate_stats(conversations_dump):
    table = str.maketrans(dict.fromkeys(string.punctuation))

    result_stats = {
        'onboarding_score': 0,
        'onboarding_score_coarse': 0,
        'game_score': 0,
        'game_score_coarse': 0,
        'message_count': 0,
        'tokens_count': 0,
        'unique_tokens': Counter(),
        'onboarding_types': Counter(),
        'game_types': Counter(),
        'number_of_submits': 0
    }

    onboarding_versions = []
    final_versions = []
    for _, user in conversations_dump.items():
        result_stats['onboarding_score'] += user['ONBOARDING_SUBMIT'][-1][0]
        result_stats['onboarding_score_coarse'] += user['ONBOARDING_SUBMIT_COARSE'][-1][0]

        result_stats['game_score'] += user['GAME_SUBMIT'][-1][0]
        result_stats['game_score_coarse'] += user['GAME_SUBMIT_COARSE'][-1][0]

        checked_onbording = [a['value'] for a in user['ONBOARDING_FINAL'] if a['checked'] is True]
        if len(checked_onbording) == 0:
            checked_onbording = ['None', 'None']

        checked_final = [a['value'] for a in user['SUBMIT_FINAL'] if a['checked'] is True]
        if len(checked_final) == 0:
            checked_final = ['None', 'None']

        if user['user_type'] != 'human_delibot':
            onboarding_versions.append("|".join(checked_onbording))
            final_versions.append("|".join(checked_final))

        result_stats['onboarding_types'].update([user['ONBOARDING_SUBMIT'][-1][1]])
        result_stats['game_types'].update([user['GAME_SUBMIT'][-1][1]])

        result_stats['message_count'] += len(user['MESSAGES_TOKENIZED'])
        result_stats['tokens_count'] += sum([len(s) for s in user['MESSAGES_TOKENIZED']])
        result_stats['unique_tokens'].update(
            [t.translate(table) for s in user['MESSAGES_TOKENIZED'] for t in s if len(t.strip()) >= 4])

        last = None
        for gs in user['GAME_SUBMIT']:
            if gs[1] != last:
                last = gs[1]
                result_stats['number_of_submits'] += 1

    # print(onboarding_versions)
    on_c = Counter(onboarding_versions).most_common(1)[0][1]
    fin_c = Counter(final_versions).most_common(1)[0][1]

    result_stats['num_of_players'] = len(conversations_dump)
    result_stats['num_of_playing_wason'] = len(
        [c for _, c in conversations_dump.items() if c['user_type'] == 'participant'])
    result_stats['onboarding_agreement'] = on_c / len(onboarding_versions)
    result_stats['final_agreement'] = fin_c / len(final_versions)
    result_stats['onboarding_success_rate'] = result_stats['onboarding_score'] / result_stats['num_of_playing_wason']
    result_stats['onboarding_success_rate_coarse'] = result_stats['onboarding_score_coarse'] / result_stats[
        'num_of_playing_wason']

    result_stats['final_success_rate'] = result_stats['game_score'] / result_stats['num_of_playing_wason']
    result_stats['final_success_rate_coarse'] = result_stats['game_score_coarse'] / result_stats['num_of_playing_wason']

    result_stats['message_per_player'] = result_stats['message_count'] / len(conversations_dump)
    result_stats['tokens_per_player'] = result_stats['tokens_count'] / len(conversations_dump)
    result_stats['unique_tokens_count'] = len(result_stats['unique_tokens'])
    result_stats['unique_tokens_per_player'] = len(result_stats['unique_tokens']) / len(conversations_dump)
    result_stats['most_common_tokens'] = result_stats['unique_tokens'].most_common(5)
    result_stats['task_performance'] = result_stats['final_success_rate'] - result_stats['onboarding_success_rate']
    result_stats['performance_gain_binary'] = 1 if result_stats['task_performance'] > 0 else 0
    result_stats['submits_per_user'] = result_stats['number_of_submits'] / result_stats['num_of_playing_wason']

    deli_correct = 0
    if 'CORRECT' not in result_stats['onboarding_types'] and 'CORRECT' in result_stats['game_types']:
        deli_correct = 1

    result_stats['deli_correct'] = deli_correct

    #     del result_stats['unique_tokens']
    return result_stats
