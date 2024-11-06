import os
import shutil
import time
from github import Github
from pathlib import Path
import subprocess
import json
from DotNETCLIClient import DotNETCLIClient

# End of Selection

class GitHubClient:
    def __init__(self, token):
        self.github = Github(token)
        self.user = self.github.get_user()
        self.local_path = None
        self.dotnet_cli = DotNETCLIClient()

    def set_local_path(self, path):
        self.local_path = os.path.normpath(path)

    def delete_repository(self, repo_name):
        """
        Delete a repository from GitHub and its local directory
        """
        try:
            # Delete from GitHub
            repo = self.user.get_repo(repo_name)
            repo.delete()
            print(f"Repository '{repo_name}' deleted from GitHub.")

            # Delete local directory
            if self.local_path:
                if os.path.exists(self.local_path):
                    if self.force_delete_directory(self.local_path):
                        print(f"Local directory '{self.local_path}' deleted successfully.")
                    else:
                        print(f"Failed to delete local directory '{self.local_path}'")
            
        except Exception as e:
            print(f"Error deleting repository: {str(e)}")

    def force_delete_directory(self, path):
        """
        Forcefully delete a directory by first removing read-only flags
        and making multiple attempts if needed
        """
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            try:
                # Remove read-only flags
                for root, dirs, files in os.walk(path):
                    for dir in dirs:
                        try:
                            os.chmod(os.path.join(root, dir), 0o777)
                        except Exception:
                            pass
                    for file in files:
                        try:
                            os.chmod(os.path.join(root, file), 0o777)
                        except Exception:
                            pass
                
                # Delete the directory
                shutil.rmtree(path)
                return True
            except Exception as e:
                print(f"Deletion attempt {attempt + 1} failed: {str(e)}")
                attempt += 1
                time.sleep(1)  # Wait a second before retrying
        
        return False
    
    def add_global_json(self, sdk_version):
        """
        Adds a global.json file to the root of the repository to specify the .NET SDK version.

        Parameters:
        - sdk_version (str): The version of the .NET SDK to be specified in the global.json file.
        """
        global_json_content = {
            "sdk": {
                "version": sdk_version
            }
        }
        global_json_path = os.path.join(self.local_path, 'global.json')
        with open(global_json_path, 'w') as global_json_file:
            json.dump(global_json_content, global_json_file, indent=4)
        print(f"global.json file created at {global_json_path}")



    def create_repository(self, repo_name, description="", private=False, base_directory=None, sdk_version="7.0.400"):
        """
        Creates a new GitHub repository and initializes a typical C# project with a specific folder structure
        under the given base directory.

        Parameters:
        - repo_name (str): Name of the repository to create.
        - description (str): Description of the repository.
        - private (bool): If True, creates a private repository.
        - base_directory (str): The base directory under which the repository folder will be created.
        - sdk_version (str): The .NET SDK version to use in global.json. Defaults to "7.0.400".

        Returns:
        - repo (github.Repository.Repository): The created repository object.
        """
        # Check if repository already exists
        try:
            existing_repo = self.user.get_repo(repo_name)
            print(f"Repository '{repo_name}' already exists at {existing_repo.html_url}")
            return existing_repo
        except:
            pass  # Repository does not exist, proceed to create

        # Create the repository on GitHub
        repo = self.user.create_repo(
            name=repo_name,
            description=description,
            private=private,
            auto_init=False  # We'll initialize locally
        )

        print(f"Repository '{repo_name}' created successfully at {repo.html_url}")

        # Determine the project path
        if base_directory:
            project_path = os.path.join(base_directory, repo_name)
        else:
            project_path = os.path.join(os.getcwd(), repo_name)

        
        # Create the local directory for the project
        os.makedirs(project_path, exist_ok=True)

        # Set the local path for the project
        self.set_local_path(project_path)   
        
        # Change the current working directory to the project path
        original_cwd = os.getcwd()
        os.chdir(project_path)

        try:
            # Initialize a local git repository
            subprocess.run(['git', 'init'], check=True)

            # Create the folder structure
            folders = ['src', 'test', 'assets', 'docs', 'lib']
            for folder in folders:
                os.makedirs(folder, exist_ok=True)

            # Add global.json with the specified SDK version
            self.add_global_json(sdk_version)

            # Create solution file in the root directory
            self.dotnet_cli.new_solution(name=repo_name)

            # Initialize a new .NET console project in the 'src' directory using DotNETCLIClient
            os.chdir('src')
            self.dotnet_cli.new_project('console', name=repo_name)
            os.chdir('..')  # Return to the project root directory

            # Add the project to the solution
            sln_path = f"{repo_name}.sln"
            project_path = os.path.join("src", repo_name, f"{repo_name}.csproj")
            self.dotnet_cli.add_project_to_solution(sln_path, project_path)

            # Create a .gitignore file using dotnet CLI
            self.dotnet_cli.new_gitignore()

            # Create a README file
            with open('README.md', 'w') as f:
                f.write(f"# {repo_name}\n\n{description}\n")

            # Add all files to staging
            subprocess.run(['git', 'add', '.'], check=True)

            # Commit the files
            subprocess.run(['git', 'commit', '-m', 'Initial commit with folder structure'], check=True)

            # Rename branch to 'main'
            subprocess.run(['git', 'branch', '-M', 'main'], check=True)

            # Add the remote repository
            subprocess.run(['git', 'remote', 'add', 'origin', repo.clone_url], check=True)

            # Push the commit to GitHub
            subprocess.run(['git', 'push', '-u', 'origin', 'main'], check=True)

            print("Local project with folder structure initialized and pushed to GitHub successfully.")

        except subprocess.CalledProcessError as e:
            print(f"An error occurred during subprocess execution: {e}")
        finally:
            # Change back to the original directory
            os.chdir(original_cwd)

        return repo
