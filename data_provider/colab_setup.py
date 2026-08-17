import os
import sys

def setup_colab_environment():
    """
    Detects if running in Google Colab and adjusts sys.path to include the project's src directory.
    This script assumes it's being run from within the 'notebooks_colab' directory,
    and that the 'src' directory is located one level up, parallel to 'notebooks_colab'.
    """
    in_colab = 'google.colab' in sys.modules

    if in_colab:
        print("Detected Google Colab environment.")
        # Navigate up to the project root and then into 'src'
        current_dir = os.getcwd()
        project_root = os.path.dirname(current_dir) # This gets the parent directory
        src_path = os.path.join(project_root, 'src')
        
        if os.path.exists(src_path) and src_path not in sys.path:
            sys.path.insert(0, src_path)
            print(f"Added '{src_path}' to sys.path for module imports.")
        else:
            print(f"Warning: 'src' directory not found at '{src_path}' or already in sys.path.")
            print(f"Current working directory: {current_dir}")
            print(f"sys.path: {sys.path}")
    else:
        print("Not running in Google Colab. Local environment detected.")
        # For local development, sys.path might already be configured or not needed for this specific setup.
        pass

if __name__ == '__main__':
    setup_colab_environment()
    # Example usage after setup:
    # try:
    #     from data_splitter import DataSplitter
    #     print("Successfully imported DataSplitter (example).")
    # except ImportError:
    #     print("Could not import DataSplitter. Ensure 'src' exists and contains the module.")