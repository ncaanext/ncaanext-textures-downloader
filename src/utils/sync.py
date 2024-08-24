import os
import sys
import requests
import base64
import hashlib
from datetime import datetime, timezone, timedelta
import time
import pytz
from email.utils import parsedate_to_datetime
import tempfile
import shutil
import argparse
import tkinter as tk 
import threading
import traceback


from .helpers import *
from .fullscan import *

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--user_choice', type=str, default='only_new_content',
                    help='Specify whether to do a full scan or only check for new or modified files.')
args = parser.parse_args()

config_manager = ConfigManager()
# Access configuration variables
debug_mode = config_manager.debug_mode
initial_setup_done = config_manager.initial_setup_done
local_directory = config_manager.local_directory
# github_token = config_manager.github_token
# last_run_date = config_manager.last_run_date
project_name = config_manager.project_name
owner = config_manager.owner
repo = config_manager.repo
branch_name = config_manager.branch_name
subdirectory = config_manager.subdirectory
slus_folder = config_manager.slus_folder
json_url = config_manager.json_url
# Other variables
github_repo_url = config_manager.github_repo_url
# Initialize user_choice_var as a global variable
user_choice_var = config_manager.user_choice_var

# Initialize counter for commits newer than last sync date
counter_valid_commits = 0
# Initialize counter for number of files downloaded
counter_files_downloaded = 0
# Initialize counter for number of files deleted
counter_files_deleted = 0

# For write_last_run_date
config_path = "config.txt"




def main_sync(user_choice, terminal_text, github_token, last_run_date):

    terminal_text.insert(tk.END, f"    Full sync choice: {user_choice}\n")
    terminal_text.insert(tk.END, f"    GitHub Token: {github_token}\n")
    terminal_text.insert(tk.END, f"    Last Run Date: {last_run_date}\n")

    # Convert last_run_date to datetime object if it's a string
    if isinstance(last_run_date, str):
        try:
            last_run_date = datetime.strptime(last_run_date, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            # Handle invalid date format
            last_run_date = datetime(2005, 7, 11, 0, 0, 0)


    # For write_last_run_date
    config_path = "config.txt"

    def scroll_terminal():
        terminal_text.yview(tk.END) 
        terminal_text.see(tk.END)

    # Function to write the last run date to config.txt in UTC format
    def write_last_run_date():
        try:
            # Get the current UTC time
            utc_now = datetime.utcnow().replace(microsecond=0, tzinfo=pytz.UTC)
            # Format and convert the UTC time to a string with milliseconds
            utc_time_str = utc_now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            last_run_date = utc_time_str
            save_config_new({'last_run_date': last_run_date})
            terminal_text.insert(tk.END, "Last Sync Date updated.\n")

        except:
            # Handle the case when the file doesn't exist
            terminal_text.insert(tk.END, "Error writing Sync Date updated. Try updating manually.\n")
            scroll_terminal()


    def download_file(url, destination, counter_files_downloaded, commit_date=None, debug_mode=False, hash_comparison=True):

        # Create the folder if it doesn't exist
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        # Check if the file with a prepended dash exists locally
        dashed_file_path = os.path.join(os.path.dirname(destination), '-' + os.path.basename(destination))

        if os.path.exists(dashed_file_path):
            # Check if the dashed file is not newer, download the original file as the dashed file
            if commit_date is None or not hash_comparison:
                with open(dashed_file_path, 'wb') as f:
                    f.write(requests.get(url).content)
                    counter_files_downloaded += 1
                    if debug_mode == 'True':
                        terminal_text.insert(tk.END, f"    Downloaded: {os.path.basename(url)} as {os.path.basename(dashed_file_path)}\n")
                        scroll_terminal()
                    else:
                        terminal_text.insert(tk.END, f"    Downloaded: {os.path.basename(dashed_file_path)}\n")
                        scroll_terminal()
                return counter_files_downloaded  # Return the updated counter
            else:
                terminal_text.insert(tk.END, f"    Skipping download because exists and is current (with prepended dash).\n")
                scroll_terminal()
                return counter_files_downloaded  # Return the current counter

        # Download the file with the original name
        response = requests.get(url)
        if response.status_code == 200:
            with open(destination, 'wb') as f:
                f.write(response.content)
                counter_files_downloaded += 1
                if debug_mode == 'True':
                    terminal_text.insert(tk.END, f"    Downloaded: {os.path.basename(url)} as {os.path.basename(destination)}\n")
                    scroll_terminal()
                else:
                    terminal_text.insert(tk.END, f"    Downloaded: {os.path.basename(destination)}\n")
                    scroll_terminal()
        else:
            terminal_text.insert(tk.END, f"Failed to download file. Status Code: {response.status_code}\n")
            scroll_terminal()

        return counter_files_downloaded  # Return the updated counter




    def download_files(repo_url, local_path, branch='main', subdirectory='', debug_mode=False):
        api_url = f"https://api.github.com/repos/{repo_url}/commits?path={subdirectory}&sha={branch_name}"
        headers = {"Authorization": f"Bearer {github_token}"}
        global counter_files_downloaded  # Declare the global variable
        global counter_files_deleted  # Declare the global variable
        global counter_valid_commits  # Declare the global variable

        # Keeping track of finished, deleted and renamed files so they don't get re-downloaded
        finished_files_set = set()



        def add_to_finished_files_set(file_path, debug_mode=False):
            if file_path not in finished_files_set:
                finished_files_set.add(file_path)
                if debug_mode == 'True':
                  terminal_text.insert(tk.END, f"    Added to finished files set: {file_path}\n")
                  scroll_terminal()
            else:
                if debug_mode == 'True':
                    terminal_text.insert(tk.END, f"    File already exists in finished files set.\n")
                    scroll_terminal()
        
        # Standard first line
        def starter_line(file_status, relative_path):
            if file_status == 'added':
                bullet = '[+]'
            elif file_status == 'modified':
                bullet = '[~]'
            elif file_status == 'renamed':
                bullet = '[=]'
            else:
                bullet = '[-]'
            terminal_text.insert(tk.END, f"\n{bullet} {file_status} in commit: {relative_path}\n")
            scroll_terminal()


        while api_url:

            terminal_text.after(100)

            response = requests.get(api_url, headers=headers)

            if response.status_code == 200:
                commits = response.json()
                

                for commit in commits:
                    commit_date = datetime.strptime(commit['commit']['author']['date'], '%Y-%m-%dT%H:%M:%SZ')
                    commit_hash = commit['sha'][:7]

                    if user_choice == 'full_scan' or commit_date > last_run_date:
                        counter_valid_commits += 1
                        terminal_text.insert(tk.END, "\n")
                        terminal_text.insert(tk.END, f"****** GIT COMMIT ({commit_hash}) DATE: {commit_date} ******\n")
                        scroll_terminal()
                        commit_sha = commit['sha']
                        files_url = f"https://api.github.com/repos/{repo_url}/commits/{commit_sha}?path={subdirectory}&sha={branch_name}"
                        files_response = requests.get(files_url, headers=headers)

                        try:
                            files_response = requests.get(files_url, headers=headers, timeout=10)  # Adding a timeout value


                            if files_response.status_code == 200:
                                files_info = files_response.json()['files']

                                while 'next' in files_response.links:
                                    next_page_url = files_response.links['next']['url']
                                    files_response = requests.get(next_page_url, headers=headers)
                                    files_info += files_response.json()['files']

                                for file_info in files_info:
                                    file_status = file_info.get('status')  # New, modified, or deleted
                                    file_sha = file_info.get('sha')  # hash

                                    if debug_mode == 'True':
                                        terminal_text.insert(tk.END, f"======== NEXT FILE ==============\n")
                                        self.terminal_text.yview(tk.END) 
                                        terminal_text.see(tk.END)
                                    
                                    # Get the URL to the item
                                    file_url = file_info.get('raw_url')
                                    # Get the name of the file or folder
                                    file_or_folder_name = os.path.basename(file_info['filename'])
                                    # Build the relative path
                                    relative_path = os.path.relpath(file_info['filename'], start=subdirectory)

                                    # Ignore git and certain (but not all) hidden files and folders
                                    if file_or_folder_name.startswith(('.git', '.DS', '._')):
                                        starter_line(file_status, relative_path)
                                        terminal_text.insert(tk.END, f"    Skipping hidden file or directory.\n")
                                        scroll_terminal()
                                        continue

                                    if 'user-customs' in relative_path:
                                        starter_line(file_status, relative_path)
                                        terminal_text.insert(tk.END, f"    Skipping file with 'user-customs' in its path.\n")
                                        scroll_terminal()
                                        continue

                                    # Check if the file is outside the specified subdirectory but only if the status wasn't "modified" (handle that later)
                                    if file_status != 'renamed':
                                        if debug_mode == 'True':
                                            terminal_text.insert(tk.END, "    Checking if outside of specified directory by seeing if relative_path starts with '..'.\n")
                                            terminal_text.insert(tk.END, f"    relative_path: {relative_path}\n")
                                            scroll_terminal()
                                        if relative_path.startswith('..') or os.path.isabs(relative_path):
                                            if debug_mode == 'True':
                                                starter_line(file_status, relative_path)
                                                terminal_text.insert(tk.END, f"    Outside of specified subdirectory. Skipping file: {file_info['filename']}\n")
                                                scroll_terminal()
                                            else:
                                                starter_line(file_status, relative_path)
                                                terminal_text.insert(tk.END, f"    Skipping download because outside of specified subdirectory.\n")
                                                scroll_terminal()
                                            continue
                                    
                                    # Build the local absolute path
                                    file_path = os.path.join(local_path, relative_path)
                                    if debug_mode == 'True':
                                        terminal_text.insert(tk.END, f"    file_path: {file_path}\n")



                                    # Common for ADDED or MODIFIED or RENAMED
                                    if file_status == 'added' or file_status == 'modified' or file_status == 'renamed':

                                        # Check if the file is has already been processed
                                        if debug_mode == 'True':
                                            terminal_text.insert(tk.END, f"    Checking if in finished_files_set before running hash tests.\n")
                                        if file_path not in finished_files_set:
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    Not in finished_files_set.\n")
                                            if os.path.exists(file_path):
                                                # Compute the local hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"\n  Hash check file path: {file_path}\n")
                                                local_file_hash = compute_local_file_hash(file_path, debug_mode)
                                                # Compare local hash to github file hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"  Comparing hashes for: {file_path}\n")  
                                                hash_comparison = compare_hashes(local_file_hash, file_sha, file_path, debug_mode)
                                            
                                            # Check for prepended version and use that unless there is also the normal/non-prepended version
                                            else:
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, "    LOCAL PATH DOESN'T EXIST. Checking if there is a disabled/prepended version.\n")
                                                    # Split the path into directory and filename
                                                directory, filename = os.path.split(file_path)
                                                # Add a dash before the final segment (filename or folder)
                                                modified_filename = '-' + filename
                                                # Join the directory and modified filename to get the new path
                                                file_path_prepended = os.path.join(directory, modified_filename)
                                                # Check if disabled/prepended version exists
                                                if os.path.exists(file_path_prepended):
                                                    # Redefine file_path to prepended name
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    It exists. Modifying path for hash comparison to: {file_path_prepended}\n")
                                                    # Compute the local hash
                                                    if debug_mode == True:
                                                        terminal_text.insert(tk.END, f"  Hash check file path: {file_path}\n")
                                                    local_file_hash = compute_local_file_hash(file_path_prepended, debug_mode)
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Computed hash for file_path_prepended is {local_file_hash}\n")
                                                    # Compare local hash to github file hash
                                                    if debug_mode == True:
                                                        terminal_text.insert(tk.END, f"  Comparing hashes for: {file_path}\n")  
                                                    hash_comparison = compare_hashes(local_file_hash, file_sha, file_path, debug_mode)
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Is remote has same as file_path_prepended: {hash_comparison}\n")
                                                else:
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Disabled/prepended file doesn't exist: {file_path}\n")
                                                    hash_comparison = False
                                            scroll_terminal()
                                        else:
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    In finished_files_set. Skipping hash tests.\n")
                                                scroll_terminal()


                                        # Detailed output for debug mode
                                        if debug_mode == 'True':
                                            # terminal_text.insert(tk.END, f"- {file_status} File: {file_info['filename']}, Relative Path: {relative_path}\n")
                                            starter_line(file_status, relative_path)
                                            terminal_text.insert(tk.END, f"    Remote hash: {file_sha}\n")
                                            scroll_terminal()
                                            # initialize variable
                                            local_file_hash = "" 
                                            if local_file_hash:
                                                terminal_text.insert(tk.END, f"    Local_file_hash exists as {local_file_hash}.\n")
                                                if hash_comparison == True:
                                                    terminal_text.insert(tk.END, f"    Local hash: {local_file_hash}\n")
                                                    terminal_text.insert(tk.END, "    HASHES ARE SAME.\n")
                                                    scroll_terminal()
                                                else:
                                                    terminal_text.insert(tk.END, f"    Local hash: {local_file_hash}\n")
                                                    terminal_text.insert(tk.END, "    DIFFERENT HASHES.\n")
                                                    scroll_terminal()

                                            sys.stdout.flush()
                                        # Normal output
                                        else:
                                            starter_line(file_status, relative_path)
                                    
                                    
                                    # ADDED or MODIFIED
                                    if file_status == 'added' or file_status == 'modified':

                                        # Check if the file is has already been processed
                                        if debug_mode == 'True':
                                            terminal_text.insert(tk.END, f"    Checking if in finished_files_set.\n")
                                            scroll_terminal()
                                        if file_path in finished_files_set:
                                            terminal_text.insert(tk.END, f"    Skipping because already processed in a newer commit.\n")
                                            scroll_terminal()
                                            continue
                                        else:
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    Not in finished_files_set.\n")
                                              
                                        if file_status == 'added':
                                            if not os.path.exists(file_path) or not hash_comparison:
                                                counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                            else:
                                                terminal_text.insert(tk.END, f"    Skipping download because file exists and matches github file.\n")
                                            # Add to finished file set to skip processing in older commits
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    Adding to the finished_files_set.\n")
                                            add_to_finished_files_set(file_path, debug_mode)   
                                            scroll_terminal()
                                            continue  
                                            
                                          
                                        if file_status == 'modified':
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    Check if hash is different before downloading: {file_path}\n")  # Debugging output
                                                scroll_terminal()
                                            if not os.path.exists(file_path) or not hash_comparison:
                                                # Download the file (or prepended file) and update the counter
                                                counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                            else:
                                                terminal_text.insert(tk.END, f"    Skipping download because files are identical.\n")
                                                scroll_terminal()
                                            # Add to finished file set to skip processing in older commits
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, f"    Adding to the finished_files_set.\n")
                                                scroll_terminal()
                                            add_to_finished_files_set(file_path, debug_mode)   
                                            scroll_terminal()
                                            continue  
                                            
                                    elif file_status == 'renamed':
                                        old_file_relative_path = os.path.relpath(file_info['previous_filename'], start=subdirectory)
                                        old_file_path = os.path.join(local_path, old_file_relative_path)
                                        new_file_path = file_path
                                        new_file_dir = os.path.dirname(new_file_path)

                                        # Info on what happened in the commit
                                        if debug_mode == 'True':
                                            terminal_text.insert(tk.END, f"    In commit, {old_file_relative_path} renamed to {relative_path}.\n")
                                            scroll_terminal()
                                        
                                        try:

                                            # Check if the file is has already been processed
                                            if file_path in finished_files_set:
                                                # Add the old name if it's not already in the set
                                                terminal_text.insert(tk.END, f"    Skipping because new or old path already processed in a newer commit.\n")
                                                scroll_terminal()
                                                if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Adding old path to the finished_files_set. New path was already there.\n")
                                                        scroll_terminal()
                                                add_to_finished_files_set(old_file_path)  
                                                scroll_terminal()
                                                continue 

                                            # Check if activity was all outside of the subdirectory and skip to next file if so
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, "    Checking if all activity was outside of specified directory by seeing if relative_paths both start with '..'.\n")
                                                terminal_text.insert(tk.END, f"    New path: {relative_path}\n")
                                                terminal_text.insert(tk.END, f"    Old Path: {old_file_relative_path}\n")
                                                scroll_terminal()
                                            # Checking both old and new file names 
                                            if relative_path.startswith('..') or os.path.isabs(relative_path):
                                                if old_file_relative_path.startswith('..') or os.path.isabs(old_file_relative_path):
                                                    terminal_text.insert(tk.END, f"    Old name and new name outside of specified subdirectory. Skipping file.\n")
                                                    scroll_terminal()
                                                    continue
                                            else:
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, "    One or both of the old/new filenames are inside the specified subdirectory. Proceeding...\n")


                                            # Check if new file name is outside of the subdirectory, and if so, just delete the local file instead of moving it
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, "    Checking if the new/desination file name is outside of the specified subdirectory by seeing if its relative path starts with '..'.\n")
                                                terminal_text.insert(tk.END, f"    New path: {relative_path}\n")
                                                scroll_terminal()
                                            # Checking new file name
                                            if relative_path.startswith('..') or os.path.isabs(relative_path):
                                                if debug_mode:
                                                    terminal_text.insert(tk.END, f"    New name is outside of specified directory. Looking for the old file...\n")
                                                # terminal_text.update_idletasks()
                                                # terminal_text.after(100)
                                                # Check if old file exists
                                                if os.path.exists(old_file_path):
                                                    if debug_mode:
                                                        terminal_text.insert(tk.END, f"    Found the old name file Deleting...\n")
                                                    os.remove(old_file_path)
                                                    counter_files_deleted += 1
                                                    terminal_text.insert(tk.END, f"    Deleted {file_info['previous_filename']}\n")
                                                else:
                                                    terminal_text.insert(tk.END, f"    File has already been deleted locally.\n")
                                                    terminal_text.yview(tk.END) 
                                                    terminal_text.see(tk.END)
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                add_to_finished_files_set(old_file_path)  
                                                add_to_finished_files_set(new_file_path)  

                                                # terminal_text.update_idletasks()
                                                # terminal_text.after(100)
                                                continue


                                            # Check if new old name is outside of the subdirectory, and if so, download the new name file
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, "    Checking if the old file name is outside of the specified subdirectory by seeing if its relative path starts with '..'.\n")
                                                terminal_text.insert(tk.END, f"    Old path: {old_file_path}\n")
                                                scroll_terminal()
                                            # Checking new file name
                                            if old_file_relative_path.startswith('..') or os.path.isabs(old_file_relative_path):
                                                if debug_mode:
                                                    terminal_text.insert(tk.END, f"    Old name is outside of specified directory. Downloading the new file.\n")
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                add_to_finished_files_set(old_file_path)  
                                                add_to_finished_files_set(new_file_path)  
                                                counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                                scroll_terminal()

                                                terminal_text.update_idletasks()
                                                terminal_text.after(100)
                                                continue

                                            # Check for the old filename to see if the file exists
                                            if os.path.exists(old_file_path):
                                                # File with the old name exists, compute the hash and compare it with the GitHub file hash

                                                # Compute the local hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"\n  Hash check for old file path: {old_file_path}\n")
                                                local_file_hash = compute_local_file_hash(old_file_path, debug_mode)

                                                # Compare local hash to GitHub file hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"  Comparing hashes for: {old_file_path}\n")
                                                hash_comparison = compare_hashes(local_file_hash, file_sha, old_file_path, debug_mode)

                                                if hash_comparison:
                                                    # Hashes match, proceed with renaming the file
                                                    terminal_text.insert(tk.END, f"    Hashes match. Proceeding with renaming the file.\n")
                                                else:
                                                    # Hashes don't match, download the file
                                                    terminal_text.insert(tk.END, f"    Hashes don't match. Downloading the correct version of the file.\n")
                                                    counter_files_downloaded = download_file(file_url, old_file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)

                                                # Create directory if needed
                                                if not os.path.exists(new_file_dir):
                                                    try:
                                                        os.makedirs(new_file_dir)
                                                        # terminal_text.insert(tk.END, f"    Created missing directories: {new_file_dir}\n")
                                                        scroll_terminal()
                                                    except Exception as e:
                                                        terminal_text.insert(tk.END, f"    ERROR creating directories: {e}\n")
                                                        terminal_text.insert(tk.END, traceback.format_exc())
                                                        scroll_terminal()
                                                        continue

                                                # Rename the file
                                                os.rename(old_file_path, new_file_path)
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                add_to_finished_files_set(old_file_path)
                                                add_to_finished_files_set(new_file_path)
                                                terminal_text.insert(tk.END, f"    Renamed: {file_info['previous_filename']} to {relative_path}\n")
                                                scroll_terminal()

                                                continue

                                            

                                            # Check for a disabled/prepended version of the old filename
                                            directory, filename = os.path.split(old_file_path)
                                            # Add a dash before the final segment (filename or folder)
                                            modified_old_filename = '-' + filename
                                            # Join the directory and modified filename to get the new path
                                            old_file_path_prepended = os.path.join(directory, modified_old_filename)
                                            
                                            # terminal_text.insert(tk.END, f"    Checking if prepended version of old file exists at {old_file_path_prepended}...\n")

                                            # Check if disabled/prepended version exists
                                            if os.path.exists(old_file_path_prepended):
                                            
                                                # Compute the local hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"\n  Hash check for prepended file path: {old_file_path_prepended}\n")
                                                local_file_hash = compute_local_file_hash(old_file_path_prepended, debug_mode)

                                                # Compare local hash to GitHub file hash
                                                if debug_mode == True:
                                                    terminal_text.insert(tk.END, f"  Comparing hashes for: {old_file_path_prepended}\n")
                                                hash_comparison = compare_hashes(local_file_hash, file_sha, old_file_path_prepended, debug_mode)

                                                if hash_comparison:
                                                    # Hashes match, proceed with renaming the file
                                                    terminal_text.insert(tk.END, f"    Hashes match. Proceeding with renaming the prepended file.\n")
                                                else:
                                                    # Hashes don't match, download the file
                                                    terminal_text.insert(tk.END, f"    Hashes don't match. Downloading the correct version of the file.\n")
                                                    counter_files_downloaded = download_file(file_url, old_file_path_prepended, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                                
                                                # Ensure the destination directory exists
                                                new_file_dir = os.path.dirname(new_file_path)
                                                if not os.path.exists(new_file_dir):
                                                    try:
                                                        os.makedirs(new_file_dir)
                                                        # terminal_text.insert(tk.END, f"    Created missing directories: {new_file_dir}\n")
                                                        scroll_terminal()
                                                    except Exception as e:
                                                        terminal_text.insert(tk.END, f"    ERROR creating directories: {e}\n")
                                                        terminal_text.insert(tk.END, traceback.format_exc())
                                                        scroll_terminal()
                                                        continue
                                                
                                                # Disabled/prepended file with the old name exists, rename it to the new name
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Old file name doesn't exist, but a disabled/prepended file with the old name exists. Renaming it to the new name.\n")
                                                    # terminal_text.insert(tk.END, f"    From: {old_file_path_prepended}\n")
                                                    # terminal_text.insert(tk.END, f"    To: {new_file_path}\n")
                                                    scroll_terminal()

                                                # Create a path and name for the new prepended file location
                                                directory_new, filename_new = os.path.split(new_file_path)
                                                # Add a dash before the final segment (filename or folder)
                                                modified_new_filename = '-' + filename_new
                                                # Join the directory and modified filename to get the new path
                                                new_file_path_prepended = os.path.join(directory_new, modified_new_filename)
                                                    
                                                try:
                                                    os.rename(old_file_path_prepended, new_file_path_prepended)
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                    add_to_finished_files_set(old_file_path)  
                                                    add_to_finished_files_set(new_file_path)  
                                                    terminal_text.insert(tk.END, f"    Renamed: {modified_old_filename} version of to {relative_path}\n")
                                                    scroll_terminal()
                                                except Exception as e:
                                                    terminal_text.insert(tk.END, f"    ERROR in renaming file: {e}\n")
                                                    terminal_text.insert(tk.END, traceback.format_exc())  # Logs the traceback
                                                    scroll_terminal()
                                                    continue
                                                
                                            # Check for the new filename to see if file exists and if it is current
                                            elif os.path.exists(new_file_path):
                                                if not hash_comparison:
                                                    # Download the file and update the counter
                                                    terminal_text.insert(tk.END, f"    Downloading because the version of new file on github is newer.\n")
                                                    counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                    add_to_finished_files_set(old_file_path)  
                                                    add_to_finished_files_set(new_file_path)  
                                                else:
                                                    # File with the new name already exists
                                                    if debug_mode == 'True':
                                                        terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                    add_to_finished_files_set(old_file_path)  
                                                    add_to_finished_files_set(new_file_path)  
                                                    terminal_text.insert(tk.END, f"    Skipping download because already exists with the new name and is current.\n")
                                                scroll_terminal()
                                                continue
                                            
                                            else:
                                                # Download the file  and update the counter
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Adding old and new path to the finished_files_set..\n")
                                                add_to_finished_files_set(old_file_path)  
                                                add_to_finished_files_set(new_file_path)  
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Downloading because neither the new or old path exist.\n")
                                                # Proceed to download logic
                                                counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                                                scroll_terminal()

                                        except Exception as e:
                                            terminal_text.insert(tk.END, f"    ERROR processing renamed file: {e}\n")
                                            scroll_terminal()

                                        # terminal_text.update_idletasks()
                                        # terminal_text.after(100)
                                        continue  

                                    elif file_status == 'removed':
                                        
                                        starter_line(file_status, relative_path)

                                        # # Check if the file is outside the specified subdirectory
                                        # if debug_mode == 'True':
                                        #     terminal_text.insert(tk.END, "    Checking if outside of specified directory by seeing if relative_path starts with '..'.\n")
                                        #     terminal_text.insert(tk.END, f"    relative_path: {relative_path}")
                                        # if relative_path.startswith('..') or os.path.isabs(relative_path):
                                        #     if debug_mode == 'True':
                                        #         terminal_text.insert(tk.END, f"    Outside of specified subdirectory. Skipping file: {file_info['filename']}")
                                        #     else:
                                        #         terminal_text.insert(tk.END, f"    Skipping because outside of specified subdirectory.\n")
                                        #     scroll_terminal()
                                        #     continue

                                        # Check if the file is has already been processed
                                        if file_path in finished_files_set:
                                            terminal_text.insert(tk.END, f"    Skipping because already processed in a newer commit.\n")
                                            scroll_terminal()
                                            continue
                                        
                                        # Add to finished file set to skip processing in older commits
                                        if debug_mode == 'True':
                                            terminal_text.insert(tk.END, f"    Adding deleted path to the finished_files_set.\n")
                                        add_to_finished_files_set(file_path, debug_mode)

                                        # If passed all of those checks, check if the file exists, and if so, delete it.
                                        if os.path.exists(file_path):
                                            os.remove(file_path)
                                            counter_files_deleted += 1
                                            if debug_mode:
                                                terminal_text.insert(tk.END, f"    Deleted {file_info['filename']} from {relative_path}\n")
                                            else:
                                                terminal_text.insert(tk.END, f"    Deleted {relative_path}\n")
                                        else:
                                            if debug_mode == 'True':
                                                terminal_text.insert(tk.END, "    LOCAL PATH DOESN'T EXIST. Checking if there is a disabled/prepended version.\n")
                                                scroll_terminal()
                                                # Split the path into directory and filename
                                            directory, filename = os.path.split(file_path)
                                            # Add a dash before the final segment (filename or folder)
                                            modified_filename = '-' + filename
                                            # Join the directory and modified filename to get the new path
                                            file_path_prepended = os.path.join(directory, modified_filename)
                                            # Check if disabled/prepended version exists
                                            if os.path.exists(file_path_prepended):
                                                if debug_mode == 'True':
                                                    terminal_text.insert(tk.END, f"    Prepended version exists at: {file_path_prepended}\n")
                                                    scroll_terminal()
                                                # Delete the prepended version
                                                os.remove(file_path_prepended)
                                                counter_files_deleted += 1
                                                terminal_text.insert(tk.END, f"    Deleted disabled/prepended version because normal named version doesn't exist. \n")
                                                scroll_terminal()
                                            else:
                                                terminal_text.insert(tk.END, f"    File has already been deleted from local.\n")
                                                scroll_terminal()


                                        # scroll_terminal()
                                        # terminal_text.update_idletasks()
                                        # terminal_text.after(100)
                                        continue

                                    
                                    else:
                                        terminal_text.insert(tk.END, f"Unknown file status: {file_status}\n")
                                        scroll_terminal()
                                
                                # Add to finished file set to skip processing in older commits
                                # add_to_finished_files_set(file_path, debug_mode)


                            else:
                                terminal_text.insert(tk.END, f"Failed to fetch files for commit. Status Code: {files_response.status_code}\n")
                                terminal_text.insert(tk.END, f"Commit ({commit_hash}) SHA: {commit_sha}, Commit Date: {commit_date}\n")
                                terminal_text.insert(tk.END, f"Files URL: {files_url}\n")
                                scroll_terminal()

                        except ConnectTimeout:
                            terminal_text.insert(tk.END, f"Connection timed out for commit ({commit_hash}) SHA: {commit_sha}, Commit Date: {commit_date}\n")
                            scroll_terminal()
                        except RequestException as e:
                            terminal_text.insert(tk.END, f"Request failed: {e}\n")
                            scroll_terminal()

                    # else:
                    #     terminal_text.insert(tk.END, "Commit date is not greater than last run date. Skipping commit\n\n")

                if counter_valid_commits < 1:
                    terminal_text.insert(tk.END, "There is no new or modified content in Github since your last sync date.\n")
                    scroll_terminal()
                    terminal_text.update_idletasks()
                    terminal_text.after(100)
                    break  # No need to continue checking older commits

                
                scroll_terminal()
                
            
            
            else:
                terminal_text.insert(tk.END, f"Failed to fetch commits. Status Code: {response.status_code}\n")
                terminal_text.insert(tk.END, f"API URL: {api_url}\n")
                scroll_terminal()
                

            # Check for pagination information in the response headers
            link_header = response.headers.get('Link')
            api_url = get_next_page_url(link_header)


        
        # terminal_text.insert(tk.END, finished_files_set)
        scroll_terminal()


    def get_next_page_url(link_header):
        # Extracts the URL for the next page from the 'Link' header
        if link_header:
            links = link_header.split(',')
            for link in links:
                if 'rel="next"' in link:
                    return link.split(';')[0].strip('<>')
        return None








    def download_directory_contents(repo_url, local_path, branch, directory_path, subdirectory=''):
        terminal_text.insert(tk.END, "download_files function:\n")
        api_url = f"https://api.github.com/repos/{repo_url}/contents/{directory_path}?ref={branch_name}"
        headers = {"Authorization": f"Bearer {github_token}"}

        while api_url:
            terminal_text.insert(tk.END, f"Fetching: {api_url}\n")  # Print the API URL being fetched
            scroll_terminal()
            response = requests.get(api_url, headers=headers)

            if response.status_code == 200:
                files = response.json()
                terminal_text.insert(tk.END, f"Received {len(files)} files\n")  # Print the number of files received
                scroll_terminal()

                for file in files:
                    file_url = file.get('download_url')

                    if file.get('type') == 'dir':
                        download_directory_contents(repo_url, local_path, branch, file['path'], subdirectory)
                    elif file_url:
                        # Preserve directory structure inside the specified subdirectory
                        relative_path = os.path.relpath(file['path'], subdirectory)
                        file_path = os.path.join(local_path, relative_path)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)

                        if not os.path.exists(file_path) or not hash_comparison:
                            # Download the file (or prepended file) and update the counter
                            counter_files_downloaded = download_file(file_url, file_path, counter_files_downloaded, commit_date, debug_mode, hash_comparison)
                        else:
                            terminal_text.insert(tk.END, f"Skipping existing file: {file['path']}\n")
                            scroll_terminal()
                    else:
                        terminal_text.insert(tk.END, f"Skipping file {file['path']} - download URL not available\n")
                        scroll_terminal()
            elif response.status_code == 403:
                terminal_text.insert(tk.END, f"Failed to fetch directory contents. Permission issue. Directory: {directory_path}\n")
            else:
                terminal_text.insert(tk.END, f"Failed to fetch directory contents. Status Code: {response.status_code}\n")

            # Check for pagination information in the response headers
            link_header = response.headers.get('Link')
            api_url = get_next_page_url(link_header)
            terminal_text.insert(tk.END, f"Next page URL: {api_url}\n")  # Print the next page URL
            scroll_terminal()





    # Check the rate limits (limit resets every hour at top of hour)
    limits = check_rate_limits(github_token)

    if limits:
        limit_cap = limits['limit']
        used_calls = limits['used']
        remaining_calls_start = limits['remaining']
        limit_reset_timestamp = limits['reset']
        reset_timestamp_local = localize_reset_timestamp(limit_reset_timestamp)

        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, f"Github API RATE LIMITS status: {used_calls} of {limit_cap} calls used. {remaining_calls_start} remaining until the hourly limit reset at {reset_timestamp_local}.\n")
        # terminal_text.insert(tk.END, f"Raw: {limits}\n")
        terminal_text.insert(tk.END, "\n")
    else:
        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, "Unable to retrieve rate limits.\n")
        terminal_text.insert(tk.END, "\n")


    # Print the current time
    formatted_local_time = get_and_print_local_time()
    terminal_text.insert(tk.END, f"Current time: {formatted_local_time}")
    # Get the starting time to calculate the duration later
    start_time = get_current_time()
    terminal_text.insert(tk.END, "\n")  # Add a line break 
    terminal_text.insert(tk.END, "#######################################################################\n")
    terminal_text.insert(tk.END, "#                                                                     #\n")
    terminal_text.insert(tk.END, "#                         Textures Sync                               #\n")
    terminal_text.insert(tk.END, "#                                                                     #\n")
    terminal_text.insert(tk.END, "#        Reads the history of changes (commits) in Github             #\n")
    terminal_text.insert(tk.END, "#      and compares those file changes with your local files.         #\n")
    terminal_text.insert(tk.END, "#      For existing files, it compares hashes for accurately          #\n")
    terminal_text.insert(tk.END, "#   determining if you have the most recent version of the file.      #\n")
    terminal_text.insert(tk.END, "#                                                                     #\n")
    terminal_text.insert(tk.END, "#              It ignores your 'user-customs' folder.                 #\n")
    terminal_text.insert(tk.END, "#  It recognizes textures you have disabled anywhere in replacements  #\n")
    terminal_text.insert(tk.END, "#    (aka files prepended with a dash, such as '-file.png')           #\n")
    terminal_text.insert(tk.END, "#   and will keep the disabled file updated to its latest version.    #\n")
    terminal_text.insert(tk.END, "#                                                                     #\n")
    terminal_text.insert(tk.END, "#---------------------------------------------------------------------#\n")
    terminal_text.insert(tk.END, "\n")  # Add a line break 
    terminal_text.insert(tk.END, "\n")  # Add a line break 
    scroll_terminal()  # Force flush the output


    # Check for new files and download
    try:
        terminal_text.insert(tk.END, f"Checking for new or modified files since last run date ({last_run_date})...\n")
        terminal_text.insert(tk.END, "\n")
        scroll_terminal()
        # debug_mode_variable_type = type(debug_mode)
        # terminal_text.insert(tk.END, f"debug_mode = {debug_mode} ({debug_mode_variable_type})")
        if debug_mode == True or debug_mode == "True":
          terminal_text.insert(tk.END, "Debug mode is on. Output will be verbose.\n\n")
          scroll_terminal()
        download_files(github_repo_url, local_directory, branch_name, subdirectory, debug_mode)
        terminal_text.insert(tk.END, "\n")
        scroll_terminal()
        # Check the rate limits again to see usage (limit resets every hour at top of hour)
        limits = check_rate_limits(github_token)
        remaining_calls_end = limits['remaining']
        limit_reset_timestamp = limits['reset']
        reset_timestamp_local = localize_reset_timestamp(limit_reset_timestamp)
        terminal_text.insert(tk.END, f"Github API RATE LIMITS status: Used {remaining_calls_start - remaining_calls_end} API calls this sync round. {remaining_calls_end} remaining until the hourly limit reset at {reset_timestamp_local}.\n")
        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, "Finished with textures sync.\n")
        terminal_text.insert(tk.END, f"{counter_files_downloaded} files downloaded.\n")
        terminal_text.insert(tk.END, f"{counter_files_deleted} files deleted.\n")
        terminal_text.insert(tk.END, "\n")
        scroll_terminal()
        # Call the function to delete empty folders after syncing files
        remove_empty_folders(local_directory, debug_mode=False)
        terminal_text.insert(tk.END, "\n")  # Add a line break 
        terminal_text.insert(tk.END, "#                                                                   #\n")
        terminal_text.insert(tk.END, "#     Finished reviewing all changes in specified time period.      #\n")
        terminal_text.insert(tk.END, "#           Comparing directory structure to Github...              #\n")
        terminal_text.insert(tk.END, "#-------------------------------------------------------------------#\n")
        terminal_text.insert(tk.END, "\n")
        scroll_terminal()

        # Save the current run date to the config file
        write_last_run_date()

    except Exception as e:
        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, f"ERROR: {e}\n")
        terminal_text.insert(tk.END, "\n")
        scroll_terminal()

    terminal_text.insert(tk.END, "\n")  # Add a line break 
    terminal_text.insert(tk.END, "#-------------------------------------------------------------------#\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#                      Starting Health Check                        #\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#    Looking for extraneous textures and duplicate filenames...     #\n")
    terminal_text.insert(tk.END, "\n")
    scroll_terminal()

    # Run fullscan to compare directory trees and offer to delete and/or download files
    run_scan_and_print_output(terminal_text)
    scroll_terminal()

    if debug_mode == 'True':
        # Check for duplicate texture names across the entire replacements folder
        replacements_path = os.path.join(local_directory, slus_folder, "replacements")
        check_for_dupes(replacements_path)

    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#                      Finished Health Check                        #\n")
    terminal_text.insert(tk.END, "#-------------------------------------------------------------------#\n")
    scroll_terminal()

    # Check the rate limits (limit resets every hour at top of hour)
    limits = check_rate_limits(github_token)

    if limits:
        limit_cap = limits['limit']
        used_calls = limits['used']
        remaining_calls_start = limits['remaining']
        limit_reset_timestamp = limits['reset']
        reset_timestamp_local = localize_reset_timestamp(limit_reset_timestamp)

        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, f"Github API RATE LIMITS status: {used_calls} of {limit_cap} calls used. {remaining_calls_start} remaining until the hourly limit reset at {reset_timestamp_local}.\n")
        # terminal_text.insert(tk.END, f"Raw: {limits}\n")
        scroll_terminal()  # Force flush the output
    else:
        terminal_text.insert(tk.END, "\n")
        terminal_text.insert(tk.END, "Unable to retrieve rate limits.\n")
        scroll_terminal()  # Force flush the output



    terminal_text.insert(tk.END, "\n")  # Add a line break 
    terminal_text.insert(tk.END, "#-------------------------------------------------------------------#\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#                              DONE!                                #\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#   If you answered yes to the prompts to download and/or delete    #\n")
    terminal_text.insert(tk.END, "#   files (or you didn't get prompted) your local directory and     #\n")
    terminal_text.insert(tk.END, "#   file structure is identical to the Github repository. Great!    #\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#   TIP: The 'Full Sync' option goes beyond the normal directory    #\n")
    terminal_text.insert(tk.END, "#  tree comparison and compares the hashes of every file to ensure  #\n")
    terminal_text.insert(tk.END, "# they are identical, rather than just checking if the file exists. #\n")
    terminal_text.insert(tk.END, "#  It's recommended you run it occassionally (or if having issues). #\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "#####################################################################\n")

    terminal_text.insert(tk.END, f"\n--- SYNC SUMMARY ---\n")
    terminal_text.insert(tk.END, f"{counter_files_downloaded} files downloaded in the Git commits review.\n")
    terminal_text.insert(tk.END, f"{counter_files_deleted} files deleted in the Git commits review.\n")
    terminal_text.insert(tk.END, f"  * These numbers do not include the final health check popups numbers, if any.\n\n")

    scroll_terminal()  # Force flush the output
    # Print the current time
    formatted_local_time = get_and_print_local_time()
    terminal_text.insert(tk.END, f"Current time: {formatted_local_time}")
    # Get the end time and calculate the duration
    end_time = get_current_time()
    formatted_time = format_time_difference(start_time, end_time)
    terminal_text.insert(tk.END, f"\nThe operation took {formatted_time}\n")
    scroll_terminal()  # Force flush the output
