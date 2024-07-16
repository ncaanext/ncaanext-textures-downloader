import os
import requests
import base64
import hashlib
from datetime import datetime, timezone
from tzlocal import get_localzone
from email.utils import parsedate_to_datetime
import tempfile
import shutil
import argparse
import pytz
from urllib.parse import urljoin, quote

def load_config(config_path):
    config = {
        "local_directory": "",
        "github_token": "",
        "last_run_date": None
        # Add other configuration variables as needed
    }

    try:
        with open(config_path, 'r') as config_file:
            for line in config_file:
                parts = line.split(':')
                if len(parts) >= 2:
                    key = parts[0].strip().lower()
                    value = ':'.join(parts[1:]).strip()
                    if key in config:
                        config[key] = value
                        if key == "last_run_date":
                            try:
                                config["last_run_date"] = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f').replace(microsecond=0)
                            except ValueError:
                                print("Invalid last_run_date format in config file.")
    except FileNotFoundError:
        pass
    
    return config

def load_config_new(config_path="config.txt"):
    # File path for the configuration file
    config_file_path = config_path

    # Dictionary to store key-value pairs
    config_dict = {}

    # Read existing content from the file
    with open(config_file_path, 'r') as file:
        lines = file.readlines()

    # Iterate through each line in the file
    for line in lines:
        # Split each line into key and value
        parts = line.strip().split(':')
        if len(parts) >= 2:
            variable_name = parts[0].strip()
            value = ':'.join(parts[1:]).strip()

            # Check if the variable is 'last_run_date' and modify its value
            if variable_name == 'last_run_date':
                if value and value.strip():  # Check if value is not None and not an empty string
                    try:
                        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M:%S.%f')
                    except (ValueError, TypeError):
                        # Handle the case where the format is not correct
                        value = None
                else:
                    # Handle the case where the value is None or an empty string
                    value = None

            # Check if the value looks like a datetime string and convert it
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except (ValueError, TypeError):
                pass  # Continue with the original value if it's not a valid datetime

            # Add the key-value pair to the dictionary
            config_dict[variable_name] = value

    return config_dict

def save_config_new(config_dict, config_path="config.txt"):
    # File path for the configuration file
    config_file_path = config_path

    # Read existing content from the file
    with open(config_file_path, 'r') as file:
        lines = file.readlines()

    # Iterate through each key-value pair in the dictionary
    for variable_name, value in config_dict.items():
        found = False

        # Iterate through each line to find the key
        for i in range(len(lines)):
            if lines[i].startswith(f'{variable_name}:'):
                # If key is found, update the line with the new value
                lines[i] = f'{variable_name}: {value}\n'
                found = True
                break

        # If the key is not found, add a new line
        if not found:
            lines.append(f'{variable_name}: {value}\n')

    # Write the updated content back to the file
    with open(config_file_path, 'w') as file:
        file.writelines(lines)


class ConfigManager:
    def __init__(self):
        self.config = load_config_new()

    def save_config(self, config_dict):
        self.config.update(config_dict)
        save_config_new(self.config)

    @property
    def debug_mode(self):
        return self._convert_to_boolean(self.config.get("debug_mode"))
    @property
    def initial_setup_done(self):
        return self._convert_to_boolean(self.config.get("initial_setup_done"))
    @property
    def local_directory(self):
        return self.config.get("local_directory")
    @property
    def github_token(self):
        return self.config.get("github_token")
    @property
    def last_run_date(self):
        return self.config.get("last_run_date")
    @property
    def project_name(self):
        return self.config.get("project_name")
    @property
    def owner(self):
        return self.config.get("owner")
    @property
    def repo(self):
        return self.config.get("repo")
    @property
    def branch_name(self):
        return self.config.get("branch_name")
    @property
    def subdirectory(self):
        return self.config.get("subdirectory")
    @property
    def slus_folder(self):
        return self.config.get("slus_folder")
    @property
    def json_url(self):
        return self.config.get("json_url")
    @property
    def github_repo_url(self):
        return f"{self.owner}/{self.repo}"
    @property
    def user_choice_var(self):
        return None

    def _convert_to_boolean(self, value):
        if value is None:
            return False
        elif isinstance(value, bool):
            return value
        elif isinstance(value, str) and value.lower() == "true":
            return True
        else:
            return False

    @initial_setup_done.setter
    def initial_setup_done(self, value):
        self.config['initial_setup_done'] = self._convert_to_boolean(value)
        self.save_config({'initial_setup_done': self._convert_to_boolean(value)})
            


def is_hidden(entry):
    # Check if a file or folder is hidden.
    return entry.startswith('.')

def remove_empty_folders(path_abs, debug_mode=False):
    deleted_any = False  # Flag to track if any directories were deleted

    while True:
        walk = list(os.walk(path_abs))
        removed_any = False

        for path, dirs, files in walk[::-1]:
            # Filter out hidden files and folders
            non_hidden_dirs = [d for d in dirs if not is_hidden(d)]
            non_hidden_files = [f for f in files if not is_hidden(f)]

            if len(non_hidden_dirs) == 0 and len(non_hidden_files) == 0:
                if debug_mode == True:
                    print(f"Deleting empty folder: {path}")
                try:
                    shutil.rmtree(path)
                    removed_any = True
                    deleted_any = True  # Set the flag to True if any directory is deleted
                except OSError as e:
                    if debug_mode == True:
                        print(f"Error deleting folder {path}: {e}")

        if not removed_any:
            break

    if deleted_any:
        print("\nEmpty directories pruned.")

def check_rate_limits(github_token):
    headers = {"Authorization": f"Bearer {github_token}"}
    rate_limit_url = "https://api.github.com/rate_limit"
    response = requests.get(rate_limit_url, headers=headers)

    if response.status_code == 200:
        limits = response.json()
        return limits['resources']['core']
    else:
        print(f"Failed to fetch rate limits. Status Code: {response.status_code}")
        return None

def is_remote_file_newer(file_url, file_path, commit_date, debug_mode=False):
    # Check if the local file exists and compare last modified timestamps
    if os.path.exists(file_path):
        local_last_modified = datetime.utcfromtimestamp(os.path.getmtime(file_path))
        if debug_mode == True:
            print(f"  Local Last Modified: {local_last_modified}")

            print(f"  Commit Date: {commit_date}")  # Debugging output
            print(f"  Comparing dates for file: {file_path}")  # Debugging output

        if commit_date > local_last_modified:
            if debug_mode == True:
                print("  Commit date is newer.")
            return True
        else:
            if debug_mode == True:
                print("  Local file is newer or same.")
            return False
    return True  # Download if the local file doesn't exist

def compute_local_file_hash(file_path, debug_mode=False):
    with open(file_path, 'rb') as f:
        data = f.read()
    s = hashlib.sha1()
    # Add blob, size of file and '\0' character
    s.update(("blob %u\0" % len(data)).encode('utf-8'))
    s.update(data)   
    return s.hexdigest()


def compare_hashes(local_hash, github_hash, file_path, debug_mode=False):
    return local_hash == github_hash


def localize_reset_timestamp(limit_reset_timestamp):
    try:
        # Try to get the local timezone of the user
        user_timezone = get_localzone()
    except Exception as e:
        print(f"Error: {e}")
        # Fallback to UTC if unable to determine the user's timezone
        user_timezone = pytz.utc

    # Convert to local time with user's timezone information using pytz
    reset_time_utc = datetime.utcfromtimestamp(limit_reset_timestamp).replace(tzinfo=timezone.utc)
    reset_time_local = reset_time_utc.astimezone(user_timezone)

    # Get the timezone abbreviation (e.g., CET, ET)
    timezone_abbreviation = reset_time_local.strftime('%Z')

    reset_time_local_str = reset_time_local.strftime('%Y-%m-%d %H:%M:%S') 

    local_time_string = f"{reset_time_local_str} {timezone_abbreviation}"

    return local_time_string

def get_current_time():
    """Get the current time in the user's timezone (with a fallback to UTC) and return it in time format"""
    try:
        # Try to get the local timezone of the user
        user_timezone = get_localzone()
    except Exception as e:
        print(f"Error: {e}")
        # Fallback to UTC if unable to determine the user's timezone
        user_timezone = pytz.utc

    # Get the current time in the user's timezone or UTC
    current_time = datetime.now(user_timezone)

    return current_time

def get_and_print_local_time():
    """Get the current time in the user's timezone (with a fallback to UTC) and return a print string"""
    # Use the already defined get_current_time function
    current_time = get_current_time()

    # Get the timezone abbreviation (e.g., CET, ET)
    timezone_abbreviation = current_time.strftime('%Z')

    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S') 

    local_time_string = f"{current_time_str} {timezone_abbreviation}"

    return local_time_string

def format_time_difference(start_time, end_time):
    time_difference = end_time - start_time

    hours, remainder = divmod(time_difference.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    formatted_time = ""
    if hours > 0:
        formatted_time += f"{hours} hr "
    if minutes > 0 or hours == 0:
        formatted_time += f"{minutes} min "
    formatted_time += f"{seconds} sec"

    return formatted_time

def check_for_dupes(folder):
    """Takes a folder and checks it recursively for non-unique filenames and prints output"""
    def find_duplicate_png_files(folder):
        png_files = {}
        duplicate_sets = []

        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith('.png'):
                    file_path = os.path.join(root, file)
                    if file in png_files:
                        existing_file_path = png_files[file]
                        duplicate_set = {existing_file_path, file_path}
                        duplicate_sets.append(duplicate_set)
                    else:
                        png_files[file] = file_path

        return duplicate_sets

    duplicate_sets = find_duplicate_png_files(folder)

    print()  # Add a line break 
    print("# - - - - - - -  Starting Duplicate Textures Finder   - - - - - - - #")
    print("#                                                                   #")
    print()
    print("Checking recursively in the replacements folder to ensure all filenames are unique...")
    print()

    if duplicate_sets:
        print()
        print("******  WARNING: Duplicate texture names found  ***********")
        print("*                                                         *")
        print("*  We aren't deleting these because the Github repo has   *")
        print("*  the same duplicate files. However, two files with the  *")
        print("*  same name anywhere in replacements will cause issues.  *")
        print("*  It's recommended you alert the maker of the mod about  *")
        print("*  these, and keep an eye on them in your installation   *")
        print("*  (or delete the one you know is not the correct one).   *")
        print("*                                                         *")
        print("*                                                         *")
        for idx, duplicate_set in enumerate(duplicate_sets, start=1):
            print(f"\nDuplicate Set {idx}:")
            for duplicate in duplicate_set:
                print(duplicate)
        print()
    else:
        print()
        print("Success. No duplicate PNG files found!")
        print()

    print()  # Add a line break 
    print("#                                                                   #")
    print("# - - - - - - -  Finished Duplicate Textures Finder   - - - - - - - #")
    print()