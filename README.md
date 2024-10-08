# LogDelta
LogDelta - Go Beyond Grepping with NLP-Based Log File Analysis

LogDelta assumes your folders represent a collection of software logs of interest. LogDelta performs a comparison between two or more folders using matching file names.  A **target run** represents a software run we are interested in analyzing. LogDelta uses **comparison runs** as a baseline. For example, the "My_passing_logs1", "My_passing_logs2", "My_passing_logs3" folders can be comparison runs, while "My_failing_logs" would be your target run that you want to analyze with respect to comparison runs.

## Installation and Example
- `pip install -r requirements.txt`
- Download [Hadoop data](https://zenodo.org/records/8196385/files/Hadoop.zip?download=1) from Zenodo
- Edit [config.yml](https://github.com/EvoTestOps/LogLead/blob/main/demo/robo_mode/config.yml) so that it points to wherever you unziped Hadoop
- Type: `python main.py` or `python main.py -c config.yml` 
- Observe Excel files with log anomaly scoring and distances, as well as HTML files with visualizations, in the output folder.

## Types of Analysis
In LogDelta, three types of analysis are available:

1. **Measure the distance between two logs or sets of logs** using:
   - Jaccard distance
   - Cosine distance
   - Containment distance
   - Compression distance

2. **Build an anomaly detection model** from a set of logs and use it to score anomalies (higher scores more anomalous) in a log file using :
   - KMeans (kmeans)
   - IsolationForest (IF)
   - RarityModel (RM)
   - Out-of-Vocabulary Detector (OOVD)

3. **Visualize** file distances and files with log anomaly scoring

## Levels of Analysis
Analysis can be done at four different levels:

1. **Run (folder) level**, investigating the names of files without looking at their contents.
2. **Run (folder) level**, investigating run contents (this is slower than what is done in 1).
3. **File level**, investigating file contents (matched with the same names between runs).
4. **Line level**, investigating line contents (matched with the same names between runs).
