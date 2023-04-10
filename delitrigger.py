import math
import dill
import pickle
from collections import defaultdict

import spacy
from wason_message_processing import read_3_lvl_annotation_file, read_wason_dump, merge_with_solution_raw, \
    preprocess_conversation_dump, calculate_stats


def get_message_causing_changepoint(current_user, messages, num_messages):
    res = []
    # print(current_user)
    # print(messages)
    for item in messages[::-1]:
        if len(res) == 0 and item['usr'] == current_user:
            continue
        if len(res) < num_messages:
            res.append(item['message'].lower())

    # print(res)
    # print('----------------')
    return res[::-1]


def preprocess_train_supervised(data):
    return_data = []
    linguistic_training_data = []
    total_gaps = 0
    return_no_gaps = []
    for conversation in data:
        counted = True

        conv_data = []
        current_user_run = defaultdict(lambda: [])
        total_user_participation = defaultdict(lambda: [])
        user_submissions = defaultdict(lambda: 0)
        last_user_submission = {}
        messages = [{"usr": "SYSTEM", "message": 'BEGIN'}]
        for item in conversation:
            user_submissions[item['user']] = 0
            last_user_submission[item['user']] = ""

        dialogue_started = True
        counted_messages = []
        for event in conversation:
            # print(event['user'], event['type'], event['content'])
            if event['type'] == 'MESSAGE':
                dialogue_started = True
                if len(messages) >= 2:
                    context = get_message_causing_changepoint(event['user'], messages, 2)
                    if " <SEP> ".join(context) not in counted_messages:
                        linguistic_training_data.append((" <SEP> ".join(context), 0))
                        counted_messages.append(" <SEP> ".join(context))
                messages.append({'usr': event['user'], 'message': event['content']})
                for u_k in user_submissions.keys():
                    total_user_participation[u_k].append(event['performance'])
                    current_user_run[u_k].append(event['performance'])

                if 'partial_solution' in event['full_ann']['additional'] \
                        or 'complete_solution' in event['full_ann']['additional']:
                    if last_user_submission[event['user']] != event['submission']:

                        last_user_submission[event['user']] = event['submission']
                        context = get_message_causing_changepoint(event['user'], messages, 2)

                        if len(linguistic_training_data) > 0 and linguistic_training_data[-1] == (
                                " <SEP> ".join(context), 0):
                            linguistic_training_data = linguistic_training_data[:-1]
                            counted_messages = counted_messages[:-1]
                        if " <SEP> ".join(context) not in counted_messages:
                            linguistic_training_data.append((" <SEP> ".join(context), 1))
                            counted_messages.append(" <SEP> ".join(context))
                        conv_data.append(current_user_run[event['user']])
                        current_user_run[event['user']] = []
                        total_user_participation[event['user']].append('CHANGEPOINT')

        return_data.append(conv_data)
        for k, v in total_user_participation.items():
            return_no_gaps.append(v)

    return return_data, return_no_gaps, linguistic_training_data


def normalize_dict_dict(input_dict):
    normalised_dict = defaultdict(lambda: defaultdict(lambda: 0))
    total_sum = 0
    for key_outer, item_outer in input_dict.items():
        sum_key = sum(item_outer.values())
        total_sum += sum_key

        for key_pred, item_pred in item_outer.items():
            normalised_dict[key_outer][key_pred] = item_pred / sum_key
        normalised_dict[key_outer]['DEFAULT'] = 100 / sum_key

    normalised_dict['DEFAULT']['DEFAULT'] = 100 / total_sum

    return normalised_dict


def get_smoothed_proba(item, collection, discount_factor=0.5):
    if item in collection:
        return collection[item]

    sorted_collect = sorted(collection.keys())
    upper = -1
    lower = -1
    for i in sorted_collect:
        if item > i:
            lower = i
        elif item < i:
            upper = i
            break

    return (collection.get(lower, 0) + collection.get(upper, 0)) * 0.5 * discount_factor


def hazard_function(current_timestep, gaps):
    current = get_smoothed_proba(current_timestep, gaps, 2)
    s = current
    for k, g in gaps.items():
        if k > current_timestep:
            s += g
    return current / s


def sequence_probability(sequence, conditionals, apriori):
    previous = None
    probability = 0
    for item in sequence:
        if previous is None:
            probability = math.log(apriori.get(item, 0.0001))  # , 0.0001
        else:
            if previous in conditionals:
                probability += math.log(conditionals[previous].get(item, conditionals[previous]['DEFAULT']))
            #                 print(probability)
            else:
                probability += math.log(conditionals['DEFAULT']['DEFAULT'])
        previous = item

    return math.exp(probability)


class ChangeOfMindPredictor:
    def __init__(self, data, model):
        self.runtime_probability = {}
        self.value_conditional = {}
        self.value_prior = {}
        self.hazards = {}
        self.gap_prior = {}
        self.total_run_continue_proba = {}
        self.total_run_changepoint_proba = {}
        self.model = model
        self.train_language_agnostic(data)

    def joint_runtime_observed_x(self, current_run_x, runtime):
        run_proba = get_smoothed_proba(runtime, self.runtime_probability)

        seq_prob = sequence_probability(current_run_x, self.value_conditional, self.value_prior)

        return run_proba * seq_prob

    def change_point_proba(self, run_step, gap_prior):
        return 1 - hazard_function(run_step, gap_prior)

    def datum_changepoint(self, current_x, timestep):
        if timestep in self.datum_given_gap_proba:
            data = self.datum_given_gap_proba[timestep].get(current_x[timestep],
                                                            self.datum_given_gap_proba[timestep]['DEFAULT'])
        else:
            data = self.datum_given_gap_proba['DEFAULT']['DEFAULT']

        seq_prob = sequence_probability(current_x, self.value_conditional, self.value_prior)

        return seq_prob * data

    def runtime_joint_observed_datum(self, current_run_length, full_run_observations):
        final_proba = 0
        for i in range(1, current_run_length + 1):
            jro = self.joint_runtime_observed_x(full_run_observations[0:i - 1], i - 1)
            cpp = self.change_point_proba(i, self.gap_prior)
            dcp = self.datum_changepoint(full_run_observations[0:i], i - 1)
            final_proba += math.exp(math.log(jro + 0.00001) + math.log(cpp + 0.00001) + math.log(dcp + 0.00001))

        return final_proba

    def calc_growth_proba(self, current_run, total_run):
        result = 0
        run_len_est = self.runtime_joint_observed_datum(len(current_run), current_run)
        haz = hazard_function(len(current_run) - 1, self.gap_prior)

        if len(current_run) in self.datum_given_gap_proba:
            predictive_proba = self.datum_given_gap_proba[len(current_run)].get(current_run[-1], 0.00001)
        else:
            predictive_proba = 0.0001

        result = run_len_est * predictive_proba * (1 - haz) * (self.total_run_continue_proba.get(total_run, 0.00001))
        return result

    def calc_changepoint_proba(self, current_run, total_run):
        result = 0
        total_run_calc = 0
        weight = 1
        for i in range(0, total_run):
            total_run_calc += self.total_run_changepoint_proba.get(i, 0.00001) * weight
        for datum in current_run:
            run_len_est = self.runtime_joint_observed_datum(len(current_run), current_run)
            if len(current_run) in self.datum_given_gap_proba:
                predictive_proba = self.datum_given_gap_proba[len(current_run)].get(datum, 0.00001)
            else:
                predictive_proba = 0.0001
            haz = hazard_function(len(current_run) - 1, self.gap_prior)

            result += run_len_est * predictive_proba * haz

        result *= total_run_calc
        return result

    def train_language_agnostic(self, data):
        preprocessed_train, no_gaps, linguistic = preprocess_train_supervised(data)

        total_run_changepoint = defaultdict(lambda: 0)
        total_run_continue = defaultdict(lambda: 0)
        total_runs = defaultdict(lambda: 0)

        for user_conv in no_gaps:
            for index, run in enumerate(user_conv):
                total_runs[index] += 1
                if run == 'CHANGEPOINT':
                    total_run_changepoint[index] += 1
                else:
                    total_run_continue[index] += 1

        for key, val in total_run_changepoint.items():
            self.total_run_changepoint_proba[key] = val / total_runs[key]

        for key, val in total_run_continue.items():
            self.total_run_continue_proba[key] = val / total_runs[key]

        value_counts = defaultdict(lambda: 0)
        value_conditional_counts = defaultdict(lambda: defaultdict(lambda: 0))

        total_events = 0
        for conversation in preprocessed_train:
            previous = None
            for run in conversation:
                for element in run:
                    total_events += 1
                    value_counts[element] += 1
                    if previous is not None:
                        value_conditional_counts[previous][element] += 1
                    previous = element

        self.value_conditional = normalize_dict_dict(value_conditional_counts)

        for k, v in value_counts.items():
            self.value_prior[k] = v / total_events

        gap_counts = defaultdict(lambda: 0)
        gaps_run = defaultdict(lambda: 0)
        datum_given_gap = defaultdict(lambda: defaultdict(lambda: 0))

        total_gaps = 0
        for conversation in preprocessed_train:
            total_gaps += len(conversation)
            for run in conversation:
                gap_counts[len(run)] += 1
                for index, e in enumerate(run):
                    datum_given_gap[index + 1][e] += 1
                    gaps_run[index + 1] += 1

        self.datum_given_gap_proba = normalize_dict_dict(datum_given_gap)

        for k, gap in gap_counts.items():
            self.runtime_probability[k] = (gaps_run[k] - gap) / gaps_run[k]

        for k, v in gap_counts.items():
            self.gap_prior[k] = v / total_gaps

        for item in range(1, 80):
            self.hazards[item] = hazard_function(item, self.gap_prior)

    def predict_change_of_mind(self, conv_text, current_run, total_run):

        cha = self.calc_changepoint_proba(current_run, total_run)
        growth_proba = self.calc_growth_proba(current_run, total_run)
        if cha + growth_proba == 0:
            ocp_proba = 0
        else:
            ocp_proba = cha / (cha + growth_proba)

        ocp_prediction = 1 if ocp_proba > 0.75 else 0

        ling_output = self.model.predict_proba(["<SEP>".join(conv_text[-2])])[0][1]
        ling_prediction = 1 if ling_output >= 0.606 else 0

        return max(ocp_prediction, ling_prediction)


if __name__ == "__main__":

    annotations = read_3_lvl_annotation_file('data/annotated_data.tsv')
    raw_data = read_wason_dump('data/all/')

    nlp = spacy.load('en_core_web_sm')

    data = []
    for item in raw_data:
        annotated = False
        anno_item = None
        for anno in annotations:
            if item.identifier == anno.identifier:
                annotated = True
                item.wason_messages = anno.wason_messages

        current = []
        prepr = preprocess_conversation_dump(item.raw_db_conversation)

        stats = calculate_stats(prepr)

        item.preprocess_everything(nlp)
        messages = merge_with_solution_raw(item, False)

        usr_sol = {}
        for s_t in messages:
            if s_t.origin in s_t.annotation:
                current.append({'type': s_t.type, 'performance': s_t.annotation['team_performance'], 'user': s_t.origin,
                                'change': s_t.annotation['performance_change'], 'room_id': s_t.identifier,
                                'submission': "".join(s_t.annotation[s_t.origin]), "full_ann": s_t.annotation,
                                "content": s_t.content})
        data.append(current)

    with open('models/bow_full_delidata.model', 'rb') as f:
        clf2 = pickle.load(f)

    print(len(data))
    comp = ChangeOfMindPredictor(data, clf2)
    aa = comp.predict_change_of_mind(['Hi', "I think the answer is A and 2"], [0.5, 0.5, 0.5, 0.5], 22)
    print(aa)

    with open('models/changepoint', 'wb') as f:
        dill.dump(comp, f)
