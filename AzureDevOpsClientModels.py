import base64
import json
import logging
import os
import time
import subprocess
import shutil
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import requests
from azure.devops.v7_1.core.models import TeamProject
from azure.devops.v7_1.work_item_tracking.models import JsonPatchOperation
from azure.devops.v7_1.graph.models import GraphSubjectLookup, GraphUser, GraphMembership
from azure.devops.v7_1.member_entitlement_management import MemberEntitlementManagementClient
import hashlib

logger = logging.getLogger(__name__)


class AzureDevOpsError(Exception):
    """Base exception class for Azure DevOps operations"""
    pass

class ProjectError(AzureDevOpsError):
    """Exception raised for project-related errors"""
    pass

class TeamError(AzureDevOpsError):
    """Exception raised for team-related errors"""
    pass

class WorkItemError(AzureDevOpsError):
    """Exception raised for work item-related errors"""
    pass

class RepositoryError(AzureDevOpsError):
    """Exception raised for repository-related errors"""
    pass

class UserError(AzureDevOpsError):
    """Exception raised for user-related errors"""
    pass

class ValidationError(AzureDevOpsError):
    """Exception raised for validation errors"""
    pass

def validate_project_name(name):
    """
    Validate project name according to Azure DevOps rules
    Args:
        name (str): Project name to validate
    Raises:
        ValidationError: If the name is invalid
    """
    if not name:
        raise ValidationError("Project name cannot be empty")
    if len(name) > 64:
        raise ValidationError("Project name cannot exceed 64 characters")
    if not name[0].isalpha():
        raise ValidationError("Project name must start with a letter")
    if not all(c.isalnum() or c in '-_' for c in name):
        raise ValidationError("Project name can only contain letters, numbers, hyphens, and underscores")

def validate_email(email):
    """
    Validate email format
    Args:
        email (str): Email to validate
    Raises:
        ValidationError: If the email is invalid
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")

def validate_path(path):
    """
    Validate file system path
    Args:
        path (str): Path to validate
    Raises:
        ValidationError: If the path is invalid
    """
    if not path:
        raise ValidationError("Path cannot be empty")
    if not os.path.isabs(path):
        raise ValidationError("Path must be absolute")


class WorkItemDetails:
        def __init__(self, title, description, work_item_type, state, assigned_to,
                     area_path='', team_project='', iteration_path='', reason='',
                     comment_count=0, changed_date='', created_date='', board_column='',
                     board_column_done=False, state_change_date='', priority=0,
                     value_area='', kanban_column='', kanban_column_done=False,
                     created_by='', changed_by='', id=None, url=None, comments=None, children=None):
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
            self.children = children or []

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
                "comments": self.comments,
                "children": [child.to_dict() for child in self.children] if self.children else []
            }
        
 
class AzureDevOpsProject(TeamProject):
    """
    A comprehensive implementation of Azure DevOps project operations.
    This class provides all the core functionality for interacting with Azure DevOps,
    including project management, work items, repositories, and team management.

    Attributes:
        organization (str): The Azure DevOps organization name
        personal_access_token (str): The PAT for authentication
        organization_url (str): The base URL for the organization
        vssps_url (str): The URL for VSSPS operations
        vsaex_url (str): The URL for VSAEX operations
        credentials (BasicAuthentication): The authentication credentials
        connection (Connection): The Azure DevOps connection
        graph_client: The client for graph operations
        git_client: The client for git operations
        core_client: The client for core operations
        build_client: The client for build operations
        project_name (str): The current project name
        team_name (str): The current team name
        repo_name (str): The current repository name
        local_repo_path (str): The path to the local repository

    Example:
        >>> project = AzureDevOpsProject("my-organization", "my-pat")
        >>> project.create_project("my-project")
        >>> project.create_repository("my-repo")
    """
    def __init__(self, organization, personal_access_token):
        self.organization = organization
        self.personal_access_token = personal_access_token
        self.id = None
        self.name = None
        self.description = None
        self.url = None
        self.state = None
        self.revision = None
        self.visibility = None
        self.last_update_time = None
        self.items = None    
        self.organization_url = f"https://dev.azure.com/{self.organization}"
        self.vssps_url = f"https://vssps.dev.azure.com/{self.organization}"
        self.vsaex_url = f"https://vsaex.dev.azure.com/{self.organization}"
        self.credentials = BasicAuthentication('', self.personal_access_token)
        self.connection = Connection(base_url=self.organization_url, creds=self.credentials)
        
        # Get clients
        self.graph_client = self.connection.clients.get_graph_client()
        self.git_client = self.connection.clients.get_git_client()
        self.core_client = self.connection.clients.get_core_client()
        self.build_client = self.connection.clients.get_build_client()

        self.template_id = self.get_process_templates("Agile")

        self.project_name = None
        self.team_name = None
        self.repo_name = None
        self.local_repo_path = None

    # Create a new project in Azure DevOps
    def create_project(self, project_name, description="", visibility="private"):
        """
        Create a new project in Azure DevOps
        Args:
            project_name (str): Name of the project
            description (str): Project description
            visibility (str): private or public
        Returns:
            object: Created project object
        Raises:
            ValidationError: If project name is invalid
            ProjectError: If project creation fails
        """
        try:
            validate_project_name(project_name)
            
            capabilities = {
                "versioncontrol": {"sourceControlType": "Git"},
                "processTemplate": {"templateTypeId": self.template_id}  # Dynamic template ID
            }
            self.project_name = project_name    
            self.team_name = project_name + ' Team'
            self.repo_name = project_name + ' Repository'
            
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

                self.create_area('inception')
                self.create_area('planning')
                self.create_area('development') 
                self.create_area('release')
                self.create_area('maintenance')
                self.create_area('retrospective')

                return operation_reference
            except Exception as e:
                print(f"Error creating project: {str(e)}")
                return None
        
        except Exception as e:
            raise ProjectError(f"Error creating project: {str(e)}")
    
    # Get the process template ID by name
    def get_process_templates(self, name="Agile"):
        """
        Get the process template ID by name
        Args:
            name (str): Name of the process template (default: "Agile")
        Returns:
            str: Template ID if found, None otherwise
        """
        url = f"{self.organization_url}/_apis/process/processes?api-version=7.1"   
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            processes = response.json().get('value', [])
            for process in processes:
                if process.get('name') == name:
                    return process.get('id')
        
        logger.warning(f"Process template '{name}' not found")
        return None

    # Delete a project from Azure DevOps and all its repositories
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
 
    def get_work_items_hierarchy(self):
        """
        Get all work items in a hierarchical structure (Epics -> Features -> User Stories -> Tasks)
        Returns:
            str: JSON string representing the hierarchical work item structure
        """
        try:
            # WIQL query to get all work items with parent/child relations
            wiql_query = {
                "query": f"""
                SELECT [System.Id], [System.WorkItemType], [System.Title], [System.State], 
                       [System.AssignedTo], [System.Description]
                FROM WorkItemLinks
                WHERE [Source].[System.TeamProject] = '{self.project_name}'
                AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
                MODE (Recursive)
                """
            }

            # Make API request to get work items
            url = f"{self.organization_url}/{self.project_name}/_apis/wit/wiql?api-version=6.0"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            response = requests.post(url, json=wiql_query, headers=headers)
            response.raise_for_status()

            # Process work items into a hierarchical structure
            work_items_dict = {}
            relations = []
            # Extract work item IDs and relations
            for relation in response.json().get('workItemRelations', []):
                if relation.get('source'):
                    source_id = relation['source']['id']
                    target_id = relation['target']['id']
                    relations.append((source_id, target_id))
                    
                    # Get details for both source and target work items if not already fetched
                    for item_id in (source_id, target_id):
                        if item_id not in work_items_dict:
                            item_url = f"{self.organization_url}/_apis/wit/workitems/{item_id}?api-version=6.0"
                            item_response = requests.get(item_url, headers=headers)
                            if item_response.status_code == 200:
                                item_data = item_response.json()
                                fields = item_data['fields']
                                work_items_dict[item_id] = WorkItemDetails(
                                    id=item_id,
                                    url=item_data.get('url', ''),
                                    title=fields.get('System.Title', ''),
                                    description=fields.get('System.Description', ''),
                                    work_item_type=fields.get('System.WorkItemType', ''),
                                    state=fields.get('System.State', ''),
                                    assigned_to=fields.get('System.AssignedTo', {}).get('displayName', ''),
                                    area_path=fields.get('System.AreaPath', ''),
                                    team_project=fields.get('System.TeamProject', ''),
                                    iteration_path=fields.get('System.IterationPath', ''),
                                    reason=fields.get('System.Reason', ''),
                                    comment_count=fields.get('System.CommentCount', 0),
                                    changed_date=fields.get('System.ChangedDate', ''),
                                    created_date=fields.get('System.CreatedDate', ''),
                                    board_column=fields.get('System.BoardColumn', ''),
                                    board_column_done=fields.get('System.BoardColumnDone', False),
                                    state_change_date=fields.get('System.StateChangeDate', ''),
                                    priority=fields.get('Microsoft.VSTS.Common.Priority', 0),
                                    value_area=fields.get('Microsoft.VSTS.Common.ValueArea', ''),
                                    kanban_column=fields.get('System.KanbanColumn', ''),
                                    kanban_column_done=fields.get('System.KanbanColumnDone', False),
                                    created_by=fields.get('System.CreatedBy', {}).get('displayName', ''),
                                    changed_by=fields.get('System.ChangedBy', {}).get('displayName', ''),
                                    comments=[],
                                    children=[]
                                )

            # Build the hierarchy
            root_items = []
            child_items = set()

            # Identify child items
            for source_id, target_id in relations:
                child_items.add(target_id)
                if source_id in work_items_dict and target_id in work_items_dict:
                    work_items_dict[source_id].children.append(work_items_dict[target_id])

            # Collect root items (items that are not children)
            for item_id in work_items_dict:
                if item_id not in child_items:
                    root_items.append(work_items_dict[item_id])

            # Sort items by work item type
            def sort_by_type(item):
                type_order = {'Epic': 0, 'Feature': 1, 'User Story': 2, 'Task': 3}
                return type_order.get(item.work_item_type, 999)

            root_items.sort(key=sort_by_type)
            for item in work_items_dict.values():
                item.children.sort(key=sort_by_type)

            # Convert root items to dictionaries (children will be converted recursively)
            hierarchy_dict = [item.to_dict() for item in root_items]
            
            # Convert to JSON
            hierarchy_json = json.dumps(hierarchy_dict, indent=2)
            return hierarchy_json

        except Exception as e:
            print(f"Error getting hierarchical work items: {str(e)}")
            return None
        
    # Convert the project details to a dictionary   
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "state": self.state,
            "revision": self.revision,
            "visibility": self.visibility,
            "last_update_time": self.last_update_time,
            "items": {key: item.to_dict() for key, item in self.items.items()} if self.items else {}
        }

    # Create a new project from a TeamProject object
    @classmethod
    def from_team_project(cls, team_project: TeamProject, items=None):
        return cls(
            id=team_project.id,
            name=team_project.name,
            description=team_project.description,
            url=team_project.url,
            state=team_project.state,
            revision=team_project.revision,
            visibility=team_project.visibility,
            last_update_time=team_project.last_update_time,
            items=items
        )
    
    # Create a new project from a dictionary
    @classmethod
    def from_dict(cls, data):
        items = {
            key: WorkItemDetails(**item_data) 
            for key, item_data in data.get('items', {}).items()
        }
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            description=data.get('description'),
            url=data.get('url'),
            state=data.get('state'),
            revision=data.get('revision'),
            visibility=data.get('visibility'),
            last_update_time=data.get('last_update_time'),
            items=items
        )
    
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
                self.repo_name = self.project_name + ' Repository'
                self.items = self.get_work_items_hierarchy()    
                return project
            else:
                print(f"Project '{project_name}' not found.")
                return None

        except Exception as e:
            print(f"Error retrieving project '{project_name}': {str(e)}")
            return None
    
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
        Invite a user to the Azure DevOps organization
        Args:
            user_email (str): Email of the user to invite
            additional_groups (list): List of additional group names
        Returns:
            dict: Response from the API
        Raises:
            ValidationError: If email is invalid
            UserError: If user operation fails
        """
        try:
            validate_email(user_email)
            
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
    
    def clone_repository_locally(self, base_directory, repo_name=None):
        """
        Clone a repository from Azure DevOps to a local directory
        Args:
            base_directory (str): Local directory to clone the repository into
            repo_name (str): Name of the repository (optional)
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
            self.git_client.delete_repository(repository_id=repo.id, project=project_name)
            print(f"Repository '{repo_name}' deleted from project '{project_name}'.")

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
    
    def get_team_descriptor(self, project_name, team_name):
        """
        Get the team descriptor for a team using the REST API
        Args:
            project_name (str): The name of the project
            team_name (str): The name of the team
        Returns:
            str: Team descriptor if found, None otherwise
        """
        try:
            # Get team ID first
            url1 = f"{self.organization_url}/_apis/projects/{project_name}/teams/{team_name}?api-version=7.1-preview.3"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to get the team ID
            response = requests.get(url1, headers=headers)
            team_id = response.json().get('id', None)

            if not team_id:
                print(f"Team ID not found for team '{team_name}'")
                return None

            # Get descriptor using team ID
            url2 = f"{self.vssps_url}/_apis/graph/descriptors/{team_id}?api-version=7.1"
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
    
    def get_backlog_item_ids(self, item_type):
        """
        Get a list of backlog item IDs of a specific type from a project in Azure DevOps
        Args:
            item_type (str): The type of the backlog item
        Returns:
            list: List of backlog item IDs
        """
        try:
            # Initialize an empty list to store all work item IDs
            work_item_ids = []

            # WIQL query to get all work items of the specified type
            wiql_query = {
                "query": f"""
                SELECT [System.Id]
                FROM WorkItems
                WHERE [System.TeamProject] = '{self.project_name}'
                AND [System.WorkItemType] = '{item_type}'
                """
            }

            # Make API request to get work item IDs
            url = f"{self.organization_url}/{self.project_name}/_apis/wit/wiql?api-version=6.0"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            response = requests.post(url, json=wiql_query, headers=headers)
            response.raise_for_status()

            # Extract work item IDs
            for item in response.json().get('workItems', []):
                work_item_ids.append(item['id'])

            return work_item_ids

        except Exception as e:
            print(f"Error getting backlog item IDs: {str(e)}")
            return []
    
    def get_backlog_items(self, item_types=["Product Backlog Item", "Epic", "Feature", "User story", "Task"]):
        """
        Get a list of backlog items from a project in Azure DevOps
        Args:
            item_types (list): List of work item types to retrieve
        Returns:
            str: JSON string of work items if found, None otherwise
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
                    work_item_details = WorkItemDetails(
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
                        comments=[],  # Assuming comments are not fetched here
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
    
    def find_user(self, user_name_or_email, subject_types='aad'):
        """
        Find a user in the Azure DevOps organization using the REST API
        Args:
            user_name_or_email (str): Username or email of the user to find
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

            # Filter the user based on principalName or mailAddress
            for user in users:
                if (user.get('principalName', '').lower() == user_name_or_email.lower() or
                    user.get('mailAddress', '').lower() == user_name_or_email.lower()):
                    # Convert the user object to a dictionary
                    user_dict = {
                        "display_name": user.get('displayName', ''),
                        "principal_name": user.get('principalName', ''),
                        "mail_address": user.get('mailAddress', ''),
                        "descriptor": user.get('descriptor', ''),
                        "url": user.get('url', '')
                    }
                    # Convert the dictionary to a JSON string
                    user_json = json.dumps(user_dict, indent=4)
                    return user_json

            print(f"No user found with identifier '{user_name_or_email}'.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error finding user '{user_name_or_email}': {str(e)}")
            return None

        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
            return None
    
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

            return items[0]['id'] if items else None

        except requests.exceptions.RequestException as e:
            print(f"Error searching for user by email '{user_email}': {str(e)}")
            return None
    
    def set_work_item_phase(self, work_item_id, phase_path):
        """
        Set the phase path for a work item in Azure DevOps
        Args:
            work_item_id (int): ID of the work item
            phase_path (str): Phase path to assign to the work item
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AreaPath",
                    value=f"{self.project_name}/{phase_path}"
                )
            ]

            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} phase path set to '{phase_path}' successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error setting work item area path: {str(e)}")
            return None
    
    def create_area(self, area_name):
        """
        Create a new area in Azure DevOps using the REST API
        Args:
            area_name (str): Name of the area to create
        Returns:
            dict: Created area object or None if failed
        """
        try:
            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Define the URL for creating an area
            url = f"{self.organization_url}/{self.project_name}/_apis/wit/classificationnodes/areas?api-version=7.1-preview.2"

            # Define the payload for the area
            payload = {
                "name": area_name,
                "structureType": "area"
            }

            # Send the POST request to create the area
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            created_area = response.json()
            print(f"Area '{area_name}' created successfully in project '{self.project_name}'.")
            return created_area

        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            print(f"Request error occurred: {req_err}")
        except Exception as e:
            print(f"Error creating area: {str(e)}")
        return None
    
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
    
    def get_work_item_details(self, work_item_id):
        """
        Get detailed information about a specific work item
        Args:
            work_item_id (int): ID of the work item
        Returns:
            WorkItemDetails: Object containing work item details or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Get the work item
            work_item = work_item_tracking_client.get_work_item(work_item_id)
            
            if work_item:
                fields = work_item.fields
                # Create WorkItemDetails object
                work_item_details = WorkItemDetails(
                    id=work_item.id,
                    url=work_item.url,
                    title=fields.get('System.Title', ''),
                    description=fields.get('System.Description', ''),
                    work_item_type=fields.get('System.WorkItemType', ''),
                    state=fields.get('System.State', ''),
                    assigned_to=fields.get('System.AssignedTo', {}).get('displayName', ''),
                    area_path=fields.get('System.AreaPath', ''),
                    team_project=fields.get('System.TeamProject', ''),
                    iteration_path=fields.get('System.IterationPath', ''),
                    reason=fields.get('System.Reason', ''),
                    comment_count=fields.get('System.CommentCount', 0),
                    changed_date=fields.get('System.ChangedDate', ''),
                    created_date=fields.get('System.CreatedDate', ''),
                    board_column=fields.get('System.BoardColumn', ''),
                    board_column_done=fields.get('System.BoardColumnDone', False),
                    state_change_date=fields.get('System.StateChangeDate', ''),
                    priority=fields.get('Microsoft.VSTS.Common.Priority', 0),
                    value_area=fields.get('Microsoft.VSTS.Common.ValueArea', ''),
                    kanban_column=fields.get('System.KanbanColumn', ''),
                    kanban_column_done=fields.get('System.KanbanColumnDone', False),
                    created_by=fields.get('System.CreatedBy', {}).get('displayName', ''),
                    changed_by=fields.get('System.ChangedBy', {}).get('displayName', '')
                )
                
                # Get comments if they exist
                if work_item_details.comment_count > 0:
                    comments = work_item_tracking_client.get_comments(self.project_name, work_item_id)
                    work_item_details.comments = [comment.text for comment in comments.comments]

                return work_item_details

        except Exception as e:
            print(f"Error getting work item details: {str(e)}")
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
    
    def update_work_item(self, work_item_id, field_updates):
        """
        Update fields of an existing work item
        Args:
            work_item_id (int): ID of the work item to update
            field_updates (dict): Dictionary of field paths and their new values
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create a list of JsonPatchOperation objects for each field update
            document = [
                JsonPatchOperation(
                    op="add",
                    path=f"/fields/{field_path}",
                    value=value
                )
                for field_path, value in field_updates.items()
            ]

            # Update the work item
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
    
    def create_team(self, team_name=None, description=""):
        """
        Create a new team in Azure DevOps
        Args:
            team_name (str): Name of the team (optional, defaults to project name + ' Team')
            description (str): Description of the team
        Returns:
            object: Created team object or None if failed
        """
        try:
            if team_name is None:
                team_name = self.team_name

            # Create the team
            team = self.core_client.create_team(
                project_id=self.project_name,
                team={
                    "name": team_name,
                    "description": description
                }
            )

            print(f"Team '{team_name}' created successfully in project '{self.project_name}'")
            return team

        except Exception as e:
            print(f"Error creating team: {str(e)}")
            return None
    
    def delete_user_via_rest_api(self, user_descriptor):
        """
        Delete a user from Azure DevOps using the REST API
        Args:
            user_descriptor (str): Descriptor of the user to delete
        Returns:
            bool: True if successful, False otherwise
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
    
    def get_work_item_comments(self, work_item_id):
        """
        Get comments for a specific work item
        Args:
            work_item_id (int): ID of the work item
        Returns:
            list: List of comments or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Get the comments
            comments = work_item_tracking_client.get_comments(
                project=self.project_name,
                work_item_id=work_item_id
            )

            if comments and comments.comments:
                # Extract comment texts and return as list
                comment_list = [comment.text for comment in comments.comments]
                print(f"Retrieved {len(comment_list)} comments for work item {work_item_id}")
                return comment_list
            else:
                print(f"No comments found for work item {work_item_id}")
                return []

        except Exception as e:
            print(f"Error getting work item comments: {str(e)}")
            return None
    
    def get_work_item_relations(self, work_item_id):
        """
        Get all relations for a specific work item
        Args:
            work_item_id (int): ID of the work item
        Returns:
            list: List of related work items or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Get the work item with relations
            work_item = work_item_tracking_client.get_work_item(
                id=work_item_id,
                project=self.project_name,
                expand="Relations"
            )

            if work_item and work_item.relations:
                relations = []
                for relation in work_item.relations:
                    # Extract the related work item ID from the URL
                    related_id = relation.url.split('/')[-1]
                    relation_type = relation.rel
                    
                    # Get details of the related work item
                    related_item = work_item_tracking_client.get_work_item(int(related_id))
                    if related_item:
                        relations.append({
                            'id': related_id,
                            'type': relation_type,
                            'title': related_item.fields['System.Title'],
                            'state': related_item.fields['System.State']
                        })

                print(f"Retrieved {len(relations)} relations for work item {work_item_id}")
                return relations
            else:
                print(f"No relations found for work item {work_item_id}")
                return []

        except Exception as e:
            print(f"Error getting work item relations: {str(e)}")
            return None
    
    