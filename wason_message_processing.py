import ast

from nltk.tokenize import TweetTokenizer
import copy
import string


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
            doc = tagger(item.content)
            item.content_pos = [a.pos_ for a in doc]
            item.content_tokenised = self.tknzr.tokenize(item.content)

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
                print(cards)
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

    print(sol_tracker)
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




def get_context_solutions_users(postgre_messages, nlp):
    print(postgre_messages)
    wason_conversation = WasonConversation(postgre_messages[0].room_id)
    for pm in postgre_messages:
        if pm.message_type in ['WASON_INITIAL', 'WASON_GAME', 'WASON_SUBMIT']:
            pm.content = pm.content.replace('false', 'False').replace('true', 'True')
            pm.content = ast.literal_eval(pm.content)
        wason_conversation.raw_db_conversation.append({'message_type': pm.message_type,
                                     'content': pm.content,
                                     'user_name': pm.origin,
                                     'message_id': pm.unique_id})

    wason_conversation.wason_messages_from_raw()
    wason_conversation.preprocess_everything(nlp)
    messages = merge_with_solution_raw(wason_conversation, False)
    wason_conversation.wason_messages = messages
    wason_conversation.clean_special_tokens()

    print([a.annotation for a in wason_conversation.wason_messages])
    return wason_conversation, None, None
