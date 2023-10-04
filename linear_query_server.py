import os.path
import random
from flask import Flask
from flask import request
import json
import numpy as np
import pandas as pd

app = Flask(__name__)
seedfile_name = "query_server_seed.txt" # file for seed
MAX_VECTOR_SIZE = 1000
CHALLENGE_MAX_LENGTH = 100

if not os.path.isfile(seedfile_name): # if no stored seed, create automatically
    with open(seedfile_name, 'w') as f:
        seed = ''.join(random.choice('0123456789abcdefghijklmnopqrstuvwxyz') for i in range(16))
        f.write(seed)
        f.close()
else: # read existing seed
    with open(seedfile_name, 'r') as f:
        seed = f.readline().strip()
        f.close()

logfile_name = f"{seed}_log.txt"


def secrets(challenge_id, n):
    rng = np.random.default_rng(abs(hash(str(n)+seed+challenge_id)))
    return rng.choice([-1,+1], size=n)

def check_required_args(args, required_args):
    for a in required_args:
        if a not in args:
            return {'error': f'Required arguments {required_args}'}
    return None

@app.route('/query', methods=['GET','POST'])
def query():
    response = check_required_args(request.args, ['challengeid','query'])
    if response is None:
        query_string = str(request.args.get('query'))
        query_vector = np.fromstring(query_string, dtype=int, sep=' ')
        challenge_id = str(request.args.get('challengeid'))
        n = query_vector.size
        if 'submit' in request.args and request.args['submit']=='True':
            epsilon = float('inf')
            submission = True
        else:
            epsilon = 1 / np.sqrt(n)
            submission = False

        if not challenge_id.isalnum():
            response = {'error': 'challengeid must be alphanumeric'}
        elif not len(challenge_id)>CHALLENGE_MAX_LENGTH:
            response = {'error': 'challengeid must og length at most {CHALLENGE_MAX_LENGTH}'}
        elif n > MAX_VECTOR_SIZE:
            response = {'error': 'maximum query vector size {MAX_VECTOR_SIZE} exceeded'}
        elif np.max(np.minimum(np.abs(query_vector - 1), np.abs(query_vector + 1))) > 0 or query_vector.size != n:
            response = {'error': f'query vector must consist of {n} values of plus or minus 1'}
        else:
            secrets_vector = secrets(challenge_id, n)
            rng = np.random.default_rng(abs(hash(challenge_id+query_string))) # fix response for a given query string
            noise = rng.laplace(scale = 1/epsilon)
            true_result = int(np.dot(query_vector, secrets_vector))
            query_result = str(int(np.clip(np.round(true_result + noise), -n, n)))
            with open(logfile_name, 'a') as f:
                if submission:
                    f.write(f"submission,{challenge_id},{n},{true_result}\n")
                    response = { 'challengeid': challenge_id, 'n': n, 'submission_vector': np.array2string(query_vector), 'result': true_result }
                else:
                    f.write(f"query,{challenge_id},{n},{query_result}\n")
                    response = { 'challengeid': challenge_id, 'n': n, 'query_vector': np.array2string(query_vector), 'result': query_result }
    return json.dumps(response)


@app.route('/leaderboard/')
def leaderboard():
    response = check_required_args(request.args, ['n'])
    if response is not None:
        return json.dumps(response)
    target_n = int(request.args.get('n'))
    query_counts = {}
    best_queries = {}
    for line in open(logfile_name, 'r'):
        record_type, challenge_id, n, result = line.split(',')
        n, result = int(n), int(result)
        if n == target_n:
            if record_type == 'query':
                query_counts[challenge_id] = query_counts.get(challenge_id,0) + 1
            elif record_type == 'submission':
                if challenge_id not in best_queries and query_counts.get(challenge_id,0) <= 2*n: # valid submission
                    best_queries[challenge_id] = ((1 + result / n) / 2, query_counts.get(challenge_id,0))

    sorted_best = sorted([(best_queries[challenge_id][0], challenge_id, best_queries[challenge_id][1]) for challenge_id in best_queries], reverse=True)
    df = pd.DataFrame(sorted_best, columns =['Percentage','ChallengeID', 'Queries'])
    df.index += 1
    return f"<html><body><h1>LEADERBOARD</h1><p>n={target_n}</p>{df.to_html()}</html>"
