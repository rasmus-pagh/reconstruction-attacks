"""Web API for the reconstruction-attack teaching exercise."""

# Copyright (c) 2026 Rasmus Pagh
# SPDX-License-Identifier: MIT

import hashlib
import json
import os
from pathlib import Path
import secrets as secrets_module
import threading

from flask import Flask, jsonify, request
import numpy as np
import pandas as pd

app = Flask(__name__)
MAX_VECTOR_SIZE = 100000
MAX_QUERY_ENTRIES = int(os.environ.get("MAX_QUERY_ENTRIES", 2_000_000))
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", 10 * 1024 * 1024))
PLUS_ONE_PROBABILITY = 2 / 3
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
app.config["MAX_FORM_MEMORY_SIZE"] = MAX_REQUEST_BYTES

data_dir = Path(
    os.environ.get("DATA_DIR", os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "data"))
)
data_dir.mkdir(parents=True, exist_ok=True)
seedfile_name = data_dir / "query_server_seed.txt"
log_lock = threading.Lock()

if not seedfile_name.is_file():
    seedfile_name.write_text(secrets_module.token_hex(16), encoding="utf-8")

seed = seedfile_name.read_text(encoding="utf-8").strip()
logfile_name = data_dir / f"{seed}_log.txt"


def deterministic_rng(*parts):
    material = "\0".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return np.random.default_rng(int.from_bytes(digest[:16], "big"))


def secrets(challenge_id, n):
    rng = deterministic_rng("dataset", n, seed, challenge_id)
    return rng.choice(
        [-1, +1],
        size=n,
        p=[1 - PLUS_ONE_PROBABILITY, PLUS_ONE_PROBABILITY],
    )

def check_required_args(args, required_args):
    for a in required_args:
        if a not in args:
            return {'error': f'Required arguments {required_args} got {args}'}
    return None


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({'error': f'request exceeds {MAX_REQUEST_BYTES} bytes'}), 413

@app.route('/query', methods=['POST'])
def query():
    response = check_required_args(request.form, ['challengeid','query'])
    if response is None:
        challenge_id = str(request.form.get('challengeid'))
        submission = request.form.get('submit') == 'True'

        try:
            query_data = json.loads(request.form.get('query'))
            query_vector = np.asarray(query_data)
        except (json.JSONDecodeError, TypeError, ValueError):
            response = {'error': 'query must be a JSON array'}
        else:
            response = None

        if response is not None:
            pass
        elif query_vector.ndim != 2:
            response = {'error': 'query must be a 2D array'}
        elif query_vector.shape[0] == 0 or query_vector.shape[1] == 0:
            response = {'error': 'query vectors must not be empty'}
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
            elif query_vector.size > MAX_QUERY_ENTRIES:
                response = {'error': f'maximum total query entries {MAX_QUERY_ENTRIES} exceeded'}
            elif not np.issubdtype(query_vector.dtype, np.number) or not np.all(np.isin(query_vector, [-1, 1])):
                response = {'error': f'query vectors must consist of {n} values of plus or minus 1'}
            else:
                epsilon = float('inf') if submission else 1 / np.sqrt(n)
                secrets_vector = secrets(challenge_id, n)
                canonical_query = json.dumps(query_data, separators=(',', ':'))
                rng = deterministic_rng("noise", challenge_id, canonical_query)
                noise = rng.laplace(scale = 1/epsilon, size = nQueries)
                true_result = np.dot(query_vector, secrets_vector) # (nQueris, ) vector if query, (1,) if submission
                query_result = str(np.clip(np.round(true_result + noise), -n, n).tolist())

                with log_lock, logfile_name.open('a', encoding='utf-8') as f:
                    if submission:
                        f.write(f"submission,{challenge_id},{n},{nQueries},{int(true_result.item())}\n")
                        response = { 'challengeid': challenge_id, 'n': n, 'submission_vector': np.array2string(query_vector), 'result': int(true_result.item()), 'number of queries': nQueries }
                    else: # if query
                        f.write(f"query,{challenge_id},{n},{nQueries},{query_result}\n")
                        response = { 'challengeid': challenge_id, 'n': n, 'query_vector': np.array2string(query_vector), 'result': query_result, 'number of queries': nQueries }
    return jsonify(response)

@app.route('/leaderboard/')
def leaderboard():
    response = check_required_args(request.args, ['n'])
    if response is not None:
        return jsonify(response)
    try:
        target_n = int(request.args.get('n'))
    except ValueError:
        return jsonify({'error': 'n must be an integer'}), 400

    query_counts = {}
    best_queries = {}
    with log_lock:
        lines = logfile_name.read_text(encoding='utf-8').splitlines() if logfile_name.is_file() else []

    for line in lines:
        record_type, challenge_id, n, nQueries, *results = line.split(',')
        n, nQueries = int(float(n)), int(float(nQueries))

        if n == target_n:
            if record_type == 'query':
                query_counts[challenge_id] = query_counts.get(challenge_id,0) + nQueries
            elif record_type == 'submission':
                result = int(results[0])
                if challenge_id not in best_queries and query_counts.get(challenge_id,0) <= 2*n: # valid submission
                    best_queries[challenge_id] = ((1 + result / n) / 2, query_counts.get(challenge_id,0))

    sorted_best = sorted([(best_queries[challenge_id][0], challenge_id, best_queries[challenge_id][1]) for challenge_id in best_queries], reverse=True)
    df = pd.DataFrame(sorted_best, columns =['Percentage','ChallengeID', 'Queries'])
    df.index += 1
    return f"<html><body><h1>LEADERBOARD</h1><p>n={target_n}</p>{df.to_html()}</html>"

if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 8000)))
