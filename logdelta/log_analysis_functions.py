import os
import polars as pl
import inspect
import datetime
from loglead.loaders import RawLoader
from loglead import LogDistance, AnomalyDetector
import umap
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from loglead.enhancers import EventLogEnhancer

# Ensure this always gets executed in the same location
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
output_folder = None
table_output = None

def set_output_folder_and_format(folder_path, table_output_format):
    """
    Set the global output folder path for the module.
    
    Parameters:
        folder_path (str): The path to the output folder.
    """
    global output_folder  # Declare that we're modifying the global variable
    folder_path = _get_abs_path(folder_path, create=True)
    output_folder = folder_path
    global table_output
    table_output = table_output_format
    print(f"Output folder set to: {output_folder}, Table output format: {table_output}")


def _get_abs_path_OLD(path):
    if not os.path.isabs(path):
        invocation_dir = os.getenv("PWD")
        if not invocation_dir:
            # Fallback if PWD isn't set (e.g., on some systems)
            invocation_dir = os.getcwd()
        abs_path = os.path.join(invocation_dir, path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Folder not found: {abs_path}")
        return abs_path
    return path

def _get_abs_path(path, create=False):
    """
    Get the absolute path of a given directory. If the path is relative, it is resolved
    against the current working directory. If `create` is True, the folder is created
    if it does not exist.
    """
    if not os.path.isabs(path):
        invocation_dir = os.getenv("PWD")
        if not invocation_dir:
            # Fallback if PWD isn't set (e.g., on some systems)
            invocation_dir = os.getcwd()
        abs_path = os.path.join(invocation_dir, path)
    else:
        abs_path = path

    if not os.path.exists(abs_path):
        if create:
            os.makedirs(abs_path)
        else:
            raise FileNotFoundError(f"Folder not found: {abs_path}")
    
    return abs_path

def read_folders(folder, filename_pattern= "*.log"):
    """
    read_folders(folder: str, filename_pattern: str = "*.log") -> Tuple[DataFrame, int]
    Loads log files from the specified folder, applying filters and transformations.

    Args:
        folder (str): Path to the folder containing log files.
        filename_pattern (str): Pattern for matching files (default: "*.log").

    Returns:
        Tuple[DataFrame, int]: 
            - DataFrame containing filtered and transformed log data.
            - Integer representing the number of unique runs (folders).

    Details:
        - Filters out rows with null or non-UTF-8 message content.
        - Extracts and processes 'run' and 'file_name' fields from the file paths.
    """
    folder = _get_abs_path(folder)
    print(f"Loading data from: {folder}")
    loader = RawLoader(folder, filename_pattern=filename_pattern, strip_full_data_path=folder)
    df = loader.execute()
    df = df.filter(pl.col("m_message").is_not_null()) #We lose lines with nulls. 
    df = df.filter(~pl.col("m_message").str.contains("�")) #We lose non-utf8 lines. 

    df = df.with_columns([
        # Extract the first part of the path and create the 'run' column
        pl.col("file_name").str.extract(r'^/([^/]+)', 1).alias("run"),
        # Remove the first part of the path to keep the rest in 'file_name'
        pl.col("file_name").str.replace(r'^/[^/]+/', '', literal=False).alias("file_name")
    ])
    unique_runs = len(df.select("run").unique().to_series().to_list())
    print (f"Loaded {unique_runs} runs (folders) with {df.height} rows from folder {folder}. Nulls and non-UTF-8s dropped.")
    return df, unique_runs

def _prepare_runs(df, target_run, comparison_runs="ALL"):
    """
    Prepares and validates the base and comparison runs from the dataframe.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - target_run: The name of the base run to compare against other runs.
    - comparison_runs: List of comparison run names, 'ALL' to compare against all other runs, 
      or an integer specifying the number of comparison runs (default is 'ALL').

    Returns:
    - base_run_df: DataFrame containing the data for the base run.
    - validated_comparison_runs: List of comparison run names to be compared with the base run.

    Raises:
    - ValueError: If the base run name or any comparison run name is not found in the dataframe.
    """
    # Extract unique runs
    unique_runs = df.select("run").unique().sort("run").to_series().to_list()

    # Validate base run name
    if target_run not in unique_runs:
        raise ValueError(f"Base run name '{target_run}' not found in the dataframe. Please provide a valid run name.")
    
    # Get the data for the base run
    base_run_df = df.filter(pl.col("run") == target_run)
    
    # Initialize the validated_comparison_runs variable
    validated_comparison_runs = []

    if comparison_runs == "ALL":
        # Use all other runs except the base run
        validated_comparison_runs = [run for run in unique_runs if run != target_run]
    elif isinstance(comparison_runs, int):
        # Ensure the number is valid
        if comparison_runs < 1 or comparison_runs > len(unique_runs) - 1:
            raise ValueError(f"Number of comparison runs must be between 1 and {len(unique_runs) - 1}.")
        # Exclude the base run and select the specified number of runs
        validated_comparison_runs = [run for run in unique_runs if run != target_run][:comparison_runs]
    elif isinstance(comparison_runs, str) and "*" in comparison_runs:
        import re
        # Convert wildcard pattern to regex
        regex_pattern = re.escape(comparison_runs).replace(r"\*", ".*")
        pattern = re.compile(f"^{regex_pattern}$")
        # Filter runs matching the regex pattern
        validated_comparison_runs = [run for run in unique_runs if pattern.match(run) and run != target_run]
        if not validated_comparison_runs:
            raise ValueError(f"No runs match the wildcard pattern '{comparison_runs}'.")
    else:
        # Assume comparison_runs is a list and validate all provided comparison runs
        comparison_runs_list = [run for run in comparison_runs if run != target_run]
        if not all(run in unique_runs for run in comparison_runs_list):
            invalid_runs = [run for run in comparison_runs_list if run not in unique_runs]
            raise ValueError(f"Comparison run names {invalid_runs} not found in the dataframe. Please provide valid run names.")
        validated_comparison_runs = comparison_runs_list

    return base_run_df, validated_comparison_runs

def _prepare_runs_OLD(df, target_run, comparison_runs="ALL"):
    """
    Prepares and validates the base and comparison runs from the dataframe.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: The name of the base run to compare against other runs.
    - comparison_runs: List of comparison run names, 'ALL' to compare against all other runs, or an integer specifying the number of comparison runs (default is 'ALL').

    Returns:
    - run1: DataFrame containing the data for the base run.
    - comparison_runs: List of comparison run names to be compared with the base run.

    Raises:
    - ValueError: If the base run name or any comparison run name is not found in the dataframe.
    """
    
    # Extract unique runs
    unique_runs = df.select("run").unique().sort("run").to_series().to_list()
    
    # Validate base run name
    if target_run not in unique_runs:
        raise ValueError(f"Base run name '{target_run}' not found in the dataframe. Please provide a valid run name.")
    
    # Get the data for the base run
    run1 = df.filter(pl.col("run") == target_run)
    
    # Determine comparison runs
    if comparison_runs == "ALL":
        # Use all other runs except the base run
        comparison_runs = [run for run in unique_runs if run != target_run]
    elif isinstance(comparison_runs, int):
        # Ensure the number is valid
        if comparison_runs < 1 or comparison_runs > len(unique_runs) - 1:
            raise ValueError(f"Number of comparison runs must be between 1 and {len(unique_runs) - 1}.")
        # Exclude the base run and select the specified number of runs
        comparison_runs = [run for run in unique_runs if run != target_run][:comparison_runs]
    elif isinstance(comparison_runs, str) and "*" in comparison_runs:
        import re
        # Convert wildcard pattern to regex
        regex_pattern = re.escape(comparison_runs).replace(r"\*", ".*")
        pattern = re.compile(f"^{regex_pattern}$")
        # Filter runs matching the regex pattern
        comparison_runs = [run for run in unique_runs if pattern.match(run) and run != target_run]
        if not comparison_runs:
            raise ValueError(f"No runs match the wildcard pattern '{comparison_runs}'.")
    else:
        # Remove the target run if it's present in the comparison runs
        comparison_runs = [run for run in comparison_runs if run != target_run]
        # Assume comparison_runs is a list and validate all provided comparison runs
        if not all(run in unique_runs for run in comparison_runs):
            invalid_runs = [run for run in comparison_runs if run not in unique_runs]
            raise ValueError(f"Comparison run names {invalid_runs} not found in the dataframe. Please provide valid run names.")
    
    return run1, comparison_runs

def _check_multiple_target_runs(df, base_runs):

    unique_runs = df.select("run").unique().sort("run").to_series().to_list()

    if base_runs == "ALL":
        base_runs = unique_runs 
    elif isinstance(base_runs, int):
        # Ensure the number is valid
        if base_runs < 1 or base_runs > len(unique_runs) - 1:
            raise ValueError(f"Number of base runs must be between 1 and {len(unique_runs) - 1}.")
        # Exclude the base run and select the specified number of runs
        base_runs = unique_runs[:base_runs]
    elif isinstance(base_runs, str) and "*" in base_runs:
        # Convert the glob-like pattern to a regex and filter available files
        import re
        pattern = re.compile(base_runs.replace(".", r"\.").replace("*", ".*"))
        matched_runs = [file for file in unique_runs if pattern.match(file)]
        if not matched_runs:
            raise ValueError(f"No runs matched the pattern: {base_runs} in {unique_runs} ")
        print (f"matched files {matched_runs}")
        base_runs = matched_runs
    else:
        # If base_runs is a single string, convert it to a list
        if isinstance(base_runs, str):
            base_runs = [base_runs]
        # Assume comparison_runs is a list and validate all provided comparison runs
        if not all(run in unique_runs for run in base_runs):
            invalid_runs = [run for run in base_runs if run not in unique_runs]
            raise ValueError(f"Comparison run names {invalid_runs} not found in the dataframe. Please provide valid run names.")
    return base_runs

def plot_run(df: pl.DataFrame, target_run: str, comparison_runs="ALL", file=True, random_seed=None, group_by_indices=None, mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Create a UMAP plot based on a document-term matrix of file names and save it as an interactive HTML file.
    
    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column and 'file_name' column.
    - target_run: Name of the target run to highlight.
    - comparison_runs: List of comparison run names to include in the plot.
    - file: Flag to indicate do use file names (True) or file contents (False)
    - random_seed: Random seed for reproducibility.
    - group_by_indices: List of integers indicating which parts of the 'run' string to group by.
    """
    # Apply the grouping by indices if specified
    if group_by_indices:
        df = _plot_group_runs_by_indices(df, group_by_indices)

    _, comparison_run_names = _prepare_runs(df, target_run, comparison_runs)
    print(
        f"Executing {inspect.currentframe().f_code.co_name} with {'file' if file else 'content'} mask={mask} with {content_format} and Vectorizer:{vectorizer} target run '{target_run}' and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )

    # Filter out target run and comparison runs from the DataFrame
    runs_to_include = [target_run] + comparison_run_names
    filtered_df = df.filter(pl.col("run").is_in(runs_to_include))
    filtered_df, field = _prepare_content(filtered_df, mask, content_format=content_format)
    #print (f"field: {field}")
    run_file_groups, documents = _plot_aggregate_run_file_groups(filtered_df, field, content_format, group_by_indices)
    embeddings_2d, num_unique_words_per_file = _plot_create_dtm_and_umap(documents, content_format, vectorizer, random_seed=None)
    
    #Prepare simple plot lines X unique_terms
    line_count = filtered_df.group_by("run").agg([pl.count().alias("line_count")]).sort("run")
    line_count_values = line_count.select("line_count").to_numpy().ravel()
    num_unique_words_per_file = np.asarray(num_unique_words_per_file).ravel()  # Ensure it's a 1D array
    line_count_values = np.asarray(line_count_values).ravel()  # Ensure it's a 1D array
    combined_data = np.column_stack((embeddings_2d, num_unique_words_per_file, line_count_values))

    fig1, fig2 = _plot_create_umap_plot(combined_data, run_file_groups, group_by_indices, target_run, file)
    
    #fig = _plot_create_umap_plot(embeddings_2d, run_file_groups, group_by_indices, target_run, file)
    _write_output(fig1, analysis=f"plot_run_{'file' if file else 'content'}_umap", level=1 if file else 2, mask=mask, target_run=target_run, comparison_run="Many", content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)
    _write_output(fig2, analysis=f"plot_run_{'file' if file else 'content'}_simple", level=1 if file else 2, mask=mask, target_run=target_run, comparison_run="Many", content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)

def _plot_group_runs_by_indices(df: pl.DataFrame, group_by_indices: list[int]) -> pl.DataFrame:
    """
    Groups the 'run' column based on specified indices.

    Parameters:
    - df: Polars DataFrame containing the 'run' column.
    - group_by_indices: List of integer indices specifying which parts to group by.

    Returns:
    - Polars DataFrame with an added 'group' column.
    """

    #S1: Split run string to multiple parts 1_33_44 becomes [1, 33, 44]
    df = df.with_columns(
        pl.col("run").str.split("_").alias("run_parts")
    )
    #S2:  Loop over and select the parts we want to keep for groups to a new df
    df_new = None
    for item in group_by_indices:
        if df_new is None:
           df_new = df.select(pl.col("run_parts").list.get(item, null_on_oob=True).alias(f"part_{item}"))
           df_new = df_new.with_columns(pl.col(f"part_{item}").fill_null(""))
        else:
           df_new = df_new.with_columns(df.select(pl.col("run_parts").list.get(item, null_on_oob=True).alias(f"part_{item}")))
           df_new = df_new.with_columns(pl.col(f"part_{item}").fill_null(""))

    #S3: New df contains only correct columns we merge 
    df_new = df_new.with_columns(pl.concat_str(pl.col("*"), separator="_",).alias("group"),)
    #S4: Lose the extra columns
    df_new = df_new.select(pl.col("group"))
    df = df.drop("run_parts")
    #S5 add the group column to df
    df = df.with_columns(df_new)
    return df

def _prepare_content(df, mask, content_format):
    """
    Function to process content (words, trigrams, etc.)  if content format SKLearn or not specified 
    """
    field = "e_message_normalized" if mask else "m_message"
    enhancer = EventLogEnhancer(df)
    if content_format == "Words":
        df = enhancer.words(field)
        return df, "e_words"
    elif content_format == "3grams":
        df = enhancer.trigrams(field)
        return df, "e_trigrams"
    elif content_format == "File":
        return df, "file_name"
    elif content_format == "Sklearn":
        return df, field
    elif content_format.startswith("Parse-"):
        # Extract the part after "Parse-" and create dynamic method and field
        parse_type = content_format.split("-")[1].lower()
        method_name = f"parse_{parse_type}"
        field_name = f"e_event_{parse_type}_id"
        
        # Dynamically call the corresponding method if it exists
        if hasattr(enhancer, method_name):
            method = getattr(enhancer, method_name)
            df = method(field)
            return df, field_name
        else:
            raise ValueError(f"No parse method found for {parse_type}")
    else:
        print(f"Unrecognized content format: {content_format}. Valid options: Words, 3grams, Sklearn, File, Parse-Tip, Parse-Drain")
        raise ValueError(f"Unrecognized content format: {content_format}. Valid options: Words, 3grams, Sklearn, File, Parse-Tip, Parse-Drain")

def _plot_aggregate_run_file_groups(filtered_df_file, field, content_format, group_by_indices):
    """
    Process the DataFrame and prepare the run file groups based on content format and grouping by indices.

    Parameters:
    - filtered_df: The full DataFrame (used for non-file-specific operations).
    - filtered_df_file: The filtered DataFrame for the file being processed.
    - field: The column name to aggregate.
    - content_format: The format of content (e.g., 'Sklearn', 'Parse').
    - group_by_indices: Whether to group by indices or not.

    Returns:
    - run_file_groups: Aggregated and grouped data for the runs and their content.
    - documents: List of concatenated file name strings for the runs.
    """

    # Handle 'Sklearn' or 'Parse' content formats (no exploding, just aggregation)
    if content_format == "Sklearn" or content_format.startswith("Parse-"):
        if group_by_indices:
            run_file_groups = filtered_df_file.select("run", field, "group").group_by("run").agg(
                pl.col(field),  # Keep the string column intact for later use in if Parse
                pl.col("group").first()  # First value of the group
            )
        else:
            run_file_groups = filtered_df_file.select("run", field).group_by("run").agg(
                pl.col(field)  # Keep the string column intact
            )
    elif content_format == "File":
        if group_by_indices:
            run_file_groups = filtered_df_file.select("run", field, "group").group_by("run").agg(
                pl.col(field).unique(), 
                pl.col("group").first()
            )
        else: 
            run_file_groups = filtered_df_file.select("run", field).group_by("run").agg(
                pl.col("file_name").unique()
            )
    else:
        if group_by_indices:
            run_file_groups = filtered_df_file.select("run", field, "group").explode(field).group_by("run").agg(
                pl.col(field), pl.col("group").first()
            )
        else:
            run_file_groups = filtered_df_file.select("run", field).explode(field).group_by("run").agg(
                pl.col(field)
            )
    
    run_file_groups = run_file_groups.sort("run") 
    column_data = run_file_groups.select(pl.col(field))
    if content_format == "Sklearn":
        column_data = column_data.with_columns(
            pl.col(field).list.join(' ')  # Concatenate the list elements with a space separator
        )
        documents = column_data.select(pl.col(field)).to_series().to_list()
    else:
        documents = column_data.to_series().to_list()

    return run_file_groups, documents

def _create_vectorizer(content_format: str, vectorizer_type: str):
    """
    Creates a vectorizer based on the content format and vectorizer type.

    Args:
    - content_format (str): The format of the content ("Sklearn" or others).
    - vectorizer_type (str): The type of vectorizer ("Count" or "Tfidf").

    Returns:
    - A fitted vectorizer instance (CountVectorizer or TfidfVectorizer).

    Raises:
    - ValueError: If the vectorizer_type is unsupported.
    """
    # vectorizer_params = {
    #     'tokenizer': lambda x: x,
    #     'preprocessor': None,
    #     'token_pattern': None,
    #     'lowercase': False
    # } if content_format != "Sklearn" else {}

    # vectorizer_params = {}

    if vectorizer_type == "Count":
        return CountVectorizer
        # return CountVectorizer(**vectorizer_params)
    elif vectorizer_type == "Tfidf":
        return TfidfVectorizer
        # return TfidfVectorizer(**vectorizer_params)
    else:
        raise ValueError(f"Unsupported vectorizer type: {vectorizer_type}")

def _plot_create_dtm_and_umap(documents, content_format, vectorizer_type, random_seed=None):
    """
    Create a document-term matrix (DTM) and perform UMAP dimensionality reduction.

    Parameters:
    - documents: List of document strings to be vectorized.
    - content_format: The format of the content ('Sklearn' or others).
    - vectorizer_type: Type of vectorizer ('Count' or 'Tfidf').
    - random_seed: Optional seed for UMAP to ensure reproducibility.

    Returns:
    - embeddings_2d: UMAP-reduced embeddings in 2D space.
    """
    # Set vectorizer parameters based on the content format
    vectorizer_params = {
        'tokenizer': lambda x: x,
        'preprocessor': None,
        'token_pattern': None,
        'lowercase': False
    } if content_format != "Sklearn" else {}

    # Create the vectorizer (Count or Tfidf)
    if vectorizer_type == "Count":
        vect = CountVectorizer(**vectorizer_params)
    elif vectorizer_type == "Tfidf":
        vect = TfidfVectorizer(**vectorizer_params)
    else:
        raise ValueError(f"Unsupported vectorizer type: {vectorizer_type}")

    # Fit the vectorizer to the documents and create the document-term matrix
    dtm = vect.fit_transform(documents)

    # Initialize UMAP with or without a random seed
    reducer = umap.UMAP(random_state=random_seed) if isinstance(random_seed, int) else umap.UMAP()

    # Perform UMAP dimensionality reduction on the document-term matrix
    embeddings_2d = reducer.fit_transform(dtm.toarray())
    unique_terms_per_document = (dtm > 0).sum(axis=1)
    return embeddings_2d, unique_terms_per_document

def _plot_create_umap_plot(embeddings_2d, run_file_groups, group_by_indices, target_run, file):
    """
    Create a UMAP plot using Plotly based on the provided embeddings and run group information.

    Parameters:
    - embeddings_2d: UMAP-reduced 2D embeddings.
    - run_file_groups: DataFrame containing run and group information.
    - group_by_indices: Flag indicating whether grouping by indices is applied.
    - target_run: The target run for highlighting in the plot.
    - file: The file name for which the UMAP plot is being created.

    Returns:
    - fig1: First Plotly scatter plot figure object.
    - fig2: Second Plotly scatter plot figure object.
    """

    if isinstance(file, str):
        title = f"Textual Content Comparison Between Files: {file} <br>Target run with diamond:<br>{target_run}"
    elif file:
        title = f"Filename Comparison Between Runs <br>Target run with diamond:<br>{target_run}"    
    else:
        title = f"Textual Content Comparison Between Runs <br>Target run with diamond:<br>{target_run}"    

    # Extract run labels from the run_file_groups DataFrame
    run_labels = run_file_groups["run"].to_list()

    # Determine group labels and color map based on grouping by indices
    if group_by_indices:
        group_labels = run_file_groups.select(pl.col("group")).to_series().to_list()
        unique_groups = sorted(set(group_labels))
        color_discrete_map = {group: f'rgba({(i*50)%255}, {(i*100)%255}, {(i*150)%255}, 1)' for i, group in enumerate(unique_groups)}
    else:
        group_labels = ['all'] * len(run_labels)
        color_discrete_map = {'all': 'blue'}

    # Calculate ranges for UMAP1 and UMAP2
    #range_x = embeddings_2d[:, 0].max() - embeddings_2d[:, 0].min()
    #range_y = embeddings_2d[:, 1].max() - embeddings_2d[:, 1].min()

    # Add jitter proportional to the range of each axis
    jitter_strength = 0.0033  # Base jitter strength
    #jitter_x = np.random.normal(0, jitter_strength * range_x, size=embeddings_2d.shape[0])
    #jitter_y = np.random.normal(0, jitter_strength * range_y, size=embeddings_2d.shape[0])

    # Create a Polars DataFrame for plotting
    plot_df = pl.DataFrame({
        "UMAP1": embeddings_2d[:, 0], #+ jitter_x,  # Add jitter to X-axis
        "UMAP2": embeddings_2d[:, 1], #+ jitter_y,  # Add jitter to Y-axis
        "run": run_labels,
        "group": group_labels  # Add group labels for coloring
    })
    # Convert Polars DataFrame to dictionary format for Plotly plotting
    plot_dict = plot_df.to_dict(as_series=False)
    # Define marker symbols: 'cross' for target run, 'circle' for others
    marker_symbols = ['circle' if run != target_run else 'cross' for run in run_labels]
    # Create the interactive UMAP plot using Plotly
    fig1 = px.scatter(
        plot_dict,
        x="UMAP1",
        y="UMAP2",
        color="group",  # Color based on groups or a single color
        symbol=marker_symbols,  # Set custom marker symbols
        color_discrete_map=color_discrete_map,  # Set custom colors based on groups or a single color
        hover_data={"run": True, "UMAP1": False, "UMAP2": False},  # Only show the run, hide UMAP coordinates
        title=title,
        opacity=0.7  # Add opacity
    )

    # Adjust jitter for second plot
    if file == True:
        x_title = "Files"
    else:
        x_title = "Unique terms"

    #Simple plot needs jitter. Lines and unique line count can be the same often. 
    jitter_strength = 0.0033
    range_x_2 = embeddings_2d[:, 2].max() - embeddings_2d[:, 2].min()
    #range_y_2 = embeddings_2d[:, 3].max() - embeddings_2d[:, 3].min()
    jitter_x_2 = np.random.normal(0, jitter_strength * range_x_2, size=embeddings_2d.shape[0])
    #jitter_y_2 = np.random.normal(0, jitter_strength * range_y_2, size=embeddings_2d.shape[0])

    # Y-axis is log scaled. Log-transformed jitter for Lines (Y-axis)
    log_lines_values = np.log10(embeddings_2d[:, 3] + 1e-10)  # Avoid log(0)
    log_lines_range = log_lines_values.max() - log_lines_values.min()

    jitter_lines_log = np.random.normal(0, jitter_strength * log_lines_range, size=embeddings_2d.shape[0])
    jittered_lines = 10 ** (log_lines_values + jitter_lines_log)  # Back to linear scale

    plot_df = pl.DataFrame({
        x_title: embeddings_2d[:, 2] + jitter_x_2,
        "Lines": jittered_lines,
        "run": run_labels,
        "group": group_labels  # Add group labels for coloring
    })
    # Convert Polars DataFrame to dictionary format for Plotly plotting
    plot_dict = plot_df.to_dict(as_series=False)
    # Define marker symbols: 'cross' for target run, 'circle' for others
    marker_symbols = ['circle' if run != target_run else 'cross' for run in run_labels]
    # Create the interactive simple plot y=Lines vs x= Unique Names plot using Plotly
    fig2 = px.scatter(
        plot_dict,
        x=x_title,
        y="Lines",
        color="group",  # Color based on groups or a single color
        symbol=marker_symbols,  # Set custom marker symbols
        color_discrete_map=color_discrete_map,  # Set custom colors based on groups or a single color
        hover_data={"run": True, x_title: True, "Lines": True, "group": False},  # Only show the run, hide UMAP coordinates
        title=title,
        opacity=0.7,  # Add opacity
        log_y=True  # Set the Y-axis to log scale
    )

    return fig1, fig2

def plot_file_content(df: pl.DataFrame, target_run: str, comparison_runs="ALL", target_files="ALL", random_seed=None, group_by_indices=None, mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Create a UMAP plot based on a document-term matrix of file names and save it as an interactive HTML file.
    
    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column and 'file_name' column.
    - target_run: Name of the target run to highlight.
    - comparison_runs: List of comparison run names to include in the plot.
    - random_state: If True, UMAP is randomized; if a number, it's used as the seed for reproducibility.
    
    The function will create a document-term matrix from the file names for each run.
    """
    # Apply the grouping by indices if specified
    if group_by_indices:
        df = _plot_group_runs_by_indices(df, group_by_indices)

    df_run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs)
    print(
        f"Executing {inspect.currentframe().f_code.co_name} with mask={mask}, {content_format} and Vectorizer:{vectorizer} on target run '{target_run}', target file {target_files} and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )

    # Filter out target run and comparison runs from the DataFrame
    runs_to_include = [target_run] + comparison_run_names
    filtered_df = df.filter(pl.col("run").is_in(runs_to_include))
    target_files = _prepare_files(df_run1, target_files)

    filtered_df, field = _prepare_content(filtered_df, mask, content_format=content_format)

    for file in target_files:
        filtered_df_file = filtered_df.filter(pl.col("file_name") == file).sort("file_name")
        run_file_groups, documents = _plot_aggregate_run_file_groups(filtered_df_file, field, content_format, group_by_indices)
        embeddings_2d, num_unique_words_per_file = _plot_create_dtm_and_umap(documents=documents, content_format=content_format, vectorizer_type=vectorizer, random_seed=random_seed)
        
        #fig = _plot_create_umap_plot(embeddings_2d, run_file_groups, group_by_indices, target_run, file)
        
        #num_unique_words_per_file = (dtm > 0).sum(axis=1).A1
        #Prepare simple plot lines X unique_terms
        line_count = filtered_df_file.group_by("run").agg([pl.count().alias("line_count")]).sort("run")
        line_count_values = line_count.select("line_count").to_numpy().ravel()
        num_unique_words_per_file = np.asarray(num_unique_words_per_file).ravel()  # Ensure it's a 1D array
        line_count_values = np.asarray(line_count_values).ravel()  # Ensure it's a 1D array
        combined_data = np.column_stack((embeddings_2d, num_unique_words_per_file, line_count_values))

        fig1, fig2 = _plot_create_umap_plot(combined_data, run_file_groups, group_by_indices, target_run, file)
        _write_output(fig1, analysis="plot_umap", level=3, target_run=target_run, comparison_run="Many", file=file, mask=mask, content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)
        _write_output(fig2, analysis="plot_simple", level=3, target_run=target_run, comparison_run="Many", file=file, mask=mask, content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)

def distance_run_file(df, target_run, comparison_runs="ALL", file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - target_run: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If None, compares against all other runs.
    """
    # Extract unique runs 
    run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
    results = []
    print(
        f"Executing {inspect.currentframe().f_code.co_name} with target run '{target_run}' and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )
    # Compare the base run to each specified comparison run
    for other_run in comparison_run_names:
        run2 = df.filter(pl.col("run") == other_run)
        
        # Extract unique file names from each run
        file_names_run1 = run1.select("file_name").unique()
        file_names_run2 = run2.select("file_name").unique()
        # Find file names that are only in run1
        only_in_run1_count = file_names_run1.filter(~pl.col("file_name").is_in(file_names_run2.get_column("file_name"))).height
        # Find file names that are only in run2
        only_in_run2_count = file_names_run2.filter(~pl.col("file_name").is_in(file_names_run1.get_column("file_name"))).height
        # Find the intersection of file names between run1 and run2
        intersection_count = file_names_run1.filter(pl.col("file_name").is_in(file_names_run2.get_column("file_name"))).height
        # Find the union of file names between run1 and run2
        union_count = pl.concat([file_names_run1, file_names_run2]).unique().height
        jaccard_dist = 1 - (intersection_count / union_count)
        overlap_dist = 1 - (intersection_count / min(file_names_run1.height, file_names_run1.height))

        # Append results to the list
        results.append({
            "target_run": target_run,
            "comparison_run": other_run,
            "files only in target": only_in_run1_count,
            "files only in comparison": only_in_run2_count,
            "union": union_count,
            "intersection": intersection_count,
            "jaccard distance": jaccard_dist,
            "overlap distance": overlap_dist
        })
        # Print a dot to indicate progress
        print(".", end="", flush=True)

    print()  # Newline after progress dots
    # Create a Polars DataFrame from the results
    results_df = pl.DataFrame(results)
    _write_output(results_df, analysis="dis", level=1, target_run=target_run, comparison_run="Many", file_name_prefix=file_name_prefix)

def distance_run_content(df, target_run, comparison_runs="ALL", mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If None, compares against all other runs.
    """
    df, field = _prepare_content(df, mask, content_format=content_format)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # Extract unique runs 
    run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
    results = []
    print(
        f"Executing {inspect.currentframe().f_code.co_name} with target run '{target_run}' normalized:{mask}, content format:{content_format}, vectorizer:{vectorizer}, field:{field} and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )
    # Compare the base run to each specified comparison run
    for other_run in comparison_run_names:
        run2 = df.filter(pl.col("run") == other_run)
        
        vectorizer_obj=_create_vectorizer(content_format=content_format, vectorizer_type=vectorizer)
        distance = LogDistance(run1, run2,vectorizer=vectorizer_obj, field=field)

        # Measure distances between the base run and the current run
        cosine = distance.cosine()
        jaccard = distance.jaccard()
        compression = distance.compression()
        containment = distance.containment()

        # Append results to the list
        results.append({
            "target_run": target_run,
            "comparison_run": other_run,
            "target_lines": distance.size1,
            "comparison_lines": distance.size2,
            "cosine": cosine,
            "jaccard": jaccard,
            "compression": compression,
            "containment": containment
        })
        # Print a dot to indicate progress
        print(".", end="", flush=True)

    #Z-score Normalization + Sum of Distances to get one score 
    #results = _calculate_zscore_sum(results)
    results = _calculate_zscore_sum_anos(results)
    print()  # Newline after progress dots
    results_df = pl.DataFrame(results)
    _write_output(results_df, analysis="dis", level=2, target_run=target_run, comparison_run="Many", mask=mask, content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)

def distance_file_content(df, target_run, comparison_runs="ALL", target_files=False, mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If None, compares against all other runs.
    """
    # Extract unique runs
    df, field = _prepare_content(df, mask, content_format=content_format) 
    run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
    results = []
    if target_files:
        target_files = _prepare_files(run1, target_files)

    print(
        f"Executing {inspect.currentframe().f_code.co_name} with target run '{target_run}' normalize:{mask} content_format:{content_format} and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )
    # Compare the base run to each specified comparison run
    for other_run in comparison_run_names:
        run2 = df.filter(pl.col("run") == other_run)
        file_names_run1 = run1.select("file_name").unique()
        file_names_run2 = run2.select("file_name").unique()
        matching_file_names = file_names_run1.filter(pl.col("file_name").is_in(file_names_run2.get_column("file_name")))
        matching_file_names_list = matching_file_names.get_column("file_name").to_list()

        if target_files:
            matching_file_names_list = list(set(target_files).intersection(set(matching_file_names_list)))
        if len(matching_file_names_list) == 0:
            continue
        print(
            f"Comparing against '{other_run}' with {len(matching_file_names_list)} matching files"
            + (f":  {matching_file_names_list}" if len(matching_file_names_list) < 6 else "")
            )
        for file_name in matching_file_names_list:
            run1_file = run1.filter(pl.col("file_name") == file_name)
            run2_file = run2.filter(pl.col("file_name") == file_name)

            # Calculate the distances
            # Initialize LogSimilarity class for each pair of runs
            distance = LogDistance(run1_file, run2_file, field=field)
            # Measure distances between the base run and the current run
            cosine = distance.cosine()
            jaccard = distance.jaccard()
            compression = distance.compression()
            containment = distance.containment()
            #Too slow
            #same, changed, deleted, added = similarity.diff_lines() 
            
            # Create a dictionary to store results
            result = {
                'file_name': file_name,
                'target_run': target_run,
                'comparison_run': other_run,
                'target_lines': distance.size1,
                'comparison_lines': distance.size2, 
                'cosine': cosine,
                'jaccard': jaccard,
                'compression': compression,
                'containment': containment,
            }
            results.append(result)
            # Print a dot to indicate progress
            print(".", end="", flush=True)
        results = _calculate_zscore_sum(results)
        print()  # Newline after progress dots

    # Create a Polars DataFrame from the results
    results_df = pl.DataFrame(results)
    _write_output(results_df, analysis="dis", level=3, target_run=target_run, comparison_run="Many", mask=mask, content_format=content_format, file_name_prefix=file_name_prefix)

def distance_line_content(df, target_run, comparison_runs="ALL", target_files="ALL", mask=False, file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If None, compares against all other runs.
    """    
    field = "e_message_normalized" if mask else "m_message"
    # Extract unique runs and files
    df_run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
    target_files = _prepare_files(df_run1, target_files)
    df_other_runs = df.filter(pl.col("run").is_in(comparison_run_names))
    print(
        f"Executing {inspect.currentframe().f_code.co_name} with target run '{target_run}' and {len(comparison_run_names)} comparison runs"
        + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
    )
    # Compare the base run to each specified comparison run
    for other_run in comparison_run_names:
        for file_name in target_files:
            df_run1_file =  df_run1.filter(pl.col("file_name") == file_name)
            df_other_run_file = df_other_runs.filter(pl.col("run") == other_run) #Filter one run
            df_other_run_file = df_other_run_file.filter(pl.col("file_name") == file_name) #Filter one file
            distance = LogDistance(df_run1_file, df_other_run_file, field=field)
            diff = distance.diff_lines()
            
            _write_output(diff, analysis="dis", level=4, target_run=target_run, comparison_run=other_run, mask=mask, file=file_name, file_name_prefix=file_name_prefix)
            print(".", end="", flush=True) #Progress on screen
    print()  # Newline after progress dots

def _prepare_files(df_run1, files="ALL"):
    """
    Prepares and validates the files from the base run data based on the provided configuration.

    Parameters:
    - df_run1: Polars DataFrame containing the data for the base run with a 'file_name' column.
    - files: List of file names, 'ALL' to use all files in the base run, an integer specifying the number of files to use, 
             or a list of file names to be processed (default is 'ALL').

    Returns:
    - files: List of file names to be used in the analysis.

    Raises:
    - ValueError: If no valid files are found or if the input list has no matching files in the base run.
    """
    
    # Extract available files from the base run
    available_files = df_run1.select("file_name").unique().to_series().to_list()

    if isinstance(files, list):
        # Check if each specified file exists in the base run data
        missing_files = [file for file in files if file not in available_files]
        if missing_files:
            print(f"Warning: The following files do not exist in the base run: {missing_files}")
            # Remove missing files from the list to avoid processing them
            files = [file for file in files if file in available_files]
        
        if not files:
            raise ValueError("No valid files found in the provided list for processing.")
    
    elif files == "ALL":
        # Use all unique files from the base run
        files = available_files
    
    elif isinstance(files, int):
        # Validate that the number is within the range of available files
        if files < 1 or files > len(available_files):
            raise ValueError(f"Number of files must be between 1 and {len(available_files)}.")
        # Select the specified number of files
        files = available_files[:files]
    elif isinstance(files, str) and "*" in files:
        # Convert the glob-like pattern to a regex and filter available files
        import re
        pattern = re.compile(files.replace(".", r"\.").replace("*", ".*"))
        matched_files = [file for file in available_files if pattern.match(file)]
        if not matched_files:
            raise ValueError(f"No files matched the pattern: {files}")
        files = matched_files
    
    else:
        raise ValueError(f"Invalid type for 'files': {files}. It must be 'ALL', a list, an integer, or a pattern.")

    
    return files

def _calculate_moving_average_all_numeric(df: pl.DataFrame, window_size: int) -> pl.DataFrame:
    """
    Internal function to calculate the moving average for all numeric columns in a Polars DataFrame.

    Args:
        df (pl.DataFrame): The Polars DataFrame containing the data.
        window_size (int): The size of the window over which to calculate the moving average.

    Returns:
        pl.DataFrame: A new DataFrame with only the moving averages for each numeric column.
    """
    # Get all numeric columns
    numeric_cols = [col for col, dtype in zip(df.columns, df.dtypes) if dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)]

    if not numeric_cols:
        raise ValueError("No numeric columns found in the DataFrame")
    
    # Populate the DataFrame with rolling means for numeric columns, rename the columns,
    # return selected columns
    return df.select([
        pl.col(col).rolling_mean(window_size).alias(f"moving_avg_{window_size}_{col}")
        for col in numeric_cols
        ])

def _calculate_zscore_sum(results):
    import numpy as np
    from scipy.stats import zscore
    """
    This function normalizes the distance measures in the results using Z-scores,
    sums the normalized values for each comparison run, and appends the zscore_sum
    to the respective result dictionaries.

    Args:
    results (list of dicts): Each dictionary contains distance measures (cosine, jaccard, compression, containment)
                             for each comparison run.

    Returns:
    list of dicts: Updated results with an additional 'zscore_sum' key for each run.
    """
    
    # Create the distance matrix from the results, explicitly replacing None with np.nan
    distance_matrix = np.array([
        [
            np.nan if result.get("cosine") is None else result["cosine"],
            np.nan if result.get("jaccard") is None else result["jaccard"],
            np.nan if result.get("compression") is None else result["compression"],
            np.nan if result.get("containment") is None else result["containment"]
        ]
        for result in results
    ])
    
    # Normalize each distance column using z-scores, ignoring NaN values
    normalized_distances = np.apply_along_axis(lambda col: zscore(col, nan_policy='omit'), axis=0, arr=distance_matrix)

    # Sum the normalized distances for each comparison run
    zscore_sum = normalized_distances.sum(axis=1)
    
    # Append the z-score sum to each result
    for idx, result in enumerate(results):
        result['zscore_sum'] = zscore_sum[idx]
    
    return results

def _calculate_zscore_sum_anos(df) -> pl.DataFrame:
    import numpy as np
    from scipy.stats import zscore, rankdata
    """
    This function normalizes the distance measures in the DataFrame using Z-scores,
    sums the normalized values for each comparison run, and appends the zscore_sum
    as a new column to the DataFrame.

    Args:
    df (pl.DataFrame): DataFrame containing distance measures (e.g., kmeans_pred_ano_proba,
                       IF_pred_ano_proba, RM_pred_ano_proba, OOVD_pred_ano_proba).

    Returns:
    pl.DataFrame: Updated DataFrame with an additional 'zscore_sum' column.
    """
    # Define the columns to normalize
    if isinstance(df, pl.DataFrame): 
        distance_columns = ["kmeans_pred_ano_proba", "IF_pred_ano_proba", "RM_pred_ano_proba", "OOVD_pred_ano_proba"]
        # Replace None with np.nan for compatibility with numpy operations
        df = df.with_columns([pl.col(col).fill_nan(np.nan) for col in distance_columns])
        # Convert Polars DataFrame to a list of dictionaries
        results = df.to_dicts()
    elif isinstance(df, list):
        distance_columns = ["cosine", "jaccard", "compression", "containment"]
        results = df
    else:
        raise ValueError(f"Error: Unsupported datatype: {type(df)}. Supported types are: pl.DataFrame and list")
    
    # Create the distance matrix from the results, explicitly replacing None with np.nan
    distance_matrix = np.array([
        [
            np.nan if result.get(col) is None else result[col]
            for col in distance_columns
        ]
        for result in results
    ])
    
    # Normalize each distance column using z-scores, ignoring NaN values
    normalized_distances = np.apply_along_axis(lambda col: zscore(col, nan_policy='omit'), axis=0, arr=distance_matrix)

    # Sum the normalized distances for each comparison run
    zscore_sum = normalized_distances.sum(axis=1)
    
    # Compute ranks for each distance column, ignoring NaN values
    rank_matrix = np.apply_along_axis(lambda col: rankdata(col, nan_policy='omit'), axis=0, arr=distance_matrix)
    
    # Sum the ranks for each comparison run
    rank_sum = rank_matrix.sum(axis=1)
    
    # Add the z-score sum and rank sum to each result
    for idx, result in enumerate(results):
        result['zscore_sum'] = zscore_sum[idx]
        result['rank_sum'] = rank_sum[idx]
    
    # If the input was Polars Datafame convert the updated results back to a Polars DataFrame
    if isinstance(df, pl.DataFrame): 
        return pl.DataFrame(results)
    elif isinstance(df, list):
        return results
    else:
        raise ValueError(f"Error: Unsupported datatype: {type(df)}. Supported types are: pl.DataFrame and list")
    
    #return updated_df

def _normalize_measure_columns(df, columns):
    """Min-Max normalize a set of columns belonging to the same measure."""
    # Combine all numeric columns to find the global min and max
    #combined_non_nulls = df.select(columns).drop_nulls()
    df = df.select(columns)
    combined_non_nulls = df.with_columns(pl.all().fill_null(pl.all().median()))
    # Calculate the global minimum and maximum across the columns in this group
    measure_min = combined_non_nulls.min().select(pl.all()).to_numpy().min()  # Get scalar min
    measure_max = combined_non_nulls.max().select(pl.all()).to_numpy().max()  # Get scalar max

    if measure_max == measure_min:
        return df  # No normalization needed if min and max are the same

    # Normalize each column in the measure group using its own min-max
    return df.select([
        ((df[col] - measure_min) / (measure_max - measure_min)).alias(col) for col in columns
    ])

def _ano_plot_line_scores(df, title, display_mode="markers"):
    # Define the different sets of measures
    measure_groups = {
        "kmeans": [col for col in df.columns if "kmeans" in col],
        "IF": [col for col in df.columns if "IF" in col],
        "RM": [col for col in df.columns if "RM" in col],
        "OOVD": [col for col in df.columns if "OOVD" in col]
    }

    # Assuming line_number or row_nr represents the index (X-axis)
    line_numbers = df['line_number'].to_list()
    m_messages = df['m_message'].to_list()  # Hover text for each point
    
    # Create an empty DataFrame for normalized data
    df_normalized = df

    # Normalize each measure group separately
    for measure, columns in measure_groups.items():
        if columns:
            df_normalized = df_normalized.with_columns(
                _normalize_measure_columns(df, columns)
            )
    
    # Create a figure
    fig = go.Figure()

    # Add traces for each normalized column
    for measure, columns in measure_groups.items():
        for col in columns:
            if col in df_normalized.columns:
                fig.add_trace(go.Scatter(
                    x=line_numbers,
                    y=df_normalized[col].to_list(),
                    mode=display_mode,  # Use the display_mode parameter ('lines', 'markers', or 'lines+markers')
                    name=col,
                    #text=m_messages,  # Set m_message as the hover text
                    text=[f"Log: {msg[:100]}<br>{msg[100:205]}" for ln, msg in zip(line_numbers, m_messages)],  # Break into two lines for m_message                    hoverinfo='text',  # Show only the text in the tooltip
                    connectgaps=False,  # Show gaps where there are None values
                    marker=dict(symbol="x", size=4),
                ))
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title="Line Number",
        yaxis_title="Normalized Anomaly Score (0-1)",
        template="plotly_white",
    )
    
    # Show plot in HTML format
    return fig

def anomaly_run(df, target_run, comparison_runs="ALL", file = False, detectors=["KMeans"], mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Detect anomalies at the run level.
    
    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to analyze.
    - comparison_runs: Optional list of run names to compare against. If ALL, compares against all other runs.
    - file: Flag to indicate do use file names (True) or file contents (False)
    """
    df, field = _prepare_content(df, mask, content_format=content_format)    
    df_anos_merge = pl.DataFrame()
    target_run_names = _check_multiple_target_runs(df, target_run)
    
    print(f"Executing {inspect.currentframe().f_code.co_name} with {'file' if file else 'content'} format:{content_format} vectorizer:{vectorizer} anomalies of {len(target_run_names)} target runs with {comparison_runs} comparison runs")
    print(f"Target runs: {target_run_names}")
    print(f"Comparison runs: {comparison_runs}")
    for target_run_name in target_run_names:
        df_run1, comparison_run_names = _prepare_runs(df, target_run_name, comparison_runs)
        df_run1 = _aggregate_dataframe(df_run1, 'run', field)
        df_other_runs = df.filter(pl.col("run").is_in(comparison_run_names))
        df_other_runs = _aggregate_dataframe(df_other_runs, 'run', field)
        #else:
        #    df_run1 = df_run1.group_by("run").agg(pl.col(field).alias(field))
        #    df_other_runs = df.filter(pl.col("run").is_in(comparison_run_names)).group_by("run").agg(pl.col(field).alias(field))
        df_anos = _run_anomaly_detection(df_run1, df_other_runs, detectors=detectors, field= field)
        comparison_runs_out = " ".join(comparison_run_names)
        df_anos = df_anos.with_columns(pl.lit(comparison_runs_out).alias("comparison_runs"))
        df_anos_merge = df_anos_merge.vstack(df_anos)
        print(".", end="", flush=True)
    print()  # Newline after progress dots
    #df_anos_merge = pl.DataFrame(_calculate_zscore_sum_anos(df_anos_merge.to_dict()))
    df_anos_merge = _calculate_zscore_sum_anos(df_anos_merge)
    _write_output(df_anos_merge, analysis="ano", level=1 if file else 2, target_run="Many", comparison_run="Many", mask=mask, file_name_prefix=file_name_prefix)

def anomaly_file_content(df, target_run, comparison_runs="ALL", target_files="ALL", detectors=["KMeans"], mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If ALL, compares against all other runs.
    """
    df, field = _prepare_content(df, mask, content_format=content_format) 

    target_run_names = _check_multiple_target_runs(df, target_run)
    # Extract unique runs
    df_anos_merge = pl.DataFrame() 
    for target_run in target_run_names:
        df_run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
        # Generate output CSV file name based on base run
        print(
            f"Executing {inspect.currentframe().f_code.co_name} with format:{content_format}, vectorizer:{vectorizer}, target_run:{target_run}, field:{field} and {len(comparison_run_names)} comparison runs"
            + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
        )
        target_files = _prepare_files(df_run1, target_files)
        print(f"Predicting {len(target_files)} files: {target_files}")
        df_other_runs = df.filter(pl.col("run").is_in(comparison_run_names))
        #df_anos_merge = pl.DataFrame()
        df_other_runs_files = _aggregate_dataframe(df_other_runs,'file_name', field)

        for file_name in target_files:
            
            df_run1_files =  df_run1.filter(pl.col("file_name") == file_name)
            df_run1_files = _aggregate_dataframe(df_run1_files, 'file_name', field)
            if df_other_runs_files.height == 0:
                print(f"Found no files matching files in comparisons runs for file: {file_name}")
                continue

            #df_anos = _run_anomaly_detection(df_run1_files,df_other_runs_files,detectors=detectors, field= field)
            df_anos = _run_anomaly_detection(df_run1_files,df_other_runs_files, field= field, detectors=detectors, vectorizer=vectorizer)

            df_anos = df_anos.with_columns(pl.lit(file_name).alias("file_name"))
            df_anos = df_anos.with_columns(pl.lit(target_run).alias("target_run"))
            df_anos = df_anos.with_columns(pl.lit(" ".join(comparison_run_names)).alias("comparison_runs"))
            df_anos_merge = df_anos_merge.vstack(df_anos)
            print(".", end="", flush=True) #Progress on screen
        print()  # Newline after progress dots
    df_anos_merge = _calculate_zscore_sum_anos(df_anos_merge)
    _write_output(df_anos_merge, analysis="ano", level=3, target_run=target_run, comparison_run="Many", mask=mask, content_format=content_format, vectorizer=vectorizer, file_name_prefix=file_name_prefix)

def anomaly_line_content(df, target_run, comparison_runs="ALL", target_files="ALL", detectors=["KMeans"], mask=False, content_format="Words", vectorizer="Count", file_name_prefix=""):
    """
    Measure distances between one run and specified other runs in the dataframe and save the results as a CSV file.
    
    The output CSV filename will include the name of the base run.

    Parameters:
    - df: Polars DataFrame containing the data with a 'run' column.
    - base_run_name: Name of the run to compare against others.
    - comparison_runs: Optional list of run names to compare against. If ALL, compares against all other runs.
    """
    # Extract unique runs
    df, field = _prepare_content(df, mask, content_format=content_format)
    target_run_names = _check_multiple_target_runs(df, target_run)
    df_anos_merge = pl.DataFrame() 
    for target_run in target_run_names:
        df_run1, comparison_run_names = _prepare_runs(df, target_run, comparison_runs) 
        print(
            f"Executing {inspect.currentframe().f_code.co_name} with format:{content_format}, vectorizer:{vectorizer}, target_run:{target_run}, field:{field} and {len(comparison_run_names)} comparison runs"
            + (f": {comparison_run_names}" if len(comparison_run_names) < 6 else "")
        )
        target_files = _prepare_files(df_run1, target_files)
        df_other_runs = df.filter(pl.col("run").is_in(comparison_run_names))
        print(f"Predicting {len(target_files)} files: {target_files}")
        # Loop over each file first
        for file_name in target_files:
            df_run1_files =  df_run1.filter(pl.col("file_name") == file_name)
            df_other_runs_files = df_other_runs.filter(pl.col("file_name") == file_name)
            if df_other_runs_files.height == 0:
                print(f"Found no files matching files in comparisons runs for file: {file_name}")
                continue

            df_anos = _run_anomaly_detection(df_run1_files,df_other_runs_files, field, detectors=detectors, vectorizer=vectorizer)
            #Add moving averages. 
            df_anos_10 = _calculate_moving_average_all_numeric(df_anos, 10)
            df_anos_100 = _calculate_moving_average_all_numeric(df_anos, 100)
            df_anos = df_anos.with_columns(df_anos_10)
            df_anos = df_anos.with_columns(df_anos_100)
            df_anos = df_anos.with_row_index("line_number")
            #Write to file and plot
            _write_output(df_anos, analysis="ano", level=4, target_run=target_run, comparison_run="Many", mask=mask,content_format=content_format, vectorizer=vectorizer,  file=file_name, file_name_prefix=file_name_prefix)
            title = f"Anomaly scores - Normalized:{mask}, Tokenization:{content_format}, Vectorizer:{vectorizer}<br>Target run: {target_run}<br>Target file: {file_name}"
            fig = _ano_plot_line_scores(df_anos, title)
            _write_output(fig, analysis="ano_plot", level=4, target_run=target_run, comparison_run="Many", mask=mask, content_format=content_format, vectorizer=vectorizer, file=file_name, file_name_prefix=file_name_prefix)
            print(".", end="", flush=True) #Progress on screen
        print()  # Newline after progress dots
    print()  # Newline after progress dots

def _aggregate_dataframe(df: pl.DataFrame, group_by_col: str, field: str) -> pl.DataFrame:
    """
    Aggregate a Polars DataFrame based on the data type of the specified field.
    
    This function handles two cases:
    1. List of strings (e.g., lists of words) - explodes the list and then aggregates
    2. Single strings - aggregates directly
    
    Parameters:
    -----------
    df : pl.DataFrame
        Input DataFrame to aggregate
    group_by_col : str
        Column name to group by (e.g., 'run', 'file_name')
    field : str
        Field to aggregate; must be either a string column or a list of strings column
    """    
    dtype = df.select(pl.col(field)).dtypes[0]
    if  dtype == pl.datatypes.List(pl.datatypes.Utf8): #We get list of str, e.g. words
        return (df
                .select(group_by_col, field)
                .explode(field)
                .group_by(group_by_col)
                .agg(pl.col(field)))
    elif dtype  == pl.datatypes.Utf8: #We get strs 
        return (df
                .group_by(group_by_col)
                .agg(pl.col(field).alias(field)))
    else: 
        raise ValueError(f"Error: Unsupported datatype {dtype} in field {field}. Supported types are: Utf8, List[Utf8]")

def _run_anomaly_detection(df_run1_files,df_other_runs_files, field, detectors=["KMeans", "RarityModel"], vectorizer="Count"):
    """
    Run anomaly detection using specified models.
    
    Parameters:
    - df_other_runs_files: DataFrame for training data.
    - df_run1_files: DataFrame for testing data.
    - field: Column name used by the AnomalyDetector as the item list column.
    - detectors: List of detector names to run (e.g., ["KMeans", "IsolationForest", "RarityModel"]).
                 If None, all detectors are run.
                 
    Returns:
    - DataFrame containing the predictions from the specified anomaly detectors.
    """
    # Initialize the AnomalyDetector
    sad = AnomalyDetector(item_list_col=field, print_scores=False, auc_roc=True)
    
    # Set the training and testing data
    sad.train_df = df_other_runs_files
    sad.test_df = df_run1_files
    
    # Create the vectorizer (Count or Tfidf)

    if vectorizer == "Count":
        vectorizer_class = CountVectorizer
    elif vectorizer == "Tfidf":
        vectorizer_class = TfidfVectorizer
    else:
        raise ValueError(f"Unsupported vectorizer type: {vectorizer}")

    # Prepare the data
    sad.prepare_train_test_data(vectorizer_class=vectorizer_class)
    
    # Initialize the output DataFrame
    df_anos = None
    
    # Run specified detectors or all if none are specified
    if detectors is None or "KMeans" in detectors:
        sad.train_KMeans()
        df_anos = sad.predict()
        df_anos = df_anos.rename({"pred_ano_proba": "kmeans_pred_ano_proba"})
    
    if detectors is None or "IsolationForest" in detectors:
        sad.train_IsolationForest()
        predictions = sad.predict().select("pred_ano_proba").rename({"pred_ano_proba": "IF_pred_ano_proba"})
        if df_anos is not None:
            df_anos = df_anos.with_columns(predictions)
        else:
            df_anos = predictions
    
    if detectors is None or "RarityModel" in detectors:
        sad.train_RarityModel()
        predictions = sad.predict().select("pred_ano_proba").rename({"pred_ano_proba": "RM_pred_ano_proba"})
        if df_anos is not None:
            df_anos = df_anos.with_columns(predictions)
        else:
            df_anos = predictions

    if detectors is None or "OOVDetector" in detectors:    
        #sad.X_train=None
        #sad.labels_train = None
        #sad.train_OOVDetector(filter_anos=False) #This just creates the object. No training for OOVD needed
        sad.train_OOVDetector() 
        predictions = sad.predict().select("pred_ano_proba").rename({"pred_ano_proba": "OOVD_pred_ano_proba"})
        if df_anos is not None:
            df_anos = df_anos.with_columns(predictions)
        else:
            df_anos = predictions

    return df_anos

def _write_output(df, analysis, level=0, target_run="", comparison_run="", file="", mask=False, content_format="", vectorizer="", file_name_prefix="", separator='\t', quote_style='always'):
    """
    Construct the file name and write a Polars DataFrame to a CSV file, creating directories if they don't exist.

    Parameters:
    - df: The Polars DataFrame to write.
    - analysis: A string indicating the type of analysis ('dis' for distance, 'ano' for another type).
    - level: An integer representing the level (default is 0).
    - target_run: A string representing the target run.
    - comparison_run: A string representing the comparison run.
    - file: Additional file information or identifier to include in the file name.
    - separator: The separator to use in the CSV file (default is '\t' for tab-separated).
    - quote_style: The quote style for writing the CSV file (default is 'always').
    """

   
    # Start constructing the output file name with the analysis type
    output_csv = file_name_prefix + "_" + analysis if file_name_prefix else analysis
    
    # Append the level to the file name
    output_csv += f"_L{level}"


    # Append the target and comparison run identifiers if they are provided
    if target_run:
        output_csv += f"_{target_run}"
    if comparison_run:
        output_csv += f"_vs_{comparison_run}"

    output_csv += f"_mask={mask}"

    if content_format:
        output_csv += f"_format={content_format}"
    if vectorizer:
        output_csv += f"_vec={vectorizer}"


    
    # Append the additional file identifier if provided
    if file:
        sanitized_file_name = file.replace('/', '_').replace('\\', '_')
        output_csv += f"_{sanitized_file_name}"
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    output_csv += f"_{timestamp}"
    # Finalize the file name with the CSV extension

    global output_folder
    output_directory = os.path.join(script_dir, output_folder)    
    # Ensure the directory exists; if not, create it
    os.makedirs(output_directory, exist_ok=True)
    # Construct the full path for the CSV file
    output_path = os.path.join(output_directory, output_csv)
    global table_output
    if isinstance(df, pl.DataFrame):
        if table_output == "xlsx":
            output_path += ".xlsx"
            df.write_excel(output_path)
        else:
            output_path += ".csv"
            if table_output != "csv":
                print (f"Unknown table_output:{table_output}. Valid options are: xlsx and csv. Defaulting to csv")
            #Identify columns that are not nested. CSV writer cannot handel them
            non_nested_columns = [
                col for col, dtype in zip(df.columns, df.dtypes)
                if not isinstance(dtype, (pl.List, pl.Struct, pl.Array))
            ]
            # Step 2: Select non-nested columns and write to CSV
            df.select(non_nested_columns).write_csv(output_path, separator='\t')
        
    else:
        output_path += ".html"
        df.write_html(output_path)
    #print(f"Results saved to {output_path}")
    
