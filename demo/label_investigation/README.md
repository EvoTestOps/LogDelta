## LogDelta Demo - Hadoop Dataset

This demo showcases how to use LogDelta for analyzing log data from [Hadoop](https://github.com/logpai/loghub/tree/master/Hadoop) hosted by [loghub](https://github.com/logpai/loghub). 

### What's Included

1. **YouTube Playlist**: A comprehensive walkthrough of the LogDelta tool.

   - [See the Video playlist](https://www.youtube.com/playlist?list=PLTUjKYPvVhe6JhHBlkJN_yPhVDR5w2ej2)

2. **Script with Visuals and Timestamps**: A detailed script of the video, including visuals and timestamped links for easy navigation.

   - File: [script\_with\_visuals.md](./video_script.md)

### Highlights

- **Anomaly Detection**: Supports both run-level and line-level anomaly analysis. Use visualizations and anomaly detection models to identify mislabeled logs.
- **Visualization Options**: File names, textual content, U-MAP projections, anomaly scores.

### Summary of Findings

- LogDelta offers a variety of tools for visual and machine learning analysis of log data, making it easier to uncover patterns and anomalies.
- Using LogDelta multiple incorrect labels in Hadoop dataset were found.
- Corrected Labels:

| ID                  | Orig Label   | Fixed Label  |
| ------------------- | ------------ | ------------ |
| 1445144423722\_0024 | Normal       | Disk Full    |
| 1445182159119\_0017 | Machine Down | Normal       |
| 1445062781478\_0020 | Machine Down | Normal       |
| 1445182151478\_0015 | Machine Down | Disk Full    |
| 1445182159119\_0013 | Disk Full    | Machine Down |
| 1445182159119\_0011 | Disk Full    | Machine Down |


---
### Quickstart Guide

Follow these steps to get started with LogDelta:

Clone the repository:
   ```bash
   git clone https://github.com/EvoTestOps/LogDelta.git
   cd LogDelta/demo/label_investigation
```
No separate install step needed — the commands below use `uv run`, which syncs the environment
from the repo's own `pyproject.toml`/`uv.lock` on first use. (If you're using `pip` instead, run
`pip install -e .` from the repo root and drop the `uv run` prefix from the commands below.)

Download the Hadoop dataset and extract it:
```bash
wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1
unzip Hadoop.zip -d Hadoop
```
Rename the runs with labels using the provided script:
```bash
uv run python label_hadoop_runs_orig.py
```
Run the demo configurations:
For file name visualization:
```bash
uv run python -m logdelta.config_runner -c 1_viz_file_names.yml
```
For textual content visualization:
```bash
uv run python -m logdelta.config_runner -c 2_viz_run_content.yml
```
For anomaly detection with run content:
```bash
uv run python -m logdelta.config_runner -c 3_ano_run_content.yml
```
For line-level anomaly detection:
```bash
uv run python -m logdelta.config_runner -c 4_ano_line_content.yml
```
Outputs will be saved in out_1, out_2, out_3, and out_4 folders, respectively.
