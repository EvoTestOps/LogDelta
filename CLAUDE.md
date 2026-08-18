# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LogDelta is a Python tool/library for **comparing sets of log files** to find anomalies — "go beyond grepping" by using NLP-ish techniques (bag-of-words/n-grams, UMAP, clustering, out-of-vocabulary detection) instead of manual log inspection. It compares a **target run** (a folder of log files you're investigating) against one or more **comparison runs** (baseline folders), matching files by name across runs. It is built on top of [Polars](https://pola.rs/) for performance and [LogLead](https://pypi.org/project/LogLead/) (a sister project by the same author) for log loading, parsing, distance metrics, and anomaly detection primitives.

There is no test suite, linter, or CI configuration in this repo — it's a research/analysis tool, not a service.

## Install & run

The project is managed with [`uv`](https://docs.astral.sh/uv/), matching its sister project
[LogLead](https://github.com/EvoTestOps/LogLead). `pyproject.toml` + `uv.lock` + `.python-version`
(3.11) are the whole setup — `uv run` syncs the environment on first use, so there is no separate
install step for local development.

```bash
uv run python -m logdelta.config_runner -c path/to/config.yml   # local checkout
```

For use as a dependency:

```bash
uv add logdelta                  # published package
python -m pip install logdelta   # or with pip
```

Either `python -m logdelta.config_runner -c config.yml` or the `config-runner` console script works
(the script's entry point used to point at a nonexistent `package_name.config_runner:main`; it now
points at `logdelta.config_runner:main`). The `python -m` form is what the README and demos use.

### Demos

`demo/` contains runnable examples against the Hadoop dataset (from [loghub](https://github.com/logpai/loghub), via Zenodo). `demo/full/` and `demo/label_investigation/` each have their own README with exact commands. General pattern:

```bash
wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1
unzip Hadoop.zip -d Hadoop
uv run python -m logdelta.config_runner -c config.yml
```

`LOG_DATA_PATH` can be set (e.g. via a `.env` file, loaded with `python-dotenv`) as a fallback input folder when `input_data_folder` is not set in the config.

## Architecture

Everything funnels through **`logdelta/config_runner.py`**, which is the sole orchestrator (`main(config_path)`):

1. Load a YAML config, resolve `input_data_folder` (relative to `$PWD`, or `LOG_DATA_PATH` env var as fallback).
2. `read_folders()` loads all `*.log` files under the input folder into one big Polars DataFrame via LogLead's `RawLoader`. Each top-level subfolder becomes a **run**; the rest of the path becomes `file_name`. Null/non-UTF-8 message lines are dropped.
3. Optionally apply regex masking (`logdelta/regex_masking.py`) via `LogLead`'s `EventLogEnhancer.normalize()` — e.g. turning `192.168.1.1` into `<IP>`. Only the config's `regex_masking.pattern[-1]` actually takes effect (documented LogLead limitation, see comment in `config_runner.py`).
4. Optionally pre-parse event templates (e.g. `Parse-Tip`, `Parse-Drain`) via `EventLogEnhancer.parse_*()` methods — dynamically dispatched by name.
5. Apply any dataset-specific preprocessing steps from `logdelta/data_specific_preprocessing.py` (e.g. `remove_run_name_from_file_names`, used for Hadoop so files with the same role can be matched across differently-named application runs).
6. Iterate the config's `steps:` map and dynamically dispatch each step name to the matching function in `logdelta/log_analysis_functions.py` via `getattr` + `inspect.signature` (only config keys that match the function's parameters are passed through — extra YAML keys are ignored). A few step names (`plot_run_file`, `plot_run_content`, `anomaly_run_file`, `anomaly_run_content`) are aliases mapped to a shared underlying function (`plot_run` / `anomaly_run`) with fixed extra args (see `special_cases` dict in `config_runner.py`).

**`logdelta/log_analysis_functions.py`** is the core library — all the actual analysis functions live here and can also be called directly from Python (not just via YAML config). Key structure:

- **The analysis grid.** Every public function is one cell of a 2-D grid: the **object level** analyzed (folder/run → file → line — nested containers, where a folder is a collection of files, including files in subfolders, and a file is a collection of lines) × the **kind of analysis**. The blank cells are inherent to the concepts, not unimplemented work.

  | | Folder (run) | File | Line |
  |---|---|---|---|
  | **Visualize a set of objects** | `plot_run_file` (Files & Lines scatter + UMAP)<br>`plot_run_content` (Terms & Lines scatter + UMAP) | `plot_file_content` (Terms & Lines scatter + UMAP) | — |
  | **Anomaly scoring** | `anomaly_run_file`<br>`anomaly_run_content` | `anomaly_file_content` | `anomaly_line_content` |
  | **Distance** | `distance_run_file`<br>`distance_run_content` | `distance_file_content` | — |

  The three rows have genuinely different semantics, which matters when adding or changing functions:
  - **Distance** is always between a **pair** of objects (folder↔folder, file↔file) — "which object is most similar to which other?"
  - **Anomaly scoring** is between **a model trained on many objects** and **one target object** — "which object is suspicious?" Equivalently, the distance from a *set* of objects to a *target* object. This is why every `anomaly_*` function splits the data into comparison runs (train) and target (test).
  - **Visualization** lays out a whole **set** of objects at once, one dot each.

  Why the gaps: a file is not a collection of files, so the *Files & Lines* scatter only exists at folder level (the *Terms & Lines* scatter and UMAP do carry down to file level). Line-vs-line distance would mean far too many pairs to be useful. And no "set of lines" visualization exists — the only line-level picture is the **chronological** anomaly-score plot emitted by `anomaly_line_content` via `_ano_plot_line_scores`, which works precisely because lines have an inherent order within a file while folders and files do not; that plot and the table written next to it carry the same information.

  Note `distance_line_content` sits outside this grid: despite the name it runs LogLead's `diff_lines()` — a classic diff between two matched files — not a line-to-line distance metric.

- **`L1`–`L4` in output filenames** flatten the grid onto the four ways content is read: **L1** = folder-level over file *names* (never opens files), **L2** = folder-level over log *text*, **L3** = file-level, **L4** = line-level. The number is passed explicitly as `_write_output(..., level=N)` at each call site; `plot_run`/`anomaly_run` pick L1 vs L2 from their `file` flag.
- **Run/file selection helpers** (`_prepare_runs`, `_prepare_files`, `_check_multiple_target_runs`) accept a flexible spec for `target_run`/`comparison_runs`/`target_files`: `"ALL"`, an exact name/list, an integer count, or a `*` wildcard pattern. Note that **all four branches of `_prepare_runs` filter out the target run from the comparison set** ([log_analysis_functions.py:137-155](logdelta/log_analysis_functions.py#L137-L155)) — this is the leave-one-out guarantee that keeps an anomaly model from being trained and tested on the same run, so a target listed among its own comparison runs is silently (and correctly) dropped from training.
- **`_prepare_content()`** maps a `content_format` config value to the LogLead-enhanced column to actually compare: `Words` (tokenized), `3grams`, `File` (file names), `Sklearn` (raw/normalized message text for sklearn vectorizers), or `Parse-<X>` (dynamically calls `enhancer.parse_<x>()`, e.g. `Parse-Tip`, `Parse-Drain`).
- Distance functions use LogLead's `LogDistance` (cosine/jaccard/compression/containment). Anomaly functions use LogLead's `AnomalyDetector` (`_run_anomaly_detection`) with pluggable `detectors`: `KMeans`, `IsolationForest`, `RarityModel`, `OOVDetector` — results get z-score-normalized and rank-summed across detectors (`_calculate_zscore_sum_anos`) to produce a single combined anomaly score. Any subset of the detectors is valid: `_run_anomaly_detection` seeds its result frame from the test data (so the caller's identity columns — `run` at folder level, `m_message` at line level — arrive regardless of which detectors ran) and `_calculate_zscore_sum_anos` ranks over whichever score columns are actually present.
- Plot functions build a document-term matrix (Count/Tfidf vectorizer) and reduce it with UMAP, rendering **two** Plotly figures per call: a 2D UMAP scatter, and a "simple" scatter of lines vs. either unique files or unique terms. Which one the simple plot's x-axis shows is decided in `_plot_create_umap_plot` by the `file` argument: `True` (only `plot_run_file`) → *Files*; `False` or a filename string → *Unique terms*. `group_by_indices` lets you color points by parts of the run name (split on `_`).
- **`_write_output()`** is the single sink for all results — every analysis/plot writes to the module-global `output_folder` (set once via `set_output_folder_and_format()`), with a filename encoding analysis type, level, target/comparison run, mask flag, content format, vectorizer, and timestamp. Tables go to CSV (tab-separated) or XLSX (`table_output` config key); plots go to standalone HTML (Plotly).
- Module-level globals (`output_folder`, `table_output`, and `script_dir`-based `os.chdir()` at import time) mean this module is stateful — `set_output_folder_and_format()` must be called before any analysis function that writes output, and paths are resolved relative to `$PWD` at call time, not relative to the script location.

**`logdelta/regex_masking.py`** holds named lists of `(replacement, pattern)` regex tuples (e.g. `myllari`, `myllari_extended`, `drain_loglead`, `drain_orig`) referenced by name from config YAML.

**`logdelta/data_specific_preprocessing.py`** holds dataset-specific DataFrame transforms, dispatched by name from the config's `preprocessing_steps`. Add new dataset-specific cleanup functions here, following the `preprocess_files(df, preprocessing_steps)` dispatch pattern (function name + optional `args` list from YAML).

**`logdelta/subset_data_to_new_dir.py`** is a standalone one-off script (not part of the config pipeline) for randomly copying a portion of run folders to a new directory — reads `LOG_DATA_PATH` and has hardcoded `comp_ws/all_data` source paths; treat as a template to adapt rather than a general utility.

## Config file format (YAML)

Config files (see `demo/config.yml` for the fullest example) have this shape:

```yaml
input_data_folder: Hadoop
output_folder: Output
preprocessing_steps:
  - name: "remove_run_name_from_file_names"
regex_masking:
  enabled: true
  pattern:
    - name: "myllari_extended"
pre_parse:
  enabled: true          # only takes effect if regex_masking.enabled is also true
  parsers:
    - name: "Parse-Tip"
table_output: "csv"       # csv or xlsx
steps:
  distance_run_content:
    - target_run: "application_..."
      comparison_runs: "ALL"   # or a list, an int count, or a "prefix*" wildcard
      mask: True
      content_format: "Sklearn"   # Words | 3grams | Sklearn | File | Parse-<X>
      vectorizer: "Count"         # Count | Tfidf
  anomaly_line_content:
    - target_run: 3               # int = pick N runs as targets
      target_files: "ALL"
      comparison_runs: "ALL"
      detectors: [IsolationForest, KMeans, RarityModel, OOVDetector]
```

Each key under `steps:` is a list of parameter sets; each item is dispatched to the matching function in `log_analysis_functions.py` by name (see dispatch logic above). When adding a new analysis function intended to be config-driven, its name and keyword parameters must line up with how `config_runner.py` builds `kwargs` (matched by parameter name via `inspect.signature`).

## Working with generated output

`.gitignore` excludes `*.csv`, `*.html`, `*.xlsx`, `*.yaml`, `*.log`, and `Hadoop/` — all analysis outputs and downloaded demo data are treated as ephemeral/regenerable, not checked in. Don't be surprised to find large uncommitted output directories (e.g. `demo/Output/`) during local development.
