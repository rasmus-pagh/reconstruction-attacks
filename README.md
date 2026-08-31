# reconstruction-attacks
Code for hands-on experience with reconstruction attacks in a simple setting with a server that answers linear queries on hidden, pseudorandom datasets in {-1,+1}^n. There is some structure in the random datasets to make the reconstruction more interesting: The fraction of coordinates with value +1 is around 2/3. Once the server is up (see below) the reconstruction attack code can use it to answer linear queries on datasets, identified with a "challenge ID" string. A baseline implementation is included as a template. The server keeps track of queries and provides a leaderboard of submissions on n-dimensional datasets using at most 2n queries. Everything is meant to be used in a small-scale setting, like teaching a class on differential privacy, and will not scale to large sets of users.

## Run locally

Create a virtual environment and install the dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the production server on <http://127.0.0.1:8000>:

```sh
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 linear_query_server:app
```

Set `SERVER_URL = "http://127.0.0.1:8000"` in the notebook. The health check is available at <http://127.0.0.1:8000/health> and the leaderboard at <http://127.0.0.1:8000/leaderboard/?n=100>.

Run the local tests with:

```sh
python3 -m unittest discover -s tests
```

## Deployment

The seed and leaderboard log are stored in `DATA_DIR`, which defaults to the local `data/` directory. In Railway or Render, set `DATA_DIR=/data` and attach a persistent volume or disk at `/data`. Keep the service at one process while it uses the file-based leaderboard. The included `Procfile` starts Gunicorn with one process and four threads.

### Railway

1. Deploy this directory with `railway up` or connect the GitHub repository in the Railway dashboard.
2. Attach a volume to the web service with mount path `/data`. The server automatically uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` variable.
3. In the service settings, set the health-check path to `/health`.
4. Under Networking, generate a public domain.

Keep the service at one replica because the leaderboard is stored on the attached volume.
