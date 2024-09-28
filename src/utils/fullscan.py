import os
import sys
import requests
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from datetime import datetime, timezone, timedelta
from tzlocal import get_localzone
import time
import pytz
from urllib.parse import urljoin, quote

# Import helper functions
from utils.helpers import load_config_new, ConfigManager, remove_empty_folders, check_rate_limits, localize_reset_timestamp, get_and_print_local_time, format_time_difference, get_current_time


config_manager = ConfigManager()
# Access configuration variables
debug_mode = config_manager.debug_mode
initial_setup_done = config_manager.initial_setup_done
local_directory = config_manager.local_directory
github_token = config_manager.github_token
last_run_date = config_manager.last_run_date
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

# Define paths to directory trees
local_tree_path = "utils/local_directory_tree.txt"
repo_tree_path = "utils/repo_directory_tree.txt"

# Set dry_run flag
dry_run = False


def get_tree_contents(owner, repo, subdirectory='', sha=branch_name):

    # Initialize the array to hold the tree data
    tree_data = []

    # Initialize the parent directory variable to keep track of full paths
    parent_directory = ""

    # if file_paths_repo is None:
        # file_paths_repo = []

    def fetch_tree(owner, repo, parent_directory, subdirectory='', sha=branch_name, recursive=''):

        # Ensure subdirectory always ends with a path separator
        if parent_directory!= '':
            parent_directory = os.path.normpath(parent_directory)
            if not parent_directory.endswith(os.sep):
              parent_directory += os.sep
        # print(f"Parent directory before fetching response is: {parent_directory}")  # Debugging

        url = f'https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}{recursive}'
        # print(f"Fetching response with URL: {url}\n") # Debugging
        headers = {'Authorization': f'Bearer {github_token}', 'X-GitHub-Api-Version': '2022-11-28'}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            # Handle error as needed
            print(response.json())
            print(f"\nERROR: Unable to fetch repository tree. Status code: {response.status_code}. \nAPI rate limit probably exceeded. Try again later. The limit resets every hour. You can see the exact reset time above at the beginning of this output.\n")
            print("Terminating the process. Hasta la vista, baby.\n")
            sys.exit(1)

        fetched_response = response.json().get('tree', [])
        fetched_response_is_truncated = response.json().get('truncated')

        if fetched_response_is_truncated == False:
            # print(f"\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n")  # Debugging
            # print(f"Tree IS NOT truncated")  # Debugging
            # print(f"Parent directory is: {parent_directory}")  # Debugging
            for item in fetched_response:  # Ensure each item is appended
                full_path = os.path.join(parent_directory, item['path'])
                item['path'] = full_path
                tree_data.append(item)
            # print(f"Appended tree_data with fetched_response.")  # Debugging

            return fetched_response, fetched_response_is_truncated

        if fetched_response_is_truncated == True:
            
            # print(f"\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n")  # Debugging
            # print(f"Tree IS truncated")  # Debugging
            # print(f"Parent directory is: {parent_directory}")  # Debugging
            # print(f"{fetched_response}")  # Debugging

            # Fetch the tree non-recursively
            fetched_response, fetched_response_is_truncated = fetch_tree(owner, repo, parent_directory, subdirectory, sha)
            
            # print(f"\nFetched response without recursive: {fetched_response}\n")  # Debugging
            # print(f"Fetched response without recursive. Looping though the sha's...")  # Debugging

            # Loop through all of the hashes in the non-recursive tree and run the recursive fetch on each one
            for item in fetched_response:
                full_path = os.path.join(parent_directory, item['path'])  # Keep track of full path
                if item['type'] == 'tree':
                    # print(f"SHA is tree. Fetching recursive response for sha {item['path']}")  # Debugging
                    fetched_response, fetched_response_is_truncated = fetch_tree(owner, repo, full_path, '', item['sha'], '?recursive=1')
                elif item['type'] == 'blob':
                    # print(f"SHA is blob. Appending tree_data for sha {item['path']}")  # Debugging
                    item['path'] = full_path
                    tree_data.append(item)

            return fetched_response, fetched_response_is_truncated


    # Fetch the root tree recursively
    fetched_response, fetched_response_is_truncated = fetch_tree(owner, repo, '', subdirectory, branch_name, '?recursive=1')
    
    # print(f"\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n Final tree_data: {tree_data}\n")  # Debugging
    # print(f"\nDone. Returning tree_data.\n")  # Debugging
    return tree_data

def save_repo_directory_tree_to_file(tree_data, current_path='', file_paths_repo=None, subdirectory=''):
    if file_paths_repo is None:
        file_paths_repo = []

    # Ensure subdirectory always ends with a path separator
    subdirectory = os.path.normpath(subdirectory)
    if not subdirectory.endswith(os.sep):
        subdirectory += os.sep


    for item in tree_data:
        # Normalize the item path
        item_path = os.path.normpath(item['path'])
        # print(f"Comparing Item path:\n{item_path}")  # Debugging
        # print(f"To see if starts with:\n{os.path.join(current_path, subdirectory)}\n\n")  # Debugging

        if item['type'] == 'tree':
            # If it's a directory, recursively call the function
            save_repo_directory_tree_to_file(item.get('contents', []), os.path.join(current_path, item_path), file_paths_repo, subdirectory)
        elif item['type'] == 'blob':
            # If it's a file, append the file path to the list only if it starts with the specified subdirectory
            if item_path.startswith(os.path.join(current_path, subdirectory)):
                file_paths_repo.append(os.path.join(current_path, item_path[len(subdirectory):].lstrip(os.sep).lstrip(os.path.sep)))

    return file_paths_repo


# def get_tree_contents(owner, repo, subdirectory=subdirectory, branch_name=branch_name, github_token=github_token):
#     headers = {
#         'Authorization': f'Bearer {github_token}',
#         'X-GitHub-Api-Version': '2022-11-28'
#     }

#     def fetch_tree(sha, recursive=True):
#         # Fetch the tree for a specific SHA with optional recursion
#         tree_url = f'https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}'
#         if recursive:
#             tree_url += '?recursive=1'
        
#         print(f"Fetching tree from URL: {tree_url}")  # Debugging
#         response = requests.get(tree_url, headers=headers)
#         print(f"Response status code: {response.status_code}")  # Debugging
        
#         if response.status_code != 200:
#             print(response.json())
#             print(f"\nERROR: Unable to fetch repository tree. Status code: {response.status_code}. \nAPI rate limit probably exceeded. Try again later.\n")
#             sys.exit(1)
        
#         return response.json()

#     def handle_directory_contents(sha):
#         # Fetch the tree for a specific SHA
#         tree_data = fetch_tree(sha, recursive=False)
#         contents = tree_data.get('tree', [])
        
#         # Print the contents for debugging
#         print(f"Fetched contents for SHA {sha}: {contents}")  # Debugging
        
#         expanded_contents = []
#         directories = [item for item in contents if item['type'] == 'tree']
#         files = [item for item in contents if item['type'] != 'tree']
        
#         # Fetch contents of subdirectories manually
#         for directory in directories:
#             print(f"Fetching directory contents for: {directory['path']}")  # Debugging
#             subdirectory_contents = handle_directory_contents(directory['sha'])
#             expanded_contents.extend(subdirectory_contents)
        
#         expanded_contents.extend(files)
#         return expanded_contents

#     # Fetch the root tree (main branch or other specified branch) with recursion
#     print(f"Fetching root tree for branch: {branch_name}")  # Debugging
#     root_data = fetch_tree(branch_name, recursive=True)
#     tree_contents = root_data.get('tree', [])
    
#     # Print the root data for debugging
#     print(f"Root data: {root_data}")  # Debugging
    
#     # Optionally filter by subdirectory
#     if subdirectory:
#         # Fetch the subdirectory tree recursively if specified
#         print(f"Filtering contents by subdirectory: {subdirectory}")  # Debugging
#         subdirectory_sha = None
#         for item in tree_contents:
#             if item['path'] == subdirectory and item['type'] == 'tree':
#                 subdirectory_sha = item['sha']
#                 break
        
#         if subdirectory_sha:
#             tree_contents = fetch_tree(subdirectory_sha, recursive=True).get('tree', [])
#         else:
#             print(f"Subdirectory {subdirectory} not found.")
#             tree_contents = []
#     else:
#         # If no subdirectory is specified, fetch all contents recursively
#         tree_contents = fetch_tree(branch_name, recursive=True).get('tree', [])
    
#     # Print final tree contents for debugging
#     print(f"Final tree contents: {tree_contents}")  # Debugging
    
#     return tree_contents








# def save_repo_directory_tree_to_file(tree_data, current_path='', file_paths_repo=None, subdirectory=''):
#     if file_paths_repo is None:
#         print(f"file_paths_repo is none.")  # Debugging
#         file_paths_repo = []

#     # Ensure subdirectory always ends with a path separator
#     subdirectory = os.path.normpath(subdirectory)
#     if not subdirectory.endswith(os.sep):
#         subdirectory += os.sep


#     for item in tree_data:
#         print(f"Processing item in tree_data.")  # Debugging
#         # Normalize the item path
#         item_path = os.path.normpath(item['path'])
#         if item['type'] == 'tree':
#             print(f"Item type is tree.\n")  # Debugging
#             # If it's a directory, recursively call the function
#             save_repo_directory_tree_to_file(item.get('contents', []), os.path.join(current_path, item_path), file_paths_repo, subdirectory)
#         elif item['type'] == 'blob':
#             print(f"Item type is a blob.\n")  # Debugging
#             # If it's a file, append the file path to the list only if it starts with the specified subdirectory
#             if item_path.startswith(os.path.join(current_path, subdirectory)):
#                 file_paths_repo.append(os.path.join(current_path, item_path[len(subdirectory):].lstrip(os.sep).lstrip(os.path.sep)))
#             else:
#                 print(f"Skipping file {item_path} because it doesn't start with the specified subdirectory {subdirectory}.\n")  # Debugging

#     return file_paths_repo


def save_local_directory_tree_to_file(directory, subdirectory, terminal_text, output_file=local_tree_path):
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for file_name in files:
            # Ignore hidden files and folders like the .git folder and .gitignore file
            if not file_name.startswith(('.git', '.DS', '._')):
                full_path = os.path.relpath(os.path.join(root, file_name), directory)
                # print(f"Full path is: {full_path}")  # Debugging
                # Make sure that if there is SLUS folder specified, we're only adding paths for files in that folder
                if slus_folder is None or not slus_folder or full_path.startswith(slus_folder):
                    # print(f"Full path is: {full_path}")  # Debugging
                    relative_path = os.path.relpath(os.path.join(root, file_name), directory)
                    path_to_add = os.path.join(subdirectory, relative_path)
                    file_paths.append(path_to_add)

    # Sort the file paths alphabetically
    file_paths.sort()

    # Save the sorted file paths to output_file
    with open(output_file, 'w') as file:
        for file_path in file_paths:
            file.write(file_path + '\n')

    terminal_text.insert(tk.END, "Directory tree generated for the local directory.\n")
    sys.stdout.flush()  # Force flush the output


def build_full_path(base_path, entry):
    return os.path.join(base_path, entry.replace('/', os.path.sep))


def list_files_not_in_repo(local_tree_path, repo_tree_path, local_directory, dry_run=True):
    # Read local directory tree
    with open(local_tree_path, 'r') as local_file:
        local_files = [line.strip() for line in local_file.readlines()]

    # Read repo directory tree
    with open(repo_tree_path, 'r') as repo_file:
        repo_files = [line.strip() for line in repo_file.readlines()]

    # Build full paths using the provided base path
    local_full_paths = [os.path.join(local_directory, entry) for entry in local_files]
    repo_full_paths = [os.path.join(local_directory, entry) for entry in repo_files]

    # Filter out files with "user-customs" in their path and filenames starting with a dash ("-\n")
    local_full_paths = [path for path in local_full_paths if "user-customs" not in path and not os.path.basename(path).startswith("-")]
    repo_full_paths = [path for path in repo_full_paths if "user-customs" not in path]

    # Filter out files without "SLUS-XXXXX/replacements/" in their path
    replacements_path = os.path.join(slus_folder, "replacements")
    local_full_paths = [path for path in local_full_paths if replacements_path in path]
    repo_full_paths = [path for path in repo_full_paths if replacements_path in path]

    # Find files in local directory but not in the repo directory
    files_to_delete = set(local_full_paths) - set(repo_full_paths)

    return files_to_delete



def list_files_to_download(local_tree_path, repo_tree_path, local_directory, terminal_text, dry_run=True):

    # Check if the local files already exist on the computer
    with open(local_tree_path, 'r') as local_file:
        local_files = [line.strip() for line in local_file.readlines()]

    # Build full paths using the provided base path
    local_full_paths = [os.path.join(local_directory, entry) for entry in local_files]


    # Read repo directory tree
    with open(repo_tree_path, 'r') as repo_file:
        repo_files = [line.strip() for line in repo_file.readlines()]

    # Build full paths using the provided base path
    repo_full_paths = [os.path.join(local_directory, entry) for entry in repo_files]

    # Filter out files with "user-customs" in their path and filenames starting with a dash ("-\n")
    local_full_paths = [path for path in local_full_paths if "user-customs" not in path and not path.split("/")[-1].startswith("-")]
    repo_full_paths = [path for path in repo_full_paths if "user-customs" not in path]

    # Find files in repo directory but not in the local directory
    files_to_download = set(repo_full_paths) - set(local_full_paths)
    
    # Check for prepended files with a dash and exclude them if the original file exists
    for file_to_download in list(files_to_download):
        original_filename = os.path.basename(file_to_download)
        prepended_file = os.path.join(os.path.dirname(file_to_download), "-" + original_filename)
        if os.path.exists(os.path.join(local_directory, prepended_file)):
            files_to_download.discard(file_to_download)

    # Remove local_directory from the paths
    files_to_download = [os.path.relpath(path, local_directory) for path in files_to_download]

    # Filter paths that do not begin with "SLUS-XXXXX/replacements/"
    files_to_download = [path for path in files_to_download if path.startswith(f"{slus_folder}\\replacements\\") or path.startswith(f"{slus_folder}/replacements/")]

    # Check if the local file already exists on the computer before further processing
    files_to_download = [path for path in files_to_download if not os.path.exists(os.path.join(local_directory, path))]

    return files_to_download



def delete_files_not_in_repo(files_to_delete, terminal_text, dry_run=True):

    # Check if there are files to be deleted
    if files_to_delete:
        terminal_text.insert(tk.END, "\nWAITING FOR YOUR RESPONSE IN THE POP-UP DIALAOG WINDOW...\n")
        sys.stdout.flush()  # Force flush the output
        # Prompt the user to continue with deletion
        if not dry_run:
            confirmation_message = (
                "Files were found to exist locally that are not in Github. These could cause issues. It is advised to delete them."
                "\nIf they are your own custom files or DLC, move them to the 'user-customs' folder where they will be ignored."
                f"\nThe {len(files_to_delete)} files listed in the output window WILL BE DELETED. Do you want to proceed?"
            )
            confirmation = messagebox.askyesno("Confirmation", confirmation_message)

            if confirmation:
                # Delete files
                deleted_files = []
                for file_path in files_to_delete:
                    file_path = os.path.join(local_directory, file_path)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            deleted_files.append(file_path)
                        except Exception as e:
                            messagebox.showerror("Error", f"Error deleting file {file_path}: {e}\n")
                    else:
                        messagebox.showwarning("File Not Found", f"File not found: {file_path}\n")


                # Print the list of deleted files
                # terminal_text.insert(tk.END, "\nFiles deleted.\n\n")
                # if debug_mode == True:
                terminal_text.insert(tk.END, "\nDeleted these Files:\n\n")
                for deleted_file in deleted_files:
                    terminal_text.insert(tk.END,  f"[-] {deleted_file}\n")
                    sys.stdout.flush()  # Force flush the output

                terminal_text.insert(tk.END, "\nDeleted Files", "\nDeleted files:\n" + "\n".join(deleted_files))
                sys.stdout.flush()  # Force flush the output
            else:
                terminal_text.insert(tk.END, "\nDeletion cancelled.\n\n")
                sys.stdout.flush()  # Force flush the output
        else:
            terminal_text.insert(tk.END, "\nDry Run", "(Dry run) Deletion cancelled.\n\n")
            sys.stdout.flush()  # Force flush the output
    else:
        terminal_text.insert(tk.END, "\n*** No Stray Files to Delete ***", "\nYou don't have any extra files that aren't in the Github repo (other than your custom textures and DLC in the 'user-customs'). Great!\n\n")
        terminal_text.insert(tk.END, "\n")
        sys.stdout.flush()  # Force flush the output


# DOWNLOAD MISSING 
def download_missing_files(github_repo_url, local_directory, branch_name, files_to_download, github_token, terminal_text, debug_mode=False):
    api_base_url = f"https://api.github.com/repos/{github_repo_url}/contents/textures/"
    headers = {"Authorization": f"Bearer {github_token}"} if github_token else {}
    counter_files_downloaded = 0

    for relative_path in files_to_download:
        # Replace %5C with slashes, if any
        corrected_path = relative_path.replace("%5C", "/\n").replace("\\", "/\n")
        # Construct the API URL for the file
        api_url = urljoin(api_base_url, f"{corrected_path}?ref={branch_name}\n")
        page = 1

        while api_url:

            try:
                response = requests.get(api_url, headers=headers)
                response.raise_for_status()

                file_info = response.json()
                download_url = file_info.get('download_url')

                
                if download_url:
                    file_path = os.path.join(local_directory, relative_path)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)


                    if not os.path.exists(file_path):
                        # Download the file using the provided download_url
                        download_response = requests.get(download_url, headers=headers)

                        if download_response.status_code == 200:
                            with open(file_path, 'wb') as file:
                                file.write(download_response.content)
                            counter_files_downloaded += 1
                            terminal_text.insert(tk.END, f"Downloaded: {relative_path}\n")
                            sys.stdout.flush()
                            terminal_text.yview(tk.END) 
                            terminal_text.see(tk.END)  
                        else:
                            terminal_text.insert(tk.END, f"Failed to download file: {relative_path}\n\n")
                            sys.stdout.flush()
                            terminal_text.yview(tk.END) 
                            terminal_text.see(tk.END) 
                    else:
                        terminal_text.insert(tk.END, f"Skipping existing file: {relative_path}\n\n")
                        sys.stdout.flush()
                        terminal_text.yview(tk.END) 
                        terminal_text.see(tk.END) 
                else:
                    terminal_text.insert(tk.END, f"Download URL not available for file: {relative_path}\n\n")
                    sys.stdout.flush()
                    terminal_text.yview(tk.END) 
                    terminal_text.see(tk.END) 

                # Check for pagination information in the response headers
                link_header = response.headers.get('Link')
                api_url = get_next_page_url(link_header)
                page += 1

            except requests.exceptions.RequestException as e:
                terminal_text.insert(tk.END, f"Failed to fetch file information. Error: {e}\n\n")
                sys.stdout.flush()
                terminal_text.yview(tk.END) 
                terminal_text.see(tk.END) 

    return counter_files_downloaded


def get_next_page_url(link_header):
    if link_header:
        links = link_header.split(', ')
        for link in links:
            url, rel = link.split('; ')
            if 'rel="next"' in rel:
                return url.strip('<>')
    return None


def download_files_not_in_local(files_to_download, terminal_text, dry_run=True):

    # Check if there are files to download
    if files_to_download:
        terminal_text.insert(tk.END, "\nWAITING FOR YOUR RESPONSE IN THE POP-UP DIALAOG WINDOW...\n")
        sys.stdout.flush()
        # Prompt the user to continue with downloading
        if not dry_run:
            confirmation_message = (
                "You're missing files that are in the Github repo. This will cause issues! It is highly recommended that you download them now. See the output window for the list of files."
                f"\nOkay to download the {len(files_to_download)} missing files?"
            )
            confirmation = messagebox.askyesno("Confirmation", confirmation_message)

            if confirmation:
                terminal_text.insert(tk.END, "\nDownloading files:\n\n")
                sys.stdout.flush()
                terminal_text.yview(tk.END) 
                terminal_text.see(tk.END)
                # Download files
                download_missing_files(github_repo_url, local_directory, branch_name, files_to_download, github_token, terminal_text, debug_mode=True)
            else:
                terminal_text.insert(tk.END, "\nDownload cancelled.\n\n")
                sys.stdout.flush()
                terminal_text.yview(tk.END) 
                terminal_text.see(tk.END)
        else:
            terminal_text.insert(tk.END, "\nDry Run. Download cancelled.\n\n")
            sys.stdout.flush()
            terminal_text.yview(tk.END) 
            terminal_text.see(tk.END)
    else:
        terminal_text.insert(tk.END, "\n*** No Missing Files to download ***", "\nYou have everything in the Github repo. Great!\n\n")
        terminal_text.insert(tk.END, "\n")
        sys.stdout.flush()
        terminal_text.yview(tk.END) 
        terminal_text.see(tk.END)


def create_message_window(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    # Define the callback function to be executed after the main loop has a chance to run
    def close_messagebox():
        root.destroy()

    confirmation = messagebox.askyesno(title, message)


def run_scan_and_print_output(terminal_text):
  
    def scroll_terminal():
        terminal_text.yview(tk.END) 
        terminal_text.see(tk.END)


    terminal_text.insert(tk.END, "# - - - - - - - - -   Comparing Directory Trees   - - - - - - - - - #\n")
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "\n")  # Add a line break 
    scroll_terminal()

    # Save the local directory tree to a file
    terminal_text.insert(tk.END, f"Analyzing local directory structure...\n")
    terminal_text.insert(tk.END, "\n")
    scroll_terminal()
    save_local_directory_tree_to_file(local_directory, subdirectory, terminal_text)
    terminal_text.insert(tk.END, "\n")
    scroll_terminal()

    # Get the contents of the github repo root directory 
    terminal_text.insert(tk.END, f"Analyzing Github repo directory structure...\n")
    terminal_text.insert(tk.END, "\n")
    scroll_terminal()

    # Step 1: Fetch the repository tree
    tree_data = get_tree_contents(owner, repo, subdirectory, branch_name)

    # Step 2: Process the tree data and get file paths
    file_paths_repo = save_repo_directory_tree_to_file(tree_data, subdirectory=subdirectory)

    # Sort the file paths alphabetically
    file_paths_repo.sort()

    # Save the sorted file paths to repo_directory_tree.txt
    with open(repo_tree_path, 'w') as file:
        for file_path in file_paths_repo:
            file.write(file_path + '\n')

    terminal_text.insert(tk.END, "Directory tree generated for the Github repository.\n")
    scroll_terminal()


    # PROCEED TO PRUNING OR DOWNLOADING -------------------------
    terminal_text.insert(tk.END, "\nComparing the Github repo directory structure to your local textures folder...\n")
    scroll_terminal()


    # Perform the deletion of local files not in the repo (or dry run) with user prompt
    files_to_delete = list_files_not_in_repo(local_tree_path, repo_tree_path, local_directory, dry_run)
    if files_to_delete:
        terminal_text.insert(tk.END, "\nEXTRA Files to be Deleted:\n\n")
        scroll_terminal()

        for file_path in files_to_delete:
            terminal_text.insert(tk.END, f"- {file_path}\n")
            scroll_terminal()

    # Delete the files or print a message saying no files to delete
    delete_files_not_in_repo(files_to_delete, terminal_text, dry_run)
    scroll_terminal()


    # Perform the download of missing files with user prompt
    files_to_download = list_files_to_download(local_tree_path, repo_tree_path, local_directory, terminal_text, dry_run)
    if files_to_download:
        terminal_text.insert(tk.END, "\nMISSING Files to Download:\n\n")
        scroll_terminal()
        for file_path in files_to_download:
            if file_path.startswith(f"{slus_folder}/replacements/\n"):
                # Remove the prefix before printing
                terminal_text.insert(tk.END, f"- {file_path[len(f'{slus_folder}/replacements/'):]}\n")
            else:
                # Print as-is
                terminal_text.insert(tk.END, f"- {file_path}\n")
            scroll_terminal()

    # Download the files or print a message saying no files to download
    download_files_not_in_local(files_to_download, terminal_text, dry_run)
    scroll_terminal()


    # Call the function to delete empty folders after syncing files
    remove_empty_folders(local_directory, debug_mode=False)

    terminal_text.insert(tk.END, "\n")  # Add a line break 
    terminal_text.insert(tk.END, "#                                                                   #\n")
    terminal_text.insert(tk.END, "# - - - - - -   Finished Directory Trees Comparison   - - - - - - - #\n")
    terminal_text.insert(tk.END, "\n")
    scroll_terminal()