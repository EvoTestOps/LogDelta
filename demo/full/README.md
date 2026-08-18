# LogDelta
LogDelta - Hadoop demo detailed. 



## Setup
From a clone of this repo (`git clone https://github.com/EvoTestOps/LogDelta.git`), in this
`demo/full` folder — no separate install step needed, `uv run` syncs the environment from the
repo's own `pyproject.toml`/`uv.lock` on first use (with `pip` instead, run `pip install -e .`
from the repo root first):
- `wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1`
- `unzip Hadoop.zip -d Hadoop`
- `uv run python label_hadoop_runs_fixed.py`

Then run any of the configurations below, e.g.
- `uv run python -m logdelta.config_runner -c demo_anodetect_1.yml`

The .yml files in this directory are demonstration configurations for various stages of log analysis, anomaly detection, distance measurement, and visualization using LogDelta. Each file focuses on a specific use case or part of the pipeline:

Visualization of Applications (demo_viz_app_X.yml): PageRank and WordCount. These configurations focus on visualizing application-specific data patterns.

Visualization of Anomalies (demo_viz_ano_X.yml).These files provide settings for visualizing detected anomalies.

Distance Measurement (demo_dist_X.yml). These files demonstrate configurations for measuring distances between log sequences.

Anomaly Detection (demo_anodetect_X.yml). These files define configurations for running anomaly detection and also visualizing anomalies on line level. 

