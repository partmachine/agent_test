import base64
import hashlib
import json
import uuid
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import os
from azure.devops.v7_1.core.models import TeamProject
import time
import subprocess
import shutil
from azure.devops.v7_1.work_item_tracking.models import JsonPatchOperation
import requests
from azure.devops.v7_1.graph.models import GraphSubjectLookup, GraphUser, GraphMembership
from azure.devops.v7_1.member_entitlement_management import MemberEntitlementManagementClient


class AzureDevOpsClient:

    class WorkItemDetails:
        def __init__(self, title, description, work_item_type, state, assigned_to,
                     area_path='', team_project='', iteration_path='', reason='',
                     comment_count=0, changed_date='', created_date='', board_column='',
                     board_column_done=False, state_change_date='', priority=0,
                     value_area='', kanban_column='', kanban_column_done=False,
                     created_by='', changed_by='', id=None, url=None, comments=None):
            self.id = id
            self.url = url
            self.title = title
            self.description = description
            self.work_item_type = work_item_type
            self.state = state
            self.assigned_to = assigned_to
            self.area_path = area_path
            self.team_project = team_project
            self.iteration_path = iteration_path
            self.reason = reason
            self.comment_count = comment_count
            self.changed_date = changed_date
            self.created_date = created_date
            self.board_column = board_column
            self.board_column_done = board_column_done
            self.state_change_date = state_change_date
            self.priority = priority
            self.value_area = value_area
            self.kanban_column = kanban_column
            self.kanban_column_done = kanban_column_done
            self.created_by = created_by
            self.changed_by = changed_by
            self.comments = comments or []

        def to_dict(self):
            return {
                "id": self.id,
                "url": self.url,
                "title": self.title,
                "description": self.description,
                "work_item_type": self.work_item_type,
                "state": self.state,
                "assigned_to": self.assigned_to,
                "area_path": self.area_path,
                "team_project": self.team_project,
                "iteration_path": self.iteration_path,
                "reason": self.reason,
                "comment_count": self.comment_count,
                "changed_date": self.changed_date,
                "created_date": self.created_date,
                "board_column": self.board_column,
                "board_column_done": self.board_column_done,
                "state_change_date": self.state_change_date,
                "priority": self.priority,
                "value_area": self.value_area,
                "kanban_column": self.kanban_column,
                "kanban_column_done": self.kanban_column_done,
                "created_by": self.created_by,
                "changed_by": self.changed_by,
                "comments": self.comments
            }
        
    def __init__(self, organization, personal_access_token):
        """
        Initialize Azure DevOps client
        Args:
            organization_url (str): The URL of your Azure DevOps organization
            personal_access_token (str): Azure DevOps Personal Access Token
        """
        self.organization = organization
        self.organization_url = f"https://dev.azure.com/{self.organization}"
        self.vssps_url = f"https://vssps.dev.azure.com/{self.organization}"
        self.vsaex_url = f"https://vsaex.dev.azure.com/{self.organization}"
        self.credentials = BasicAuthentication('', personal_access_token)
        self.connection = Connection(base_url=self.organization_url, creds=self.credentials)
        
        # Get clients
        self.graph_client = self.connection.clients.get_graph_client()
        self.git_client = self.connection.clients.get_git_client()
        self.core_client = self.connection.clients.get_core_client()
        self.build_client = self.connection.clients.get_build_client()

        self.project_name = None
        self.team_name = None
        self.repo_name = None
        self.local_repo_path = None
    
    def create_project(self, project_name, description="", visibility="private"):
        """
        Create a new project in Azure DevOps
        Args:
            project_name (str): Name of the project
            description (str): Project description
            visibility (str): private or public
        Returns:
            object: Created project object
        """
        self.get_process_templates()
        capabilities = {
            "versioncontrol": {"sourceControlType": "Git"},
            "processTemplate": {"templateTypeId": "adcc42ab-9882-485e-a3ed-7678f01f66bc"}  # Agile process
        }
        self.project_name = project_name    
        self.team_name = project_name + ' Team'
        self.repo_name = project_name  
        
        project = TeamProject(
            name=self.project_name,
            description=description,
            visibility=visibility,
            capabilities=capabilities
        )
        
        try:
            operation_reference = self.core_client.queue_create_project(project)
            print(f"Project '{self.project_name}' creation initiated.")
            
            # Wait for project creation to complete by checking if the project exists
            while True:
                projects = self.core_client.get_projects()
                if any(p.name == self.project_name for p in projects):
                    print(f"Project '{self.project_name}' created successfully.")
                    break
                time.sleep(5)  # Wait for a few seconds before checking again
            
            repo = self.git_client.get_repository(project=self.project_name, repository_id=self.project_name)
            if repo:
                self.repo_name = repo.name
            
            self.team_name = self.project_name + ' Team'

            return operation_reference
        except Exception as e:
            print(f"Error creating project: {str(e)}")
            return None
   
    def get_process_templates(self):
    # Construct the URL for the WIQL query with a stable API version
        url = f"{self.organization_url}/_apis/process/processes?api-version=7.1"   

            # Define the headers for the request
        headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list users
        response = requests.get(url, headers=headers)

        return None


    def delete_project(self, project_name, base_directory):
        """
        Delete a project from Azure DevOps and all its repositories
        Args:
            project_name (str): Name of the project to delete
            base_directory (str): Local directory where repositories are cloned
        """
        try:
            # Retrieve the project to ensure we have the correct project ID
            project = next((p for p in self.core_client.get_projects() if p.name == project_name), None)
            if not project:
                print(f"Project '{project_name}' does not exist.")
                return

            # Retrieve all repositories in the project
            repos = self.git_client.get_repositories(project=project.id)
            for repo in repos:
                # Delete each repository and its local clone
                self.delete_repository(project_name, repo.name, base_directory)

            # Queue the project deletion using the project ID
            self.core_client.queue_delete_project(project.id)
            print(f"Project '{project_name}' and all its repositories deleted successfully.")
        except Exception as e:
            print(f"Error deleting project: {str(e)}")

    def create_repository(self, project_name, repo_name=None):
        """
        Create a new Git repository in an Azure DevOps project and clone it to a local directory
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            base_directory (str): Local directory to clone the repository into
        Returns:
            object: Created repository object
        """
        try:
            # Retrieve the project to ensure we have the correct project ID
            project = next((p for p in self.core_client.get_projects() if p.name == project_name), None)
            if not project:
                print(f"Project '{project_name}' does not exist.")
                return None

            # Use the project ID for the repository creation
            repo = self.git_client.create_repository(
                git_repository_to_create={
                    "name": repo_name,
                    "project": {
                        "id": project.id  # Use project ID instead of name
                    }
                },
                project=project.id  # Use project ID here as well
            )
            if repo:
                self.repo_name = repo.name
                print(f"Repository '{self.repo_name}' created successfully in project '{project_name}'")
            

            return repo
        except Exception as e:
            print(f"Error creating repository: {str(e)}")
            return None
    
    def add_user_to_team(self, user_email, additional_groups=[]):
        """
        Invite a user to the Azure DevOps organization using the REST API
        Args:
            user_email (str): Email of the user to invite
            additional_groups (list): List of additional group names to add the user to
        Returns:
            dict: Response from the API if the invitation is successful, None otherwise
        """
        try:
            team_descriptor = self.get_team_descriptor(self.project_name, self.team_name)
            if not team_descriptor:
                print(f"Error: Team descriptor for '{self.team_name}' not found.")
                return None

            group_descriptors = [team_descriptor]
            for group in additional_groups:
                group_json = json.loads(self.get_group(group))
                if group_json:
                    group_descriptors.append(group_json['descriptor'])
                else:
                    print(f"Warning: Group '{group}' not found. Skipping.")

            url = f"{self.vssps_url}/_apis/graph/users?api-version=7.1-preview.1"

            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            payload = {
                "principalName": user_email
            }

            response = requests.post(url, headers=headers, json=payload, params={'groupDescriptors': ','.join(group_descriptors)})

            response.raise_for_status()  # Raise an error for bad responses

            print(f"User '{user_email}' added to Team: '{self.team_name}' successfully.")
            return response.json()

        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            print(f"Request error occurred: {req_err}")
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
        return None
       
    def remove_user_from_team(self, user_email):
        """
        Delete a user from the Azure DevOps organization using the REST API
        Args:
            user_email (str): Email of the user to invite
        Returns:
            dict: Response from the API if the removal is successful, None otherwise
        """
        try:
            user_json = self.find_user(user_email)
            if not user_json:
                print(f"Error: User '{user_email}' not found.")
                return None

            # Parse the JSON string into a dictionary
            user_info = json.loads(user_json)

            user_descriptor = user_info.get('descriptor')
            if not user_descriptor:
                print(f"Error: User descriptor for '{user_email}' not found.")
                return None

            url = f"{self.vssps_url}/_apis/graph/users/{user_descriptor}?api-version=7.2-preview.1"

            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            response = requests.delete(url, headers=headers)

            response.raise_for_status()  # Raise an error for bad responses

            print(f"User '{user_email}' removed from Team '{self.team_name}' successfully.")
            return None

        except json.JSONDecodeError as json_err:
            print(f"JSON decode error: {json_err}")
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            print(f"Request error occurred: {req_err}")
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
        return None

    def create_pipeline(self, project_name, repository_name, pipeline_name, yaml_path):
        """
        Create a new pipeline in Azure DevOps
        Args:
            project_name (str): Name of the project
            repository_name (str): Name of the repository
            pipeline_name (str): Name of the pipeline
            yaml_path (str): Path to the YAML pipeline definition file
        Returns:
            object: Created pipeline object
        """
        from azure.devops.v7_1.build.models import BuildDefinition, BuildRepository
        
        try:
            # Create repository reference
            repository = BuildRepository(
                name=repository_name,
                type="Git",
                url=f"{self.organization_url}/{project_name}/_git/{repository_name}"
            )
            
            # Create pipeline definition
            pipeline_definition = BuildDefinition(
                name=pipeline_name,
                repository=repository,
                process={
                    "type": 2,  # YAML
                    "yamlFilename": yaml_path
                }
            )
            
            # Create the pipeline
            created_pipeline = self.build_client.create_definition(
                definition=pipeline_definition,
                project=project_name
            )
            
            print(f"Pipeline '{pipeline_name}' created successfully")
            return created_pipeline
            
        except Exception as e:
            print(f"Error creating pipeline: {str(e)}")
            return None


    def add_readme_to_repo(self, project_name, repo_name=None, content="# Project Title\n\nA brief description of the project."):
        """
        Add a README.md file to the root of a repository in Azure DevOps
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            content (str): Content of the README.md file
        """
        try:
            # Retrieve the repository to ensure we have the correct repository ID
            if not repo_name:
                repo_name = self.repo_name
                
            repo = self.git_client.get_repository(project=project_name, repository_id=repo_name)
            if not repo:
                print(f"Repository '{repo_name}' does not exist in project '{project_name}'.")
                return None

            # Check if the branch exists
            branch_name = "main"
            refs = self.git_client.get_refs(repository_id=repo.id, project=project_name)
            branch_ref = next((ref for ref in refs if ref.name == f"refs/heads/{branch_name}"), None)

            if not branch_ref:
                # If the branch doesn't exist, create it with an initial commit
                initial_commit = {
                    "refUpdates": [{"name": f"refs/heads/{branch_name}", "oldObjectId": "0000000000000000000000000000000000000000"}],
                    "commits": [{
                        "comment": "Initial commit",
                        "changes": [{
                            "changeType": "add",
                            "item": {"path": "/README.md"},
                            "newContent": {
                                "content": content,
                                "contentType": "rawtext"
                            }
                        }]
                    }]
                }
                response = self.git_client.create_push(push=initial_commit, repository_id=repo.id, project=project_name)
                print(f"Branch '{branch_name}' created with README.md in repository '{repo_name}'.")
                print(f"Commit details: {[commit.commit_id for commit in response.commits]}")
            else:
                # If the branch exists, add the README.md file
                push = {
                    "refUpdates": [{"name": f"refs/heads/{branch_name}", "oldObjectId": branch_ref.object_id}],
                    "commits": [{
                        "comment": "Add README.md",
                        "changes": [{
                            "changeType": "add",
                            "item": {"path": "/README.md"},
                            "newContent": {
                                "content": content,
                                "contentType": "rawtext"
                            }
                        }]
                    }]
                }
                try:
                    self.git_client.create_push(push, repository_id=repo.id, project=project_name)
                    print('README.md file added successfully.')
                except Exception as e:
                    print(f"Error adding README.md: {e}")
        except Exception as e:
            print(f"Error adding README.md to repository: {str(e)}")

    def add_default_folders_to_repo(self, project_name, folders=['src', 'test', 'assets', 'docs', 'lib', 'build', 'deploy'], repo_name=None):
        """
        Add specified folders with a descriptive README.md file to the root of a repository in Azure DevOps
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            folders (list): List of folder names to add
        """
        try:
            # Retrieve the repository to ensure we have the correct repository ID
            if repo_name == None:
                repo_name = self.repo_name
            repo = self.git_client.get_repository(project=project_name, repository_id=repo_name)
            if not repo:
                print(f"Repository '{repo_name}' does not exist in project '{project_name}'.")
                return None

            # Check if the branch exists
            branch_name = "main"
            refs = self.git_client.get_refs(repository_id=repo.id, project=project_name)
            branch_ref = next((ref for ref in refs if ref.name == f"refs/heads/{branch_name}"), None)

            if not branch_ref:
                print(f"Branch '{branch_name}' does not exist in repository '{repo_name}'.")
                return None

            # Define descriptive content for each folder
            folder_descriptions = {
                "src": "# Source Code\n\nThis folder contains the main source code for the project.",
                "test": "# Tests\n\nThis folder contains test cases and testing scripts.",
                "assets": "# Assets\n\nThis folder contains images, videos, and other media assets.",
                "docs": "# Documentation\n\nThis folder contains project documentation and guides.",
                "lib": "# Libraries\n\nThis folder contains external libraries and dependencies.",
                "build": "# Build\n\nThis folder contains the build scripts and configuration.",
                "deploy": "# Deploy\n\nThis folder contains the deployment scripts and configuration."
            }

            # Create a commit to add the folders with README.md files
            changes = [{
                "changeType": "add",
                "item": {"path": f"/{folder}/README.md"},
                "newContent": {
                    "content": folder_descriptions.get(folder, f"# {folder.capitalize()}\n\nThis folder contains the {folder} files."),
                    "contentType": "rawtext"
                }
            } for folder in folders]

            push = {
                "refUpdates": [{"name": f"refs/heads/{branch_name}", "oldObjectId": branch_ref.object_id}],
                "commits": [{
                    "comment": "Add folders with descriptive README.md",
                    "changes": changes
                }]
            }

            try:
                self.git_client.create_push(push, repository_id=repo.id, project=project_name)
                print(f"Folders {folders} with descriptive README.md added successfully to repository '{repo_name}'.")
            except Exception as e:
                print(f"Error adding folders: {e}")
        except Exception as e:
            print(f"Error adding folders to repository: {str(e)}")

    def clone_repository_locally(self, base_directory, repo_name = None):
        """
        Clone a repository from Azure DevOps to a local directory
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            base_directory (str): Local directory to clone the repository into
        """
        try:
            if not repo_name:
                repo_name = self.repo_name             
            hash_object = hashlib.sha256(self.credentials.password.encode())
            short_hash = hash_object.hexdigest()[:16]
            # Construct the repository URL
            repo_url = f"{self.organization_url}/{self.project_name}/_git/{self.repo_name}"
            # Normalize the base directory path            
            clone_directory = os.path.normpath(os.path.join(base_directory, short_hash, self.repo_name))
            
            self.local_repo_path = clone_directory

            # Run the git clone command
            subprocess.run(['git', 'clone', repo_url, clone_directory], check=True)
            print(f"Repository cloned successfully to {clone_directory}")
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e}")

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

    def delete_repository(self, project_name, repo_name, base_directory):
        """
        Delete a repository from Azure DevOps and remove the local clone
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            base_directory (str): Local directory where the repository is cloned
        """
        try:
            # Retrieve the repository to ensure we have the correct repository ID
            repo = self.git_client.get_repository(project=project_name, repository_id=repo_name)
            if not repo:
                print(f"Repository '{repo_name}' does not exist in project '{project_name}'.")
                return

            # Delete the repository from Azure DevOps
            # self.git_client.delete_repository(repository_id=repo.id, project=project_name)
            # print(f"Repository '{repo_name}' deleted from project '{project_name}'.")

            # Construct the local clone directory path
            clone_directory = os.path.normpath(os.path.join(base_directory, repo_name))

            # Use force_delete_directory to remove the local clone directory
            if os.path.exists(clone_directory):
                if self.force_delete_directory(clone_directory):
                    print(f"Local clone of repository '{repo_name}' deleted from '{clone_directory}'.")
                else:
                    print(f"Failed to delete local clone of repository '{repo_name}' from '{clone_directory}'.")
            else:
                print(f"No local clone found for repository '{repo_name}' at '{clone_directory}'.")

        except Exception as e:
            print(f"Error deleting repository: {str(e)}")

    def create_backlog_item(self, title, description, item_type="Product Backlog Item", parent_id=None):
        """
        Create a new backlog item in Azure DevOps
        Args:
            title (str): Title of the backlog item
            description (str): Description of the backlog item
            item_type (str): Type of the backlog item (e.g., "Product Backlog Item", "Bug")
            parent_id (int, optional): ID of the parent work item to link to
        Returns:
            int: ID of the created work item or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the fields for the new work item
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.Title",
                    value=title
                ),
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.Description",
                    value=description
                )
            ]

            # If a parent ID is provided, add a link to the parent item
            if parent_id is not None:
                document.append(
                    JsonPatchOperation(
                        op="add",
                        path="/relations/-",
                        value={
                            "rel": "System.LinkTypes.Hierarchy-Reverse",
                            "url": f"{self.organization_url}/_apis/wit/workItems/{parent_id}",
                            "attributes": {
                                "comment": "Linking to parent work item"
                            }
                        }
                    )
                )

            # Create the work item
            work_item = work_item_tracking_client.create_work_item(
                document=document,
                project=self.project_name,
                type=item_type
            )

            # Get the item ID
            item_id = work_item.id
            print(f"Backlog item '{title}' created successfully with ID: {item_id}.")
            return item_id

        except Exception as e:
            print(f"Error creating backlog item: {str(e)}")
            return None

    def add_work_item_comment(self, work_item_id, comment_text):
        """
        Add a comment to an existing work item in Azure DevOps
        Args:
            work_item_id (int): ID of the work item
            comment_text (str): Text of the comment to add
        Returns:
            object: Created comment object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create the comment
            comment = work_item_tracking_client.add_comment(
                project=self.project_name,
                work_item_id=work_item_id,
                request={
                    "text": comment_text
                }
            )

            print(f"Comment added successfully to work item {work_item_id}")
            return comment

        except Exception as e:
            print(f"Error adding comment to work item: {str(e)}")
            return None

    def assign_backlog_item(self, work_item_id, user_email):
        """
        Assign a backlog item to a specific user in Azure DevOps
        Args:
            work_item_id (int): ID of the work item
            user_email (str): Email of the user to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the update operation for assigning the work item
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AssignedTo",
                    value=user_email
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Backlog item {work_item_id} assigned to {user_email} successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning backlog item: {str(e)}")
            return None

    def get_backlog_item_ids(self, item_type="Product Backlog Item"):
        """
        Get a list of backlog item IDs from a project in Azure DevOps using the REST API
        Args:
            project_name (str): Name of the project
            item_type (str): Type of the backlog item (e.g., "Product Backlog Item", "Bug")
        Returns:
            list: List of work item IDs
        """
        try:
            # Define the WIQL query to get backlog item IDs
            wiql_query = {
                "query": f"""
                SELECT [System.Id]
                FROM WorkItems
                WHERE [System.TeamProject] = '{self.project_name}'
                AND [System.WorkItemType] = '{item_type}'
                ORDER BY [System.Id]
                """
            }

            # Construct the URL for the WIQL query with a stable API version
            url = f"{self.organization_url}/_apis/wit/wiql?api-version=6.0"

            # Make the HTTP request to the Azure DevOps REST API
            response = requests.post(
                url,
                json=wiql_query,
                auth=('', self.credentials.password)
            )

            # Check if the request was successful
            response.raise_for_status()

            # Extract work item IDs from the response
            work_item_ids = [item['id'] for item in response.json().get('workItems', [])]
            print(f"Retrieved {len(work_item_ids)} backlog item IDs from project '{self.project_name}'.")
            return work_item_ids

        except requests.exceptions.RequestException as e:
            print(f"Error retrieving backlog item IDs: {str(e)}")
            return []

    def get_backlog_items(self, item_types=["Product Backlog Item", "Epic","Feature", "Use story", "Task"]):
        """
        Get a list of backlog items from a project in Azure DevOps
        Args:
            project_name (str): Name of the project
            item_type (str): Type of the backlog item (e.g., "Product Backlog Item", "Bug")
        Returns:
            list: List of WorkItemDetails objects
        """
        try:
            # Initialize an empty list to store all work item IDs
            work_item_ids = []

            # Iterate over each item type and get the work item IDs
            for item_type in item_types:
                work_item_ids.extend(self.get_backlog_item_ids(item_type))

            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Retrieve the work items using the IDs
            if work_item_ids:
                work_items = work_item_tracking_client.get_work_items(ids=work_item_ids)
                work_item_details_list = []

                for item in work_items:
                    fields = item.fields
                    work_item_details = self.WorkItemDetails(
                        id=item.id,
                        url=item.url,
                        title=fields.get('System.Title', ''),
                        description=fields.get('System.Description', ''),
                        work_item_type=fields.get('System.WorkItemType', ''),
                        state=fields.get('System.State', ''),
                        assigned_to=fields.get('System.AssignedTo', {}).get('uniqueName', ''),
                        area_path=fields.get('System.AreaPath', ''),
                        team_project=fields.get('System.TeamProject', ''),
                        iteration_path=fields.get('System.IterationPath', ''),
                        reason=fields.get('System.Reason', ''),
                        comment_count=fields.get('System.CommentCount', 0),
                        changed_date=fields.get('System.ChangedDate', ''),
                        created_date=fields.get('System.CreatedDate', ''),
                        board_column=fields.get('System.BoardColumn', ''),
                        board_column_done=fields.get('System.BoardColumnDone', False),
                        state_change_date=fields.get('Microsoft.VSTS.Common.StateChangeDate', ''),
                        priority=fields.get('Microsoft.VSTS.Common.Priority', 0),
                        value_area=fields.get('Microsoft.VSTS.Common.ValueArea', ''),
                        kanban_column=fields.get('WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column', ''),
                        kanban_column_done=fields.get('WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column.Done', False),
                        created_by=fields.get('System.CreatedBy', {}).get('uniqueName', ''),
                        changed_by=fields.get('System.ChangedBy', {}).get('uniqueName', ''),
                        comments=[]  # Assuming comments are not fetched here
                    )
                    work_item_details_list.append(work_item_details)

                    print(f"Retrieved {len(work_item_details_list)} backlog items from project '{self.project_name}'.")
                    work_items_dict = [item.to_dict() for item in work_item_details_list]

                    # Convert the list of dictionaries to a JSON string
                    work_items_json = json.dumps(work_items_dict, indent=4)
                
                    return work_items_json
            else:
                print(f"No backlog items found in project '{self.project_name}'.")
                return []

        except Exception as e:
            print(f"Error retrieving backlog items: {str(e)}")
            return []

    def list_active_directory_users(self):
        """
        List users from the Active Directory in Azure DevOps
        Returns:
            list: List of user objects
        """
        try:
            # Initialize the Graph client
            graph_client = self.connection.clients.get_graph_client()

            # Get all users
            paged_users = graph_client.list_users()

            # Access the 'value' attribute to get the list of users
            users = paged_users.graph_users

            # Print and return the list of users
            user_list = []
            for user in users:
                print(f"User: {user.principal_name}, Display Name: {user.display_name}")
                user_list.append(user)

            return user_list

        except Exception as e:
            print(f"Error listing Active Directory users: {str(e)}")
            return []

    def get_project_by_name(self, project_name):
        """
        Retrieve a project by its name in Azure DevOps and set the repository name
        Args:
            project_name (str): Name of the project to retrieve
        Returns:
            object: Project object if found, None otherwise
        """
        try:
            # Retrieve all projects
            projects = self.core_client.get_projects()

            # Find the project with the specified name
            project = next((p for p in projects if p.name == project_name), None)

            if project:
                print(f"Project '{project_name}' found.")
                
                self.project_name = project.name
                # Retrieve repositories in the project
                repos = self.git_client.get_repositories(project=project.id)

                # Set the first repository name found, if any
                if repos:
                    self.repo_name = repos[0].name
                    print(f"Repository '{self.repo_name}' found in project '{project_name}'.")
                else:
                    print(f"No repositories found in project '{project_name}'.")

                self.team_name = self.project_name + ' Team'

                return project
            else:
                print(f"Project '{project_name}' not found.")
                return None

        except Exception as e:
            print(f"Error retrieving project '{project_name}': {str(e)}")
            return None


    def find_user(self, user_name_or_email, subject_types='aad'):
        """
        Find a user in the Azure DevOps organization using the REST API
        Args:
            user_email (str): Email of the user to find
            subject_types (str): Type of subjects to search for (default is 'aad')
        Returns:
            dict: User object if found, None otherwise
        """
        try:
            # Define the URL for the users API
            url = f"{self.vssps_url}/_apis/graph/users?subjectTypes={subject_types}&api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list users
            response = requests.get(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract the list of users
            users = response.json().get('value', [])

            user_name = user_name_or_email.lower()
            # Filter the user based on email matching principalName, mailAddress, or displayName
            for user in users:
                if (user_name == user.get('principalName', '').lower() or
                    user_name == user.get('mailAddress', '').lower() or
                    user_name == user.get('displayName', '').lower()):
                    
                    if user:
                        # Convert the user object to a dictionary
                        user_dict = {
                            "display_name": user['displayName'],        
                            "principal_name": user['principalName'],
                            "descriptor": user['descriptor'],
                            "url": user['url']
                        }
                        # Convert the dictionary to a JSON string
                        user_json = json.dumps(user_dict, indent=4)
                        return user_json

            print(f"No user found with email '{user_name}'.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error finding user '{user_name}': {str(e)}")
            return None

    def list_users_via_rest_api(self):
        """
        List users in the Azure DevOps organization using the REST API
        Returns:
            list: List of user objects or None if failed
        """
        try:
            # Define the URL for the users API
            url = f"{self.vssps_url}/_apis/graph/users?api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list users
            response = requests.get(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract and return the list of users
            users = response.json().get('value', [])
            for user in users:
                print(f"User: {user.get('principalName')}, Display Name: {user.get('displayName')}")
            
            return users

        except requests.exceptions.RequestException as e:
            print(f"Error listing users: {str(e)}")
            return None

    def delete_user_via_rest_api(self, user_descriptor):
        """
        Delete a user from the Azure DevOps organization using the REST API
        Args:
            user_descriptor (str): The descriptor of the user to delete
        Returns:
            bool: True if the user was deleted successfully, False otherwise
        """
        try:
            # Define the URL for the user deletion API
            url = f"{self.vssps_url}/_apis/graph/users/{user_descriptor}?api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the DELETE request to remove the user
            response = requests.delete(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            print(f"User with descriptor '{user_descriptor}' deleted successfully.")
            return True

        except requests.exceptions.RequestException as e:
            print(f"Error deleting user with descriptor '{user_descriptor}': {str(e)}")
            return False

    

    def list_user_teams(self, user_email):
        """
        List the teams a user belongs to in Azure DevOps using the REST API
        Args:
            user_email (str): Email of the user
        Returns:
            list: List of team objects or None if failed
        """
        try:
            user_json = self.find_user(user_email)
            if not user_json:
                print(f"Error: User '{user_email}' not found.")
                return None

            # Parse the JSON string into a dictionary
            user_info = json.loads(user_json)
            user_descriptor = user_info.get('descriptor')
            if not user_descriptor:
                print(f"Error: User descriptor for '{user_email}' not found.")
                return None
            core_client = self.connection.clients.get_core_client()
            all_teams = core_client.get_all_teams()

            user_teams = []
            graph_client = self.connection.clients.get_graph_client()
            for team in all_teams:
                team_members = graph_client.list_memberships(user_descriptor)
                if any(member.member_descriptor == user_descriptor for member in team_members):
                    user_teams.append(team)
            seen_ids = set()
            distinct_teams = []

            for team in all_teams:
                if team.name not in seen_ids:
                    distinct_teams.append(team)
                    seen_ids.add(team.name)
            return distinct_teams           

        except requests.exceptions.RequestException as e:
            print(f"Error listing teams for user '{user_email}': {str(e)}")
            return None

    def get_group_by_descriptor(self, descriptor):
        """
        Get the group details using the descriptor
        Args:
            descriptor (str): The descriptor of the group
        Returns:
            str: JSON string of the group details if found, None otherwise
        """
        try:
            # Define the URL for the group descriptor API
            url = f"{self.vssps_url}/_apis/graph/descriptors/{descriptor}?api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to get the group details
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            # Extract the group details
            group = response.json()

            # Convert the group object to a dictionary
            group_dict = {
                "display_name": group.get('displayName', ''),
                "principal_name": group.get('principalName', ''),
                "descriptor": group.get('descriptor', ''),
                "url": group.get('url', '')
            }
            # Convert the dictionary to a JSON string
            group_json = json.dumps(group_dict, indent=4)
            return group_json

        except requests.exceptions.RequestException as e:
            print(f"Error getting group by descriptor '{descriptor}': {str(e)}")
            return None

    def find_group_by_display_name(self, display_name, subject_types='vssgp'):
        """
        Find a group in the Azure DevOps organization using the REST API
        Args:
            display_name (str): Display name of the group to find
            subject_types (str): Type of subjects to search for (default is 'vssgp' for groups)
        Returns:
            str: JSON string of the group details if found, None otherwise
        """
        try:
            # Define the URL for the groups API
            url = f"{self.vssps_url}/_apis/graph/groups?subjectTypes={subject_types}&api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list groups
            response = requests.get(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract the list of groups
            groups = response.json().get('value', [])

            # Filter the group based on displayName
            for group in groups:
                if display_name.lower() == group.get('displayName', '').lower():
                    # Convert the group object to a dictionary
                    group_dict = {
                        "display_name": group.get('displayName', ''),
                        "principal_name": group.get('principalName', ''),
                        "descriptor": group.get('descriptor', ''),
                        "url": group.get('url', '')
                    }
                    # Convert the dictionary to a JSON string
                    group_json = json.dumps(group_dict, indent=4)
                    return group_json

            print(f"No group found with display name '{display_name}'.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error finding group '{display_name}': {str(e)}")
            return None

        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
            return None

    
    def search_user_entitlements_by_email(self, user_email):
        """
        Search for a user in the Azure DevOps organization by email using the REST API
        Args:
            user_email (str): Email of the user to search for
        Returns:
            dict: User object if found, None otherwise
        """
        try:
            # Define the URL for the user entitlements API
            url = f"{self.vssps_url}/_apis/userentitlements?api-version=7.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Define the filter query to search by email
            filter_query = f"name eq '{user_email}'"

            # Send the GET request to search user entitlements
            response = requests.get(url, headers=headers, params={'$filter': filter_query})

            # Check if the request was successful
            response.raise_for_status()

            # Extract the list of user entitlements
            items = response.json().get('items', [])

            return items[0]['id']
        

        except requests.exceptions.RequestException as e:
            print(f"Error searching for user by email '{user_email}': {str(e)}")
            return None

    def get_team_descriptor(self, project_name, team_name):
        """
        Get the team descriptor for a team using the REST API
        Args:
            organization (str): The name of the Azure DevOps organization
            storage_key (str): The storage key of the team
        Returns:
            str: Team descriptor if found, None otherwise
        """
        try:
            #team = self.core_client.get_team(project_id=project_name, team_id=team_name)

            #storage_key = team.id

            # Define the URL for the descriptors API
            url1 = f"https://dev.azure.com/LeeNey/_apis/projects/{project_name}/teams/{self.team_name}?api-version=7.1-preview.3"


            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to get the team descriptor
            response = requests.get(url1, headers=headers)

            team_id = response.json().get('id', None)

            url2 = f"https://vssps.dev.azure.com/LeeNey/_apis/graph/descriptors/{team_id}?api-version=7.1"

            response = requests.get(url2, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            descriptor = response.json().get('value', None)

            return descriptor

        except requests.exceptions.RequestException as e:
            print(f"Error getting team descriptor for team '{team_name}': {str(e)}")
            return None

    def get_group(self, group_name):
        """
        Get the team descriptor for a team using the REST API
        Args:
            group_name (str): The name of the group
        Returns:
            str: JSON string of the group details if found, None otherwise
        """
        try:
            groups = self.graph_client.list_groups()

            for group in groups.graph_groups:
                if group.display_name == group_name:
                    # Convert the group object to a dictionary
                    group_dict = {
                        "display_name": group.display_name,
                        "principal_name": group.principal_name,
                        "descriptor": group.descriptor,
                        "url": group.url
                    }
                    # Convert the dictionary to a JSON string
                    group_json = json.dumps(group_dict, indent=4)
                    return group_json

            print(f"Group '{group_name}' not found.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error getting group '{group_name}': {str(e)}")
            return None


    def get_work_items_assigned_to_user(self, user_email):
        """
        Get all work items assigned to a particular user in Azure DevOps using the REST API
        Args:
            user_email (str): Email of the user
        Returns:
            list: List of WorkItemDetails objects or None if failed
        """
        try:
            # Define the WIQL query to find work items assigned to the user
            wiql_query = {
                "query": f"""
                SELECT [System.Id], [System.AreaPath], [System.TeamProject], [System.IterationPath],
                       [System.WorkItemType], [System.State], [System.Reason]
                FROM WorkItems
                WHERE [System.AssignedTo] = '{user_email}'
                AND [System.TeamProject] = '{self.project_name}'
                ORDER BY [System.ChangedDate] DESC
                """
            }

            # Construct the URL for the WIQL query
            url = f"{self.organization_url}/{self.project_name}/_apis/wit/wiql?api-version=6.0"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Make the HTTP request to the Azure DevOps REST API
            response = requests.post(url, json=wiql_query, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract work item IDs from the response
            work_item_ids = [item['id'] for item in response.json().get('workItems', [])]

            # Retrieve the work items using the IDs
            if work_item_ids:
                # Construct the URL to get work item details
                ids_str = ','.join(map(str, work_item_ids))
                work_items_url = f"{self.organization_url}/_apis/wit/workitems?ids={ids_str}&fields=System.AreaPath,System.TeamProject,System.IterationPath,System.WorkItemType,System.State,System.Reason,System.CommentCount,System.ChangedDate,System.CreatedDate,System.Title,System.BoardColumn,System.BoardColumnDone,Microsoft.VSTS.Common.StateChangeDate,Microsoft.VSTS.Common.Priority,Microsoft.VSTS.Common.ValueArea,WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column,WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column.Done,System.Description,System.AssignedTo,System.CreatedBy,System.ChangedBy&api-version=6.0"

                # Make the HTTP request to get work item details
                work_items_response = requests.get(work_items_url, headers=headers)
                work_items_response.raise_for_status()

                work_items_data = work_items_response.json().get('value', [])
                work_items = []

                for item in work_items_data:
                    # Fetch comments for each work item
                    comments_url = f"{self.organization_url}/{self.project_name}/_apis/wit/workItems/{item.get('id')}/comments?api-version=7.2-preview.4"
                    comments_response = requests.get(comments_url, headers=headers)
                    comments_response.raise_for_status()
                    comments_data = comments_response.json().get('comments', [])

                    # Extract comment details
                    comments = [
                        {
                            "id": comment.get('id'),
                            "text": comment.get('text'),
                            "created_by": comment.get('createdBy', {}).get('uniqueName', '')
                        }
                        for comment in comments_data
                    ]

                    work_item = self.WorkItemDetails(
                        id=item.get('id'),
                        url=item.get('url'),
                        title=item['fields'].get('System.Title', ''),
                        description=item['fields'].get('System.Description', ''),
                        work_item_type=item['fields'].get('System.WorkItemType', ''),
                        state=item['fields'].get('System.State', ''),
                        assigned_to=item['fields'].get('System.AssignedTo', {}).get('uniqueName', ''),
                        area_path=item['fields'].get('System.AreaPath', ''),
                        team_project=item['fields'].get('System.TeamProject', ''),
                        iteration_path=item['fields'].get('System.IterationPath', ''),
                        reason=item['fields'].get('System.Reason', ''),
                        comment_count=item['fields'].get('System.CommentCount', 0),
                        changed_date=item['fields'].get('System.ChangedDate', ''),
                        created_date=item['fields'].get('System.CreatedDate', ''),
                        board_column=item['fields'].get('System.BoardColumn', ''),
                        board_column_done=item['fields'].get('System.BoardColumnDone', False),
                        state_change_date=item['fields'].get('Microsoft.VSTS.Common.StateChangeDate', ''),
                        priority=item['fields'].get('Microsoft.VSTS.Common.Priority', 0),
                        value_area=item['fields'].get('Microsoft.VSTS.Common.ValueArea', ''),
                        kanban_column=item['fields'].get('WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column', ''),
                        kanban_column_done=item['fields'].get('WEF_C0095A5713844C44BD92373DCB0B692E_Kanban.Column.Done', False),
                        created_by=item['fields'].get('System.CreatedBy', {}).get('uniqueName', ''),
                        changed_by=item['fields'].get('System.ChangedBy', {}).get('uniqueName', ''),
                        comments=comments
                    )
                    work_items.append(work_item)

                print(f"Retrieved {len(work_items)} work items assigned to '{user_email}'.")
                work_items_dict = [item.to_dict() for item in work_items]

                # Convert the list of dictionaries to a JSON string
                work_items_json = json.dumps(work_items_dict, indent=4)
                
                return work_items_json
            else:
                print(f"No work items found assigned to '{user_email}'.")
                return []

        except requests.exceptions.RequestException as e:
            print(f"Error retrieving work items for user '{user_email}': {str(e)}")
            return None

    def assign_work_item_to_user(self, work_item_id, user_email):
        """
        Assign a work item to a specific user in Azure DevOps
        Args:
            project_name (str): Name of the project
            work_item_id (int): ID of the work item
            user_email (str): Email of the user to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the update operation for assigning the work item
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AssignedTo",
                    value=user_email
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} assigned to {user_email} successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning work item: {str(e)}")
            return None

    def create_iteration(self, iteration_name, start_date, finish_date):
        """
        Create a new iteration in Azure DevOps using the REST API
        Args:
            project_name (str): Name of the project
            iteration_name (str): Name of the iteration
            start_date (str): Start date of the iteration in 'YYYY-MM-DD' format
            finish_date (str): Finish date of the iteration in 'YYYY-MM-DD' format
        Returns:
            dict: Created iteration object or None if failed
        """
        try:
            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }
            
            classification_url = f"https://dev.azure.com/{self.organization}/{self.project_name}/_apis/wit/classificationnodes/iterationpaths/classification?api-version=7.2-preview.1"

            # Define the URL for creating an iteration
            url = f"https://dev.azure.com/{self.organization}/{self.project_name}/{self.team_name}/_apis/work/teamsettings/iterations?api-version=7.2-preview.1"


            iteration_id = str(uuid.uuid4())
            # Define the payload for the iteration
            payload = {
                "id": iteration_id,
                "name": iteration_name,
                "attributes": {
                    "startDate": start_date,
                    "finishDate": finish_date
                }
            }

            # Send the POST request to create the iteration
            response = requests.post(url, headers=headers, json=payload)

            # Check if the request was successful
            response.raise_for_status()

            created_iteration = response.json()
            print(f"Iteration '{iteration_name}' created successfully in project '{self.project_name}'.")
            return created_iteration

        except requests.exceptions.RequestException as e:
            print(f"Error creating iteration: {str(e)}")
            return None

    def assign_work_item_to_iteration(self, work_item_id, iteration_path):
        """
        Assign a work item to a specific iteration in Azure DevOps
        Args:
            project_name (str): Name of the project
            work_item_id (int): ID of the work item
            iteration_path (str): Path of the iteration to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the update operation for assigning the work item to an iteration
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.IterationPath",
                    value=iteration_path
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} assigned to iteration '{iteration_path}' successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning work item to iteration: {str(e)}")
            return None
        
    def set_work_item_priority(self, work_item_id, priority):
        """
        Assign a work item to a specific iteration in Azure DevOps
        Args:
            project_name (str): Name of the project
            work_item_id (int): ID of the work item
            priority (str): priority to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the update operation for assigning the work item to an iteration
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/Microsoft.VSTS.Common.Priority",
                    value=priority
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Set Work item {work_item_id} priority '{priority}' successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning work item to iteration: {str(e)}")
            return None
        
    def update_work_item(self, work_item_id, field_updates):
        """
        Update any properties of a work item in Azure DevOps
        Args:
            work_item_id (int): ID of the work item
            field_updates (dict): Dictionary of field paths and their new values
                                e.g., {
                                    "System.Title": "New Title",
                                    "System.State": "Active",
                                    "System.Description": "New description"
                                }
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()
            
            document = [
                JsonPatchOperation(
                    op="add",
                    path=f"/fields/{field_path}",
                    value=field_value
                )
                for field_path, field_value in field_updates.items()
            ]

            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} updated successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error updating work item: {str(e)}")
            return None
    