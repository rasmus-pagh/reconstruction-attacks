# Code is provided by Rasmus Pagh (pagh@di.ku.dk), i have only slightly modified the query and leaderboard functions

import os.path
import random
from flask import Flask
from flask import request
import json
import numpy as np
import pandas as pd

app = Flask(__name__)
seedfile_name = "query_server_seed.txt" # file for seed
MAX_VECTOR_SIZE = 100000

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
            return {'error': f'Required arguments {required_args} got {args}'}
    return None

@app.route('/query', methods=['POST'])
def query():
    response = check_required_args(request.form, ['challengeid','query'])
    if response is None:
        query_vector = np.array(eval(request.form.get('query'))) # nQueries x n matrix
        challenge_id = str(request.form.get('challengeid'))

        if 'submit' in request.form and request.form['submit']=='True':
            epsilon = float('inf')
            submission = True
        else:
            epsilon = 1 / np.sqrt(query_vector.shape[1])
            submission = False

        # Check that query/submission vector is right size
        if len(query_vector.shape) != 2:
            response = {'error': 'query must be a 2D array'}
        elif query_vector.shape[0] != 1 and submission:
            response = {'error': 'submission must be a 2D array with one row'}
        else:
            # Get n (size of secret dataset) and nQueries (number of query vectors in input)
            n = query_vector.shape[1]
            nQueries = query_vector.shape[0]

            # First check if the query is a valid query
            if not challenge_id.isalnum():
                response = {'error': 'challengeid must be alphanumeric'}
            elif n > MAX_VECTOR_SIZE or nQueries > MAX_VECTOR_SIZE*2:
                response = {'error': f'maximum query vector size {MAX_VECTOR_SIZE}x{2*MAX_VECTOR_SIZE} exceeded'}
            elif np.max(np.minimum(np.abs(query_vector - 1), np.abs(query_vector + 1))) > 0 or query_vector.shape[1] != n:
                response = {'error': f'query vectors must consist of {n} values of plus or minus 1'}
            else:
                secrets_vector = secrets(challenge_id, n)
                rng = np.random.default_rng(abs(hash(challenge_id + str(query_vector)))) # fix for a given query string
                noise = rng.laplace(scale = 1/epsilon, size = nQueries)
                true_result = np.dot(query_vector, secrets_vector) # (nQueris, ) vector if query, (1,) if submission
                query_result = str(np.clip(np.round(true_result + noise), -n, n).tolist())

                with open(logfile_name, 'a') as f:
                    if submission:
                        f.write(f"submission,{challenge_id},{n},{nQueries},{int(true_result.item())}\n")
                        response = { 'challengeid': challenge_id, 'n': n, 'submission_vector': np.array2string(query_vector), 'result': int(true_result.item()), 'number of queries': nQueries }
                    else: # if query
                        f.write(f"query,{challenge_id},{n},{nQueries},{query_result}\n")
                        response = { 'challengeid': challenge_id, 'n': n, 'query_vector': np.array2string(query_vector), 'result': query_result, 'number of queries': nQueries }
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
        record_type, challenge_id, n, nQueries, *results = line.split(',')
        n, nQueries = int(float(n)), int(float(nQueries))

        if record_type == 'submission':
            result = int(results[0])
        else:
            result = None

        if n == target_n:
            if record_type == 'query':
                query_counts[challenge_id] = query_counts.get(challenge_id,0) + nQueries
            elif record_type == 'submission':
                if challenge_id not in best_queries and query_counts.get(challenge_id,0) <= 2*n: # valid submission
                    best_queries[challenge_id] = ((1 + result / n) / 2, query_counts.get(challenge_id,0))

    sorted_best = sorted([(best_queries[challenge_id][0], challenge_id, best_queries[challenge_id][1]) for challenge_id in best_queries], reverse=True)
    df = pd.DataFrame(sorted_best, columns =['Percentage','ChallengeID', 'Queries'])
    df.index += 1
    return f"<html><body><h1>LEADERBOARD</h1><p>n={target_n}</p>{df.to_html()}</html>"

if __name__ == '__main__':
    app.run(debug=True, port=5000)