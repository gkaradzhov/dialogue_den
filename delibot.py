import transformers
import pandas as pd
from transformers import GPT2Tokenizer, GPT2LMHeadModel
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import csv
from collections import defaultdict
from transformers import AutoModelForCausalLM, AutoTokenizer

from wason_message_processing import read_3_lvl_annotation_file, read_wason_dump, merge_with_solution_raw

import torch
import torch.nn as nn
import torch.utils.data
from transformers import GPT2Tokenizer, GPT2Model
import random
from spacy.util import minibatch, compounding
import numpy as np
from typing import List, Tuple


def mean_across_all_tokens(hidden_states):
    return torch.mean(hidden_states[-1], dim=1)

def sum_all_tokens(hidden_states):
    return torch.sum(hidden_states[-1], dim=1)

def concat_all_tokens(hidden_states):
    batch_size, max_tokens, emb_dim = hidden_states[-1].shape
    return torch.reshape(hidden_states[-1], (batch_size, max_tokens * emb_dim))



class GPT2SequenceClassifierModel(nn.Module):
    def __init__(
            self,
            max_seq_length: int = 280,
            embedding_func=sum_all_tokens,
            combine_sentence_tokens=True, tokenizer='microsoft/DialoGPT-small', model='microsoft/DialoGPT-small'
    ):
        super(GPT2SequenceClassifierModel, self).__init__()
        # self.hidden_size = hidden_size
        # self.fc1 = nn.Linear(hidden_size, num_classes)

        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer)
        self.tokenizer.add_special_tokens({'additional_special_tokens':["<CARD>", '<MENTION>']})
        self.model = AutoModelForCausalLM.from_pretrained(model, output_hidden_states=True)
        self.model.resize_token_embeddings(len(self.tokenizer))

        # self.model = GPT2Model.from_pretrained(
        #     gpt_model_name,
        #     output_hidden_states=True
        # )
        # self.tokenizer = GPT2Tokenizer.from_pretrained(gpt_model_name)
        self.combine_sentence_tokens = combine_sentence_tokens;
        self.embedding_func = embedding_func;
        self.model.eval()
        self.max_length = max_seq_length

    def _tokenize(self, text_list: List[str]) -> Tuple[torch.tensor, torch.tensor]:
        # Tokenize the text with the provided tokenizer
        #self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        self.tokenizer.add_special_tokens({'cls_token': '[CLS]'})

        self.model.resize_token_embeddings(len(self.tokenizer))
        input_ids = self.tokenizer.batch_encode_plus(text_list,
                                                     add_special_tokens=True,
                                                     max_length=self.max_length,
                                                     pad_to_max_length=True
                                                     )["input_ids"]

        return torch.LongTensor(input_ids)

    def tokenize_and_predict(self, text_list: List[str]) -> torch.tensor:
        input_ids_tensor = self._tokenize(text_list)
        out = self.model(input_ids=input_ids_tensor)
        hidden_states = out[2]
        if (self.combine_sentence_tokens):
            return self.embedding_func(hidden_states).detach().numpy()
        else:
            return hidden_states[-1];


    def forward(self, text_list: List[str]):
        """
        :param input_ids: (torch.LongTensor of shape (batch_size, input_ids_length))
        :return: logits for class
        """
        if isinstance(text_list, pd.Series):
            text_list = text_list.tolist()
        with torch.no_grad():
            # fine tuning GPT2 model is too expensive, so won't do it
            gpt_out = self.tokenize_and_predict(text_list)
        batch_size = len(text_list)
        # assert gpt_out.shape == (batch_size, self.hidden_size)
        prediction_vector = self.fc1(gpt_out)  # (batch_size , max_len, num_classes)
        logits = torch.softmax(prediction_vector, dim=1)
        return logits


def speak_similarity(type, context, cards, users, all_utterances, processor):
    deli_utterance = ""
    gsb = get_similarity_best(tokenizer.eos_token.join(context),
                             all_utterances[type], 'previous_embedding_dialogue', processor)

    deli_utterance = reverse_fill(gsb, cards, users)

    return deli_utterance


def reverse_fill(text, solution_list, user_list):
  new_text = ''
  used_solutions = set()
  used_users = set()
  old_text = text

  for i in solution_list[::-1]:
    if i not in used_solutions:
        sol = i
        used_solutions.add(sol)
        break
  new_text = old_text.replace('<CARD>', sol, 1)

  while old_text != new_text:
    for i in solution_list[::-1]:
      if i not in used_solutions:
        sol = i
        used_solutions.add(sol)
        break
    old_text = new_text
    new_text = old_text.replace('<CARD>', sol, 1)


  old_text = new_text
  new_text = ''
  for i in user_list[::-1]:
    if i not in used_users:
        us = i
        used_users.add(us)
        break
  new_text = old_text.replace('<MENTION>', us, 1)

  while old_text != new_text:
    for i in user_list[::-1]:
      if i not in used_users:
        us = i
        used_users.add(us)
        break
    old_text = new_text
    new_text = old_text.replace('<MENTION>', us, 1)

  return new_text

def get_similarity_best(item, collection, key, embedder):
  embedding = embedder.tokenize_and_predict([item])[0].reshape(1, -1)
  best = None
  best_score = 0
  for i in collection:
    sim = cosine_similarity(embedding, i[key])[0][0]
    if sim > best_score:
      best_score = sim
      best = i['probing']

  return best


if __name__ == "__main__":

    tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-small")
    # model = AutoModelForCausalLM.from_pretrained("microsoft/DialoGPT-large")
    #
    tokenizer.add_special_tokens({'additional_special_tokens': ["<CARD>", '<MENTION>']})
    # model.resize_token_embeddings(len(tokenizer))

    dialogue = GPT2SequenceClassifierModel()
    annotations = read_3_lvl_annotation_file('data/annotated_data.tsv')
    raw_data = read_wason_dump('data/all/')

    nlp = spacy.load('en_core_web_sm')

    for item in annotations:
        raw = [r for r in raw_data if r.identifier == item.identifier][0]
        item.raw_db_conversation = raw.raw_db_conversation


    for item in annotations:
        item.preprocess_everything(nlp)
        messages = merge_with_solution_raw(item, False)
        item.wason_messages = messages
        item.clean_special_tokens()

    probing = defaultdict(lambda: [])
    for conversation in annotations:
        current_conversation = []
        for message in conversation.wason_messages:
            if 'type' in message.annotation and message.annotation['type'] == 'Probing':
                probing[message.annotation['target']].append(
                    {'previous': tokenizer.eos_token.join(current_conversation[-2:]), 'probing': message.clean_text})
            current_conversation.append(message.clean_text)


    counter = 0
    processed = defaultdict(lambda: [])
    for key, item in probing.items():
        print(key)
        for example in item:
            counter += 1
            print(counter)
            tokenised_dialogue = dialogue.tokenize_and_predict([example['previous']])[0]
            example['previous_embedding_dialogue'] = tokenised_dialogue.reshape(1, -1)
            processed[key].append(example)
            if counter == 10:
                break
        if counter == 10:
            break

    s = speak_similarity('Moderation', ['Hey how are you', 'I am well thanks'], cards=['A', 'A', '3'],
                         users=['Dolphin'], all_utterances=processed, processor=dialogue)

    print(s)
