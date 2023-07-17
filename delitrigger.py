import json
import math
import pickle
from collections import defaultdict
from functools import partial

import spacy
from sklearn.base import BaseEstimator, TransformerMixin

from wason_message_processing import read_3_lvl_annotation_file, read_wason_dump, merge_with_solution_raw, \
    preprocess_conversation_dump, calculate_stats




class ChangeOfMindTrainer:
    def __init__(self, input_data=None):

        self.runtime_probability = {}
        self.value_conditional = {}
        self.value_prior = {}
        self.hazards = {}
        self.gap_prior = {}
        self.total_run_continue_proba = {}
        self.total_run_changepoint_proba = {}
        self.datum_given_gap_proba = {}
        if input_data is not None:
            self.train_language_agnostic(input_data)
            self.save_states()

    def save_states(self):
        with open('models/changeofmindstates.json', 'w') as f:
            json.dump([self.runtime_probability, self.value_conditional, self.value_prior, self.hazards, self.gap_prior,
                       self.total_run_continue_proba, self.total_run_changepoint_proba, self.datum_given_gap_proba],
                      f, ensure_ascii=False, indent=4)

    def get_message_causing_changepoint(self, current_user, in_messages, num_messages):
        res = []
        # print(current_user)
        # print(messages)
        for it in in_messages[::-1]:
            if len(res) == 0 and it['usr'] == current_user:
                continue
            if len(res) < num_messages:
                res.append(it['message'].lower())

        # print(res)
        # print('----------------')
        return res[::-1]

    def preprocess_train_supervised(self, in_data):
        return_data = []
        linguistic_training_data = []
        total_gaps = 0
        return_no_gaps = []
        for conversation in in_data:
            counted = True

            conv_data = []
            current_user_run = defaultdict(lambda: [])
            total_user_participation = defaultdict(lambda: [])
            user_submissions = defaultdict(lambda: 0)
            last_user_submission = {}
            conv_messages = [{"usr": "SYSTEM", "message": 'BEGIN'}]
            for item in conversation:
                user_submissions[item['user']] = 0
                last_user_submission[item['user']] = ""

            dialogue_started = True
            counted_messages = []
            for event in conversation:
                # print(event['user'], event['type'], event['content'])
                if event['type'] == 'MESSAGE':
                    dialogue_started = True
                    if len(conv_messages) >= 2:
                        context = self.get_message_causing_changepoint(event['user'], conv_messages, 2)
                        if " <SEP> ".join(context) not in counted_messages:
                            linguistic_training_data.append((" <SEP> ".join(context), 0))
                            counted_messages.append(" <SEP> ".join(context))
                    conv_messages.append({'usr': event['user'], 'message': event['content']})
                    for u_k in user_submissions.keys():
                        total_user_participation[u_k].append(event['performance'])
                        current_user_run[u_k].append(event['performance'])

                    if 'partial_solution' in event['full_ann']['additional'] \
                            or 'complete_solution' in event['full_ann']['additional']:
                        if last_user_submission[event['user']] != event['submission']:

                            last_user_submission[event['user']] = event['submission']
                            context = self.get_message_causing_changepoint(event['user'], conv_messages, 2)

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

    def normalize_dict_dict(self, input_dict):
        normalised_dict = defaultdict(partial(defaultdict, int))
        total_sum = 0
        for key_outer, item_outer in input_dict.items():
            sum_key = sum(item_outer.values())
            total_sum += sum_key

            for key_pred, item_pred in item_outer.items():
                normalised_dict[key_outer][key_pred] = item_pred / sum_key
            normalised_dict[key_outer]['DEFAULT'] = 100 / sum_key

        normalised_dict['DEFAULT']['DEFAULT'] = 100 / total_sum

        return normalised_dict

    def get_smoothed_proba(self, search_element, collection, discount_factor=0.5):

        if search_element in collection.keys():
            return collection[search_element]

        sorted_collect = sorted(collection.keys())
        upper = -1
        lower = -1
        for i in sorted_collect:
            if search_element > i:
                lower = i
            elif search_element < i:
                upper = i
                break

        return (collection.get(lower, 0) + collection.get(upper, 0)) * 0.5 * discount_factor

    def hazard_function(self, current_timestep, gaps):
        c = self.get_smoothed_proba(current_timestep, gaps, 2)
        s = c
        for k, g in gaps.items():
            if k > current_timestep:
                s += g
        return c / s

    def train_language_agnostic(self, processed_input):
        preprocessed_train, no_gaps, linguistic = self.preprocess_train_supervised(processed_input)

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

        self.value_conditional = self.normalize_dict_dict(value_conditional_counts)

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

        self.datum_given_gap_proba = self.normalize_dict_dict(datum_given_gap)

        for k, gap in gap_counts.items():
            self.runtime_probability[k] = (gaps_run[k] - gap) / gaps_run[k]

        for k, v in gap_counts.items():
            self.gap_prior[k] = v / total_gaps

        for ind in range(1, 80):
            self.hazards[ind] = self.hazard_function(ind, self.gap_prior)

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

class ChangeOfMindPredictor:
    def __init__(self, saved_states_path='models/changeofmindstates.json', model_path='models/bow_full_delidata_withparticipation.model'):
        self.runtime_probability = {}
        self.value_conditional = {}
        self.value_prior = {}
        self.hazards = {}
        self.gap_prior = {}
        self.total_run_continue_proba = {}
        self.total_run_changepoint_proba = {}
        self.datum_given_gap_proba = {}
        self.model_path = model_path
        sss = Selector('aa')
        with open(saved_states_path, 'r') as f:
            loaded_dicts = json.load(f)
            loaded_dicts = [self.convert_keys_to_number(d) for d in loaded_dicts]

            self.runtime_probability, self.value_conditional, self.value_prior, self.hazards, self.gap_prior, self.total_run_continue_proba, self.total_run_changepoint_proba, self.datum_given_gap_proba = loaded_dicts
        with open(model_path, 'rb') as f:
            self.model = pickle.load(f)

    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def convert_keys_to_number(self, d):
        new_dict = {}
        for k, v in d.items():
            if isinstance(v, dict):
                v = self.convert_keys_to_number(v)

            if self.is_number(k) and k != "DEFAULT":
                try:
                    key = int(k)
                except ValueError:
                    key = float(k)
            else:
                key = k
            new_dict[key] = v
        return new_dict

    def get_smoothed_proba(self, search_element, collection, discount_factor=0.5):

        if search_element in collection.keys():
            return collection[search_element]

        sorted_collect = sorted(collection.keys())
        upper = -1
        lower = -1
        for i in sorted_collect:
            if search_element > i:
                lower = i
            elif search_element < i:
                upper = i
                break

        return (collection.get(lower, 0) + collection.get(upper, 0)) * 0.5 * discount_factor

    def hazard_function(self, current_timestep, gaps):
        c = self.get_smoothed_proba(current_timestep, gaps, 2)
        s = c
        for k, g in gaps.items():
            if k > current_timestep:
                s += g
        return c / s

    def predict_change_of_mind(self, conv_text, current_run, total_run, participation):
        prediction_object = {}
        cha = self.calc_changepoint_proba(current_run, total_run)
        growth_proba = self.calc_growth_proba(current_run, total_run)
        if cha + growth_proba == 0:
            ocp_proba = 0
        else:
            ocp_proba = cha / (cha + growth_proba)
        prediction_object['current_run'] = current_run
        prediction_object['BOCP'] = ocp_proba
        prediction_object['BOCP_threshold'] = 0.5
        prediction_object['BOCP_adjustment'] = 0.85

        ocp_prediction = 1 if 0.85 * ocp_proba > 0.5 else 0

        ling_output = self.model.predict_proba([{'text': "<SEP>".join(conv_text[-2:]), 'part': participation}])[0][1]
        prediction_object['linguistic_thresh'] = 0.5
        prediction_object['linguistic_proba'] = ling_output
        prediction_object['linguistic_path'] = self.model_path

        ling_prediction = 1 if ling_output >= 0.50 else 0
        print("Preds ", ocp_proba, ling_output)
        return max(ocp_prediction, ling_prediction), prediction_object

    def sequence_probability(self, sequence, conditionals, apriori):
        previous = None
        probability = 0
        for el in sequence:
            if previous is None:
                probability = math.log(apriori.get(el, 0.0001))  # , 0.0001
            else:
                if previous in conditionals:
                    probability += math.log(conditionals[previous].get(el, conditionals[previous]['DEFAULT']))
                #                 print(probability)
                else:
                    probability += math.log(conditionals['DEFAULT']['DEFAULT'])
            previous = el

        return math.exp(probability)

    def joint_runtime_observed_x(self, current_run_x, runtime):
        run_proba = self.get_smoothed_proba(runtime, self.runtime_probability)

        seq_prob = self.sequence_probability(current_run_x, self.value_conditional, self.value_prior)

        return run_proba * seq_prob

    def change_point_proba(self, run_step, gap_prior):
        return 1 - self.hazard_function(run_step, gap_prior)

    def datum_changepoint(self, current_x, timestep):
        if timestep in self.datum_given_gap_proba:
            dgp = self.datum_given_gap_proba[timestep].get(current_x[timestep],
                                                           self.datum_given_gap_proba[timestep]['DEFAULT'])
        else:
            dgp = self.datum_given_gap_proba['DEFAULT']['DEFAULT']

        seq_prob = self.sequence_probability(current_x, self.value_conditional, self.value_prior)

        return seq_prob * dgp

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
        haz = self.hazard_function(len(current_run) - 1, self.gap_prior)

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
            haz = self.hazard_function(len(current_run) - 1, self.gap_prior)

            result += run_len_est * predictive_proba * haz

        result *= total_run_calc
        return result


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

    print(len(data))
    trainer = ChangeOfMindTrainer(data)

    comp = ChangeOfMindPredictor()
    aa, obj = comp.predict_change_of_mind(['Hi', "I think the answer is A and 2"], [0.5, 0.5, 0.5, 0.5], 22)
    print(aa)
    print(obj)
    pass
