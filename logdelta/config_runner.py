import os
import yaml
import warnings
from dotenv import load_dotenv, find_dotenv
from loglead.enhancers import EventLogEnhancer

import logdelta.log_analysis_functions as log_analysis_functions
from logdelta.log_analysis_functions import (
    set_output_folder_and_format, read_folders, distance_run_file, distance_run_content,
    distance_file_content, distance_line_content,
    plot_run, plot_file_content,
    anomaly_file_content, anomaly_line_content,
    anomaly_run
)


import logdelta.regex_masking as regex_masking
from logdelta.data_specific_preprocessing import preprocess_files
import inspect
import sys
def load_config(config_path):
    """
    Load the YAML configuration file.
    Resolves relative paths to absolute paths based on the script's directory.
    """
    invocation_dir = os.getenv("PWD")
    if not invocation_dir:
    # Fallback if PWD isn't set (e.g., on some systems)
        invocation_dir = os.getcwd()
    if not os.path.isabs(config_path):
        # Make the config path relative to the current working directory
        config_path = os.path.join(invocation_dir, config_path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def main(config_path):
    # Load configuration
    config = load_config(config_path)
    print(f"Starting loaded config: {config_path}")

    # Set output folder
    output_folder = config.get('output_folder')
    table_output = config.get('table_output')
    set_output_folder_and_format(output_folder, table_output)

    # Set input data folder
    input_data_folder = config.get('input_data_folder')
    if not input_data_folder:
        input_data_folder = os.getenv("LOG_DATA_PATH")
        if not input_data_folder:
            print("WARNING!: LOG_DATA_PATH is not set. This will most likely fail")
    # Read data
    df, _ = read_folders(input_data_folder)
 
    
    # Check if masking is enabled
    enhancer = EventLogEnhancer(df)
    if config['regex_masking']['enabled']:
        # Retrieve and apply patterns
        print("Masking data")
        patterns = config['regex_masking']['pattern']  # This is a list of patterns
        if len(patterns) > 1:
            print("Warning: Multiple masking patterns detected. Only the last masking will have an effect.") #https://github.com/EvoTestOps/LogLead/issues/38
        
        # Apply the patterns in a loop (currently only the last one will be used)
        for pattern in patterns:
            pattern_name = pattern['name']
            print(f"Applying pattern: {pattern_name}")
            if hasattr(regex_masking, pattern_name):
                pattern_list = getattr(regex_masking, pattern_name)
                df = enhancer.normalize(regexs=pattern_list)
            else:
                print(f"Unknown masking pattern: {pattern_name}")
    else:
        print("Masking is disabled.")

    # Check if pre-parse is enabled
    if config['pre_parse']['enabled'] and config['regex_masking']['enabled']:
        # Retrieve and apply patterns
        print("Parsing event templates")
        parsers = config['pre_parse']['parsers']  # This is a list of patterns
        
        # Apply the patterns in a loop (currently only the last one will be used)
        for parser in parsers:
            parser_name = parser['name']
            method_name = parser_name.split("-")[1].lower()
            method_name = f"parse_{method_name}"
            print(f"Parsing with: {parser_name}")
        # Dynamically call the corresponding method if it exists
            if hasattr(enhancer, method_name):
                method = getattr(enhancer, method_name)
                df = method()
            else:
                raise ValueError(f"No parse method found for {parse_type}")
    else:
        print("No pre-parsing")

    # Data-specific preprocessing
    df = preprocess_files(df, config.get('preprocessing_steps', []))

    #Start analysis steps
    steps = config.get('steps', {})
    # Map step types that need to be handled differently
    special_cases = {
        'plot_run_file': {'func_name': 'plot_run', 'fixed_args': {'file': True, 'content_format':'File'}},
        'plot_run_content': {'func_name': 'plot_run', 'fixed_args': {'file': False}},
        'anomaly_run_file': {'func_name': 'anomaly_run', 'fixed_args': {'file': True, 'content_format':'File'}},
        'anomaly_run_content': {'func_name': 'anomaly_run', 'fixed_args': {'file': False}},
    }

    for step_type, configs in steps.items():
        for config_item in configs:
            # Determine function to call
            if step_type in special_cases:
                func_name = special_cases[step_type]['func_name']
                fixed_args = special_cases[step_type]['fixed_args']
            else:
                func_name = step_type
                fixed_args = {}

            # Get the function from the module
            func = getattr(log_analysis_functions, func_name, None)

            if func is None:
                print(f"Function {func_name} not found")
                continue

            # Get function parameters
            func_params = inspect.signature(func).parameters

            # Build kwargs
            kwargs = {k: v for k, v in config_item.items() if k in func_params}

            # Add fixed args
            kwargs.update(fixed_args)

            # Add df
            kwargs['df'] = df

            # Call the function
            func(**kwargs)

    print(f"Done! See output in folder: {output_folder}")


def cli():
    """Entry point for the `config-runner` console script and for `python -m logdelta.config_runner`.

    `main()` takes the config path as an argument so it stays callable from Python; everything that
    only makes sense when invoked from a shell — dotenv, warning filters, argument parsing — lives
    here.
    """
    # Load environment variables
    load_dotenv(find_dotenv())

    # Set working directory
    #script_dir = os.path.dirname(os.path.abspath(__file__))
    #os.chdir(script_dir)

    # Suppress specific warnings
    warnings.filterwarnings("ignore", "WARNING! data has no labels. Only unsupervised methods will work.", UserWarning)

    # Determine if running in an IPython environment
    try:
        __IPYTHON__
        ipython_env = True
    except NameError:
        ipython_env = False

    if ipython_env:
        # Running in IPython/Jupyter
        config_path = os.path.abspath("config.yml") 
    else:
        # Parse command-line arguments
        import argparse
        parser = argparse.ArgumentParser(description="LogDelta")
        parser.add_argument(
            "-c", "--config",
            default="config.yml",
            help="Path to the configuration file (default: config.yml)"
        )
        args = parser.parse_args()
        config_path = args.config

    # Run main process
    main(config_path)


if __name__ == "__main__":
    cli()
