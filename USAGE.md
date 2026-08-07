# LogDelta Demos — Usage Guide

The `demo/` folder has two purposes, in two subfolders:

- **`demo/label_investigation/`** — a guided, narrated walkthrough (with a companion YouTube playlist) that uses LogDelta to find *actual mislabeled runs* in a public dataset. Start here if you're new to LogDelta and want to see *why* each analysis is useful, not just how to invoke it.
- **`demo/full/`** — a reference gallery of ~19 small config files, each isolating one analysis type/option combination. Use this once you know what you're doing and want a config to copy-paste from.

There's also **`demo/config.yml`**, a single "kitchen sink" config (referenced by the root `README.md` quickstart) that exercises nearly every step type in one file — good as a syntax reference, not as a tutorial.

All three use the same underlying dataset: the **Hadoop** log dataset from [loghub](https://github.com/logpai/loghub) (originally from Lin et al., ICSE 2016), containing PageRank and WordCount MapReduce runs, each either `Normal` or injected with one of three failures (`MachineDown`, `NetworkDisconnection`, `DiskFull`).

---

## How to think about a LogDelta analysis

In LogDelta you select two things: *what kind of object* you analyze, and *what kind of analysis* you run on it.

### The objects: folder → file → line

The three object levels are nested:

- a **folder** (a "run") is a collection of files — files in subfolders belong to it
- a **file** is a collection of lines
- a **line** is the atom

If you have data that has sequences but all sequences are inside a single file, a LogDelta way of working is to split each sequence to unique file. 

### The three kinds of analysis

| Analysis | What it compares | The question it answers |
|---|---|---|
| **Visualizing sets of objects** | a whole *set* of objects, plotted together, one dot each | *Which objects stand out from the crowd?* |
| **Anomaly scoring** | a **model trained on many objects** vs. **one target object** | *Which object is suspicious?* Think of it as measuring the distance between a **set** of objects and a **target** object. |
| **Distance measurement** | a **pair** of objects | *Which object is most similar to which other object?* Good for pairwise matching — e.g. matching one known anomaly against a set of unidentified cases to find its closest relative. |

The distinction between the last two is the one people mix up. Distance is symmetric and pairwise: two folders, or two files. Anomaly scoring is one-against-many: you train on a group (usually the known-normal runs) and score a single target against it.

### Which configurations exist

Every LogDelta function is one cell of this grid. The blank cells repsent configurations that do not make sense. They are not missing features:

| | **Folder-level** | **File-level** | **Line-level** |
|---|---|---|---|
| **Visualize** | `plot_run_file` — *Files & Lines* scatter and UMAP<br>`plot_run_content` — *Terms & Lines* scatter and UMAP | `plot_file_content` — *Terms & Lines* scatter and UMAP | — |
| **Anomaly scoring** | `anomaly_run_file`<br>`anomaly_run_content` | `anomaly_file_content` | `anomaly_line_content` (table **and** chronological plot) |
| **Distance** | `distance_run_file`<br>`distance_run_content` | `distance_file_content` | — |


### The `L1`–`L4` numbers in output filenames

Output files are named `..._L1_...`, `..._L2_...` and so on. That numbering flattens the grid above onto the four combinations that read log content differently:

| | Meaning |
|---|---|
| **L1** | Folder-level, using **file names** as the content (never opens the files) |
| **L2** | Folder-level, using the **log text** |
| **L3** | File-level |
| **L4** | Line-level |

So `ano_L2_...xlsx` is run-level anomaly scoring over log text, and `dis_L3_...xlsx` is pairwise distance between matched files.

---

## 1. `demo/label_investigation/` — start here

**What it's for:** telling the story of how LogDelta was used to catch **6 incorrect labels** in the Hadoop dataset, walking down the grid above in four steps: folder-level visualization by *file names* → folder-level visualization by *log text* → folder-level *anomaly scoring* → line-level *anomaly scoring*. Each step builds on the previous one's findings. Full narration, screenshots, and result tables live in [`video_script.md`](demo/label_investigation/video_script.md); the images it references are in `demo/label_investigation/images/`.

Companion video playlist: https://www.youtube.com/playlist?list=PLTUjKYPvVhe6JhHBlkJN_yPhVDR5w2ej2 (three videos, covering visualization, run-level anomaly detection, and line-level anomaly detection respectively — `video_script.md` links to specific timestamps for key findings).

### Why this works (the core intuition)

This walkthrough uses two of the three analyses from the grid above, and they find anomalies by completely different mechanisms.

**The folder-level visualizations** (steps 1–2 below) rest on a "size and vocabulary differ from normal" heuristic, and the difference can go either way. On one hand, an anomalous run is rarely anomalous end-to-end — it's still mostly made up of the same normal log lines as a healthy run, just with extra unusual content mixed in (errors, retries, warnings, stack traces), so it can end up with *more* lines and a *larger vocabulary* than a normal run of the same application. On the other hand, a run can also abnormally terminate — crash or get killed partway through — and produce *fewer* lines and a *smaller vocabulary* than any normal run simply because it never got the chance to log the rest of a normal execution. (Landauer et al. found this shorter-than-any-normal-run pattern alone identifies roughly a third of the anomalies in the HDFS dataset — see `video_script.md`.) Either direction shows up as an outlier on the **Terms & Lines** scatter, and it's cheap to eyeball.

The **Files & Lines** scatter applies that same larger-or-smaller-than-normal logic to a cheaper proxy: instead of counting unique *terms* inside the log text, it counts unique *file names* in the run — without ever opening a file. This only carries a signal for applications that change how many log files they produce under failure. Some applications respond to failures by spawning extra sub-processes or retries, each writing to its own distinctly-named log file — Hadoop is a good example, since a retried task gets a brand-new container log file, so a struggling run accumulates more unique file names than a normal one. Plenty of other systems always write to a fixed set of file names no matter what's failing, in which case the Files & Lines plot shows nothing useful and you should go straight to the Terms & Lines scatter or content-based anomaly scoring instead.

**The anomaly-scoring steps** (steps 3–4 below, and `demo/full/demo_anodetect_*.yml`) use a different mechanism, not a bigger version of the vocabulary heuristic. Instead of counting how many unique terms or files an object contains, they train unsupervised models (KMeans, IsolationForest, RarityModel, OOVDetector) on the `Normal` runs' content, turning each object into a feature vector, then score any new object by how far its vector falls from that learned notion of normal. Counting unique terms only makes sense for an object big enough to contain many of them — a single log line doesn't have a meaningful "vocabulary size" to count. But a single line still reduces to a feature vector just as a whole run does, so the trained-model approach scores it just fine. That's why anomaly scoring is the only one of the three analyses that reaches all the way down to individual lines, while the vocabulary-counting visualizations top out at file level.

### Setup

```bash
pip install logdelta
git clone https://github.com/EvoTestOps/LogDelta.git
cd LogDelta/demo/label_investigation
wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1
unzip Hadoop.zip -d Hadoop
python label_hadoop_runs_orig.py
```

`label_hadoop_runs_orig.py` renames each `Hadoop/application_<id>` folder to `<App>_<OriginalLabel>_application_<id>` (e.g. `PageRank_MachineDown_application_1445062781478_0012`), using the *original, uncorrected* labels from the dataset's `abnormal_label.txt`. Baking the label into the run name is what lets the later configs color/group plots by label via `group_by_indices` (splitting the run name on `_`) and filter comparison runs with wildcards like `"PageRank_Normal*"`.

(`demo/label_investigation/Hadoop/README.md` has background on the dataset and how the failures were injected; `abnormal_label.txt` is the raw label file the renaming script consumes.)

### Run in order

| Step | Config | Command | Output | What it shows |
|---|---|---|---|---|
| 1 | `1_viz_file_names.yml` | `python -m logdelta.config_runner -c 1_viz_file_names.yml` | `out_1/` (`L1`) | **Visualize, folder-level, file names** (`plot_run_file`) — the *Files & Lines* scatter plus a UMAP, each dot a run. A crude "lines vs. unique files" boundary already classifies ~76% of anomalies correctly. See "Why this works" above for why file names carry signal in Hadoop specifically. |
| 2 | `2_viz_run_content.yml` | `python -m logdelta.config_runner -c 2_viz_run_content.yml` | `out_2/` (`L2`) | **Visualize, folder-level, log text** (`plot_run_content`) — the *Terms & Lines* scatter plus a UMAP, each dot still a run. Boundary-based classification improves to ~86%, and this is where the run `..._0020` labeled `MachineDown` first looks suspicious (it lands inconsistently across repeated UMAP runs and across plot types). |
| 3 | `3_ano_run_content.yml` | `python -m logdelta.config_runner -c 3_ano_run_content.yml` | `out_3/` (`L2`, xlsx) | **Anomaly scoring, folder-level** (`anomaly_run_content`) — trains KMeans/IsolationForest/RarityModel/OOVDetector on the `Normal` runs' content, then scores every run against that model. Sorting by rank-sum surfaces 3 suspicious label candidates. |
| 4 | `4_ano_line_content.yml` | `python -m logdelta.config_runner -c 4_ano_line_content.yml` | `out_4/` (`L4`, xlsx + HTML) | **Anomaly scoring, line-level** (`anomaly_line_content`) — per-line scores for each run's main log file (`container__01_000001.log`), written as a table *and* as the chronological plot, which reads as a "fingerprint" per run. Comparing fingerprints side-by-side across all `Normal` / `MachineDown` / `DiskFull` runs is what confirms the mislabels (e.g. spotting the recurring "lack of space for maps" message). |

Final corrected labels found via this process:

| Application ID | Original Label | Corrected Label |
|---|---|---|
| 1445144423722_0024 | Normal | Disk Full |
| 1445182159119_0017 | Machine Down | Normal |
| 1445062781478_0020 | Machine Down | Normal |
| 1445182151478_0015 | Machine Down | Disk Full |
| 1445182159119_0013 | Disk Full | Machine Down |
| 1445182159119_0011 | Disk Full | Machine Down |

`demo/full/label_hadoop_runs_fixed.py` applies these corrected labels instead of the originals (see §2).

### Supporting script

- **`find_string.py`** — not part of the config pipeline; a standalone grep-like helper used during the investigation to confirm a specific log message (e.g. `"Going to preempt 1 due to lack of space for maps"`) only appears in certain runs. Edit `base_directory`/`search_string` at the bottom of the file and run `python find_string.py` directly. Useful as a template when you need to manually spot-check a hypothesis a plot/score gave you.

### Dead ends worth knowing about

Per `video_script.md`: pairwise distance metrics (Jaccard/Cosine/Compression) were tried during this investigation and found inconclusive here (differences between runs were too small to threshold on) — that's why this demo leans on anomaly detection and visualization instead. Distance metrics are still useful in other contexts — see `demo/full/demo_dist_*.yml`.

---

## 2. `demo/full/` — reference config gallery

**What it's for:** once you understand the levels of analysis, this is a fast way to find a config to copy for your own dataset. Every file targets the same run (`PageRank_DiskFull_application_1445182159119_0014`) so you can diff two configs and see exactly which option changes the output.

### Setup

```bash
cd demo/full
wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1
unzip Hadoop.zip -d Hadoop
python label_hadoop_runs_fixed.py
```

Unlike `label_investigation`'s renaming script, this one applies the **corrected** labels from the table above (see the mapping dict at the top of the file, and its docstring comment).

Each config writes to its own `Out/<config_name>/` folder, so you can run all of them without output collisions.

### Distance metrics (`demo_dist_*.yml`)

| Config | Object level | What pairs it compares |
|---|---|---|
| `demo_dist_1.yml` | Folder, file names (`L1`) | Target run vs. every other run, by file-name-set Jaccard/overlap distance only — never opens the files. |
| `demo_dist_2.yml` | Folder, log text (`L2`) | Target run vs. every `PageRank*` run, run four ways in one file: default word tokens, `Parse-Tip` event templates, `3grams`, and raw `Sklearn` text — so you can compare how `content_format` changes cosine/jaccard/compression/containment distances. |
| `demo_dist_34.yml` | File (`L3`) | Target run vs. other `DiskFull` runs, one pair per matched file, using `Sklearn` content + `Count` vectorizer. |

There's no `demo_dist` config below file level, for the reason given in the grid above: distance is a pairwise measure and line-vs-line pairs aren't useful. If you want per-line output from a pair of files, `distance_line_content` runs a plain diff between two matched files; if you want to know which *lines* are unusual, use `anomaly_line_content` instead.

### Anomaly detection (`demo_anodetect_*.yml`)

All four train a model on the `PageRank_Normal*` runs and score all `PageRank*` runs against it, with all four detectors (`IsolationForest`, `KMeans`, `RarityModel`, `OOVDetector`). They differ only in what one scored object *is* — this is the one analysis that reaches every level of the grid:

| Config | Object scored | |
|---|---|---|
| `demo_anodetect_1.yml` | One folder, represented by its file-name set | `L1` |
| `demo_anodetect_2.yml` | One folder, represented by its whole text content | `L2` |
| `demo_anodetect_3.yml` | One file (6 target files) | `L3` |
| `demo_anodetect_4.yml` | One line, in `container__01_000001.log` | `L4` |

### Visualization, by what you color the plot on (`demo_viz_*`)

These cover the whole visualization row of the grid — `plot_run_file` (folder, file names), `plot_run_content` (folder, log text) and `plot_file_content` (file) — and differ mainly in **`group_by_indices`**, i.e. which part of the (now label-baked-in) run name is used to color the dots:

| Family | `group_by_indices` | Colors points by |
|---|---|---|
| `demo_viz_app_*.yml` | `[0]` | Application (`PageRank` vs `WordCount`) |
| `demo_viz_ano_*.yml` | `[1]` | Failure label (`Normal` / `MachineDown` / `NetworkDisconnection` / `DiskFull`) |
| `demo_viz_app_ano_*.yml` | `[0, 1]` | Both combined |

Within each family the suffix picks the object level: `_1` = folder by file names (`L1`), `_2` = folder by log text (`L2`, and `viz_app_2` additionally runs `mask: True` vs `False` side by side), `_3` and `_4` = file level (`L3`) against one or several `target_files`. There is deliberately no `_5`: visualization stops at file level.

---

## 3. `demo/config.yml` — single-file config reference

Referenced directly by the root `README.md` quickstart:

```bash
cd demo
wget -O Hadoop.zip https://zenodo.org/records/8196385/files/Hadoop.zip?download=1
unzip Hadoop.zip -d Hadoop
python -m logdelta.config_runner -c config.yml
```

This is not narrated or level-by-level like the other two — it's one file that defines a step for nearly every function (`distance_run_file` through `plot_file_content`), each with several parameter variants (different `content_format`/`vectorizer`/`mask` combinations). Treat it as a syntax cheat-sheet: when writing your own config, find the step type you need here and copy its shape.

---

## Common gotchas across all demos

- **Download the dataset first.** None of the `Hadoop/` folders are checked into the repo (`.gitignore` excludes `Hadoop/`); every demo's first real step is the `wget`/`unzip`.
- **Run the labeling script before any config.** `group_by_indices` and `"Prefix*"` wildcard filters in the configs assume run folders are already renamed to `<App>_<Label>_application_<id>`. Skipping `label_hadoop_runs_orig.py` (label_investigation) or `label_hadoop_runs_fixed.py` (full) will make `target_run`/`comparison_runs` lookups fail.
- **`mask: True` matters.** Most configs mask volatile tokens (IPs, timestamps, hex IDs, etc. — see `logdelta/regex_masking.py`'s `myllari_extended` list) before comparing content; a couple of `demo/full` configs deliberately run both masked and unmasked to show the difference.
- **Output format is per-config**, via `table_output: csv` or `xlsx` — the label-investigation and full-gallery anomaly/distance configs use `xlsx` since CSV can't hold nested (list) columns.
