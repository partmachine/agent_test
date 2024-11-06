# Ensure that the environment variable 'GITHUB_TOKEN' is set with your GitHub Personal Access Token
import os

from GitHub import GitHubClient

# Retrieve the token from environment variables
token = os.getenv('GITHUB_TOKEN')

# Check if the token is retrieved successfully
if token is None:
    raise ValueError("GITHUB_TOKEN environment variable is not set.")

# Instantiate the GitHub class
github_project_creator = GitHubClient(token)

# Repository details
repo_name = 'MyCSharpProject'
description = 'This is a sample C# project with a structured folder layout.'
private_repo = False
sdk_version = "9.0.100-rc.2.24474.11"  # Specify the desired .NET SDK version

# Specify the base directory
base_dir = 'D:/development/repos'  # Replace with your desired base directory path

# Create the repository and initialize the project under the base directory
github_project_creator.create_repository(
    repo_name, 
    description, 
    private_repo, 
    base_directory=base_dir,
    sdk_version=sdk_version
)

# Delete the repository and optionally remove the local directory
# Ensure the base directory path uses the correct path separator
github_project_creator.delete_repository(repo_name)

