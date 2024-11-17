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
import uuid

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

class GroupError(AzureDevOpsError):
    """Exception raised for group-related errors"""
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
                     created_by='', changed_by='', id=None, url=None, comments=None, items=None):
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
            self.items = items or []

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
                "items": [child.to_dict() for child in self.items] if self.items else []
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
    def create_project(self, project_name, description="", visibility="private", process_template_Name='Agile'):
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

            self.template_id = self.get_process_templates(process_template_Name)
            capabilities = {
                "versioncontrol": {"sourceControlType": "Git"},
                "processTemplate": {"templateTypeId": self.template_id}  # Dynamic template ID
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
                
                self.name = self.project_name
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
            url = f"{self.organization_url}/{self.name}/_apis/wit/wiql?api-version=6.0"
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
                                    items=[]
                                )

            # Build the hierarchy
            root_items = []
            child_items = set()

            # Identify child items
            for source_id, target_id in relations:
                child_items.add(target_id)
                if source_id in work_items_dict and target_id in work_items_dict:
                    work_items_dict[source_id].items.append(work_items_dict[target_id])

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
                item.items.sort(key=sort_by_type)

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
            "last_update_time": self.last_update_time.isoformat() if self.last_update_time else None,
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
                
                self.id = project.id
                self.name = project.name
                self.description = project.description
                self.url = project.url
                self.state = project.state
                self.revision = project.revision
                self.visibility = project.visibility
                self.last_update_time = project.last_update_time
                
                                                # Retrieve repositories in the project
                repos = self.git_client.get_repositories(project=project.id)

                # Set the first repository name found, if any
                if repos:
                    self.repo_name = repos[0].name
                    print(f"Repository '{self.repo_name}' found in project '{project_name}'.")
                else:
                    print(f"No repositories found in project '{project_name}'.")

                self.project_name = project.name
                self.team_name = self.project_name + ' Team'
                self.repo_name = self.project_name + ' Repository'
                #self.items = self.get_work_items_hierarchy()    
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
        Invite a user to the Azure DevOps organization and add them to existing groups
        Args:
            user_email (str): Email of the user to invite
            additional_groups (list): List of additional group names to add user to if they exist
        Returns:
            dict: Response from the API
        Raises:
            ValidationError: If email is invalid
            UserError: If user operation fails
        """
        try:
            validate_email(user_email)
            
            # Get team descriptor
            team_descriptor = self.get_team_descriptor(self.project_name, self.team_name)
            if not team_descriptor:
                print(f"Error: Team descriptor for '{self.team_name}' not found.")
                return None

            group_descriptors = [team_descriptor]
            
            # Process each additional group
            for group_name in additional_groups:
                # Try to get existing group
                group_json = self.get_group(group_name)
                if group_json:
                    group_info = json.loads(group_json)
                    group_descriptors.append(group_info['descriptor'])
                    print(f"Adding user to existing group: {group_name}")
                else:
                    print(f"Warning: Group '{group_name}' not found. Skipping.")

            # Add user to all found groups
            url = f"{self.vssps_url}/_apis/graph/users?api-version=7.1-preview.1"

            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            payload = {
                "principalName": user_email
            }

            response = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                params={'groupDescriptors': ','.join(group_descriptors)}
            )

            response.raise_for_status()

            print(f"User '{user_email}' added to Team: '{self.team_name}' and existing additional groups successfully.")
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
    
    def clone_repository_locally(self, base_directory, member_email=None, repo_name=None):
        """
        Clone a repository from Azure DevOps to a local directory
        Args:   
            base_directory (str): Local directory to clone the repository into
            member_email (str): Email of the member to add to the repository (optional)
            repo_name (str): Name of the repository (optional)
        """
        try:
            if not repo_name:
                repo_name = self.repo_name
                
            # Create hash from member_email if available, otherwise use credentials.password
            hash_input = member_email if member_email else self.credentials.password
            hash_object = hashlib.sha256(hash_input.encode())
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
    
    def create_backlog_item(self, title, description, item_type="Project Backlog Item", parent_id=None):
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
            if parent_id=='':
                parent_id=None
                
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
    
    def get_backlog_item_ids(self, item_type="Product Backlog Item"):
        """
        Get a list of backlog item IDs from a project in Azure DevOps using the REST API
        Args:
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
    




    def find_user(self, user_name_or_email, subject_types=['aad']):
        """
        Find a user in the Azure DevOps organization using the REST API
        Args:
            user_name_or_email (str): Username or email of the user to find
            subject_types (str): Type of subjects to search for (default is 'aad')
        Returns:
            dict: User object if found, None otherwise
        """
        try:
            # Join the subject types into a comma-separated string
            subject_types_str = ','.join(subject_types)

            # Define the URL for the users API
            url = f"{self.vssps_url}/_apis/graph/users?subjectTypes={subject_types_str}&api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list users
            response = requests.get(url, headers=headers, params={'subjectTypes': subject_types_str})

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
    
    def list_team_users(self):
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
            field_updates (list or dict): array of field paths and their new values,
                                        or a JSON/dict of field paths and values
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Convert field_updates to list if it's a dictionary/JSON
            if not isinstance(field_updates, list):
                if isinstance(field_updates, str):
                    # Parse JSON string to dictionary
                    field_updates = json.loads(field_updates)
                
                # Convert dictionary to list of tuples
                field_updates = field_updates.items()

            # Create a list of JsonPatchOperation objects for each field update
            document = [
                JsonPatchOperation(
                    op="add",
                    path=f"/fields/{field_path}",
                    value=value
                )
                for field_path, value in field_updates
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} updated successfully.")
            return updated_work_item

        except json.JSONDecodeError as e:
            print(f"Error parsing field updates JSON: {str(e)}")
            return None
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
    
    def get_group_by_descriptor(self, descriptor):
        """
        Get a group by its descriptor using the REST API
        Args:
            descriptor (str): The descriptor of the group to find
        Returns:
            str: JSON string of the group details if found, None otherwise
        """
        try:
            # Define the URL for the group API
            url = f"{self.vssps_url}/_apis/graph/groups/{descriptor}?api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to get the group
            response = requests.get(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract the group details
            group = response.json()
            
            # Convert the group object to a dictionary
            group_dict = {
                "display_name": group.get('displayName'),
                "descriptor": group.get('descriptor'),
                "url": group.get('url'),
                "origin": group.get('origin'),
                "subject_kind": group.get('subjectKind'),
                "domain": group.get('domain'),
                "mail_address": group.get('mailAddress'),
                "principal_name": group.get('principalName'),
                "legacy_descriptor": group.get('legacyDescriptor')
            }

            # Convert the dictionary to a JSON string
            group_json = json.dumps(group_dict, indent=4)
            return group_json

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting group by descriptor '{descriptor}': {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting group by descriptor '{descriptor}': {str(e)}")
            return None
    
    def find_group_by_display_name(self, display_name):
        """
        Find a group by its display name in Azure DevOps
        Args:
            display_name (str): Display name of the group to find
        Returns:
            object: Group object if found, None otherwise
        Raises:
            ValidationError: If display name is invalid
            GroupError: If group operation fails
        """
        try:
            if not display_name:
                raise ValidationError("Display name cannot be empty")

            # List all groups
            groups = self.graph_client.list_groups()
            
            # Find the group with matching display name
            for group in groups.graph_groups:
                if group.display_name.lower() == display_name.lower():
                    return group
                    
            logger.warning(f"Group with display name '{display_name}' not found")
            return None

        except ValidationError as e:
            raise e
        except Exception as e:
            raise GroupError(f"Error finding group '{display_name}': {str(e)}")
    
    def to_json(self):
        """
        Helper method to convert project properties to JSON format
        Returns:
            str: JSON string containing the project properties
        """
        try:
            # Only fetch items if they're not already present
            items = self.items
            if not items:
                items_json = self.get_work_items_hierarchy()
                if isinstance(items_json, str):
                    items = json.loads(items_json)
                
            project_dict = {
                "id": self.id,
                "name": self.name,
                "description": self.description,
                "url": self.url,
                "state": self.state,
                "revision": self.revision,
                "visibility": self.visibility,
                "repo_name": self.repo_name,
                "team_name": self.team_name,
                "last_update_time": self.last_update_time.isoformat() if self.last_update_time else None,
                "items": items
            }
            
            return json.dumps(project_dict, indent=4)

        except Exception as e:
            logger.error(f"Error in to_json: {str(e)}")
            return None
    
    def create_iteration(self, iteration_name, start_date, finish_date):
        """
        Create a new iteration in Azure DevOps using the REST API
        Args:
            iteration_name (str): Name of the iteration
            start_date (str): Start date of the iteration in 'YYYY-MM-DD' format
            finish_date (str): Finish date of the iteration in 'YYYY-MM-DD' format
        Returns:
            dict: Created iteration object or None if failed
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # First, create the iteration path
            classification_url = f"{self.organization_url}/{self.project_name}/_apis/wit/classificationnodes/iterations?api-version=7.1-preview.2"
            
            path_payload = {
                "name": iteration_name,
                "attributes": {
                    "startDate": start_date,
                    "finishDate": finish_date
                }
            }

            # Create the iteration path
            path_response = requests.post(classification_url, headers=headers, json=path_payload)
            path_response.raise_for_status()
                       

            print(f"Iteration '{iteration_name}' created successfully in project '{self.project_name}'.")
            return path_response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error creating iteration: {str(e)}")
            return None
        
    def assign_work_item_to_iteration(self, work_item_id, iteration_path):
        """
        Assign a work item to a specific iteration
        Args:
            work_item_id (int): ID of the work item to assign
            iteration_path (str): Path of the iteration to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Clean up iteration path - remove any 'Iteration' folder reference
            clean_iteration = iteration_path.replace('Iteration\\', '').replace('\\Iteration\\', '')
            
            # Get classification nodes to verify iteration exists
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }
            classification_url = f"{self.organization_url}/{self.project_name}/_apis/wit/classificationnodes/iterations?$depth=100&api-version=7.1-preview.2"
            
            response = requests.get(classification_url, headers=headers)
            response.raise_for_status()
            iterations = response.json()

            # Verify iteration exists
            iteration_found = False
            def find_iteration(node, target):
                if node.get('name') == target:
                    return True
                for child in node.get('children', []):
                    if find_iteration(child, target):
                        return True
                return False

            iteration_found = find_iteration(iterations, clean_iteration)
            
            if not iteration_found:
                print(f"Warning: Iteration '{clean_iteration}' not found in project. Work item will still be assigned but may cause issues.")

            # Define the update operation
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.IterationPath",
                    value=f"{self.project_name}\\{clean_iteration}"
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} assigned to iteration '{clean_iteration}' successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning work item to iteration: {str(e)}")
            return None
    
    def assign_work_item_to_user(self, work_item_id, user_email):        
        """
        Assign a work item to a specific user in Azure DevOps
        Args:
            work_item_id (int): ID of the work item
            user_email (str): Email of the user to assign the work item to
        Returns:
            object: Updated work item object or None if failed
        """
        try:
            # First, find the user to get their details
            user_json = self.find_user(user_email)
            if not user_json:
                print(f"Error: User '{user_email}' not found")
                return None
                
            # Parse the user JSON string to get the display name
            user_dict = json.loads(user_json)
            user_principal_name = user_dict.get('principal_name')
            
            if not user_principal_name:
                print(f"Error: Could not get principal name for user '{user_email}'")
                return None

            # Get the Work Item Tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Define the update operation for assigning the work item
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AssignedTo",
                    value=user_principal_name
                )
            ]

            # Update the work item
            updated_work_item = work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )

            print(f"Work item {work_item_id} assigned to {user_principal_name} successfully.")
            return updated_work_item

        except Exception as e:
            print(f"Error assigning work item: {str(e)}")
            return None
        
    def add_default_folders_to_repo(self, project_name, repo_name=None):
        """
        Add specified folders with a descriptive README.md file to the root of a repository in Azure DevOps
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository (optional)
            folders (list): List of folder names to add (optional)
        """
        try:
            folders = ['src', 'test', 'assets', 'docs', 'lib', 'build', 'deploy']

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
                "scripts": "# Deploy\n\nThis folder contains build, deployment, and other utility scripts."
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

                    work_item = WorkItemDetails(
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

    def remove_user_matching(self, user_email):
        """
        Remove users from Azure DevOps using the Graph client where user_email matches part of display name
        Args:
            user_email (str): Email or name pattern to match against user display names
        Returns:
            bool: True if any users were removed successfully, False otherwise
        """
        try:
            # Initialize the Graph client
            graph_client = self.connection.clients.get_graph_client()

            # Get all users
            users = graph_client.list_users()
            
            # Find all users whose display name contains the search string
            users_to_remove = [
                user for user in users.graph_users 
                if user_email.lower() in user.display_name.lower()
            ]

            if not users_to_remove:
                print(f"No users found with '{user_email}' in their display name.")
                return False

            removal_success = False
            for user in users_to_remove:
                try:
                    # Delete the user using their descriptor
                    graph_client.delete_user(user_descriptor=user.descriptor)
                    print(f"Successfully removed user: {user.display_name}")
                    removal_success = True
                except Exception as delete_error:
                    print(f"Failed to remove user {user.display_name}: {str(delete_error)}")

            return removal_success

        except Exception as e:
            print(f"Error during user removal operation: {str(e)}")
            return False

    
    def list_users_in_tenant(self, pattern=None, subject_types=['aad']):
        """
        List users in the Azure DevOps tenant using REST API, optionally filtered by a pattern
        Args:
            pattern (str, optional): Pattern to match against user display name, principal name, or email
            subject_types (list, optional): List of subject types to filter by (default: ['aad'])
        Returns:
            str: JSON string containing list of matching user objects or all users if no pattern provided
        """
        try:
            # Define the URL for the users API with subject types parameter
            subject_types_param = ','.join(subject_types)
            url = f"{self.vssps_url}/_apis/graph/users?subjectTypes={subject_types_param}&api-version=7.1-preview.1"

            # Define the headers for the request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # Send the GET request to list users
            response = requests.get(url, headers=headers)

            # Check if the request was successful
            response.raise_for_status()

            # Extract users from response
            users = response.json().get('value', [])
            
            # Convert users to a list of dictionaries with relevant information
            user_list = []
            for user in users:
                user_info = {
                    "display_name": user.get('displayName'),
                    "principal_name": user.get('principalName'),
                    "mail_address": user.get('mailAddress'),
                    "descriptor": user.get('descriptor'),
                    "domain": user.get('domain'),
                    "origin": user.get('origin'),
                    "origin_id": user.get('originId'),
                    "subject_kind": user.get('subjectKind')
                }
                
                # If pattern is provided, filter users
                if pattern:
                    pattern = pattern.lower()
                    if (pattern in user_info["display_name"].lower() or 
                        pattern in (user_info["principal_name"] or '').lower() or 
                        pattern in (user_info["mail_address"] or '').lower()):
                        user_list.append(user_info)
                else:
                    user_list.append(user_info)

            # Sort the list by display name
            user_list.sort(key=lambda x: x["display_name"])

            # Convert to JSON string for consistent output
            return json.dumps(user_list, indent=4)

        except requests.exceptions.RequestException as e:
            print(f"Error listing users in tenant: {str(e)}")
            return None

    def get_current_phase(self):
        """
        Get or create the Epic named 'Documentation' and return its phase
        Returns:
            str: Value after backslash in area path (e.g., 'development' from 'SiamEComm\\development'),
                 or None if operation failed
        """
        try:
            # Get the work item tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create WIQL query to find the Documentation Epic
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.AreaPath]
                    FROM WorkItems
                    WHERE [System.WorkItemType] = 'Epic'
                    AND [System.Title] = 'Documentation'
                    AND [System.TeamProject] = '{self.project_name}'
                """
            }

            # Execute the query
            query_results = work_item_tracking_client.query_by_wiql(wiql).work_items

            if not query_results:
                print("No Documentation Epic found. Creating new one...")
                # Create the Documentation Epic with default phase
                default_phase = 'inception'
                document = [
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Title",
                        value="Documentation"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.WorkItemType",
                        value="Epic"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Description",
                        value="Documentation Epic for tracking project phases"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.AreaPath",
                        value=f"{self.project_name}\\{default_phase}"
                    )
                ]

                # Create the work item
                work_item_tracking_client.create_work_item(
                    document=document,
                    project=self.project_name,
                    type="Epic"
                )
                print(f"Documentation Epic created with default phase: {default_phase}")
                return default_phase

            # Get the first matching work item's details
            work_item = work_item_tracking_client.get_work_item(query_results[0].id)
            area_path = work_item.fields.get('System.AreaPath')

            if area_path:
                # Parse out the value after the backslash
                parts = area_path.split('\\')
                if len(parts) > 1:
                    result = parts[1]
                    print(f"Documentation Epic found in area: {area_path}, returning phase: {result}")
                    return result
                else:
                    print(f"Documentation Epic found but area path has no backslash: {area_path}")
                    return None
            else:
                print("Documentation Epic found but has no area path.")
                return None

        except Exception as e:
            print(f"Error getting Documentation Epic area: {str(e)}")
            return None

    def set_current_phase(self, phase):
        """
        Set the area path of the Epic named 'Documentation', creating it if it doesn't exist
        Args:
            phase (str): Phase name to set as the area path
        Returns:
            str: Phase part of the area path if successful, None if operation failed
        """
        try:
            # Get the work item tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create WIQL query to find the Documentation Epic
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.AreaPath]
                    FROM WorkItems
                    WHERE [System.WorkItemType] = 'Epic'
                    AND [System.Title] = 'Documentation'
                    AND [System.TeamProject] = '{self.project_name}'
                """
            }

            # Execute the query
            query_results = work_item_tracking_client.query_by_wiql(wiql).work_items

            if not query_results:
                print("No Documentation Epic found. Creating new one...")
                document = [
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Title",
                        value="Documentation"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.WorkItemType",
                        value="Epic"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Description",
                        value="Documentation Epic for tracking project phases"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.AreaPath",
                        value=f"{self.project_name}\\{phase}"
                    )
                ]

                # Create the work item
                work_item_tracking_client.create_work_item(
                    document=document,
                    project=self.project_name,
                    type="Epic"
                )
                print(f"Documentation Epic created with phase: {phase}")
                return phase

            # Update existing Epic
            work_item_id = query_results[0].id
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AreaPath",
                    value=f"{self.project_name}\\{phase}"
                )
            ]

            # Update the work item
            work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )
            print(f"Documentation Epic updated with phase: {phase}")
            return phase

        except Exception as e:
            print(f"Error setting Documentation Epic phase: {str(e)}")
            return None
        
    def get_current_iteration(self):
        """
        Get or create the Epic named 'Documentation' and return its ITERATION
        Returns:
            str: Value after backslash in area path (e.g., 'development' from 'SiamEComm\\development'),
                 or None if operation failed
        """
        try:
            # Get the work item tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create WIQL query to find the Documentation Epic
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.IterationPath]
                    FROM WorkItems
                    WHERE [System.WorkItemType] = 'Epic'
                    AND [System.Title] = 'Documentation'
                    AND [System.TeamProject] = '{self.project_name}'
                """
            }

            # Execute the query
            query_results = work_item_tracking_client.query_by_wiql(wiql).work_items

            if not query_results:
                print("No Documentation Epic found. Creating new one...")
                # Create the Documentation Epic with default phase
                default_iteration = 'Sprint 1'
                document = [
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Title",
                        value="Documentation"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.WorkItemType",
                        value="Epic"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Description",
                        value="Documentation Epic for tracking project phases"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.IterationPath",
                        value=f"{self.project_name}\\{default_iteration}"
                    )
                ]

                # Create the work item
                work_item_tracking_client.create_work_item(
                    document=document,
                    project=self.project_name,
                    type="Epic"
                )
                print(f"Documentation Epic created with default iteration: {default_iteration}")
                return default_iteration

            # Get the first matching work item's details
            work_item = work_item_tracking_client.get_work_item(query_results[0].id)
            iteration_path = work_item.fields.get('System.IterationPath')

            if iteration_path:
                # Parse out the value after the backslash
                parts = iteration_path.split('\\')
                if len(parts) > 1:
                    result = parts[1]
                    print(f"Documentation Epic found in iteration: {iteration_path}, returning iteration: {result}")
                    return result
                else:
                    print(f"Documentation Epic found but iteration path has no backslash: {iteration_path}")
                    return None
            else:
                print("Documentation Epic found but has no iteration path.")
                return None

        except Exception as e:
            print(f"Error getting Documentation Epic iteration: {str(e)}")
            return None

    def set_current_iteration(self, iteration):
        """
        Set the area path of the Epic named 'Documentation', creating it if it doesn't exist
        Args:
            phase (str): Phase name to set as the area path
        Returns:
            str: Phase part of the area path if successful, None if operation failed
        """
        try:
            # Get the work item tracking client
            work_item_tracking_client = self.connection.clients.get_work_item_tracking_client()

            # Create WIQL query to find the Documentation Epic
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.AreaPath]
                    FROM WorkItems
                    WHERE [System.WorkItemType] = 'Epic'
                    AND [System.Title] = 'Documentation'
                    AND [System.TeamProject] = '{self.project_name}'
                """
            }

            # Execute the query
            query_results = work_item_tracking_client.query_by_wiql(wiql).work_items

            if not query_results:
                print("No Documentation Epic found. Creating new one...")
                document = [
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Title",
                        value="Documentation"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.WorkItemType",
                        value="Epic"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Description",
                        value="Documentation Epic for tracking project phases"
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.IterationPath",
                        value=f"{self.project_name}\\{iteration}"
                    )
                ]

                # Create the work item
                work_item_tracking_client.create_work_item(
                    document=document,
                    project=self.project_name,
                    type="Epic"
                )
                print(f"Documentation Epic created with iteration: {iteration}")
                return iteration

            # Update existing Epic
            work_item_id = query_results[0].id
            document = [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.IterationPath",
                    value=f"{self.project_name}\\{iteration}"
                )
            ]

            # Update the work item
            work_item_tracking_client.update_work_item(
                document=document,
                id=work_item_id,
                project=self.project_name
            )
            print(f"Documentation Epic updated with iteration: {iteration}")
            return iteration

        except Exception as e:
            print(f"Error setting Documentation Epic phase: {str(e)}")
            return None


    def add_folder(self, folder_path, description=None, repo_name=None):
        """
        Add a folder with a README.md file at the specified path in a repository.
        Creates intermediate folders if they don't exist.
        Args:            
            folder_path (str): Path where the folder should be created (e.g., 'src/utils')
            description (str): Description for the folder's README.md file (optional)
            repo_name (str): Name of the repository (optional)
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get all repositories in the project
            repos = self.git_client.get_repositories(project=self.project_name)
            
            # Find the repository to use
            if len(repos) == 1:
                # If only one repository exists, use it
                repo = repos[0]
                self.repo_name = repo.name  # Update the class's repo_name
                repo_name = repo.name
            else:
                # Use the provided repo_name or class repo_name
                if not repo_name:
                    repo_name = self.repo_name
                if not repo_name:
                    print("No repository name specified and multiple repositories exist.")
                    return False
                repo = next((r for r in repos if r.name == repo_name), None)
                if not repo:
                    print(f"Repository '{repo_name}' not found in project '{self.project_name}'.")
                    return False
                
            # Normalize folder path (remove leading/trailing slashes)
            folder_path = folder_path.strip('/')
            path_parts = folder_path.split('/')
            
            # Check if the branch exists
            branch_name = "main"
            refs = self.git_client.get_refs(repository_id=repo.id, project=self.project_name)
            branch_ref = next((ref for ref in refs if ref.name == f"refs/heads/{branch_name}"), None)

            if not branch_ref:
                print(f"Branch '{branch_name}' does not exist in repository '{repo_name}'.")
                return False

            # Create each folder in the path if it doesn't exist
            current_path = ""
            changes = []
            for i, part in enumerate(path_parts):
                current_path = f"{current_path}/{part}" if current_path else part
                
                # Check if this part of the path exists
                try:
                    self.git_client.get_item(repository_id=repo.id, 
                                           project=self.project_name,
                                           path=f"/{current_path}/README.md")
                except Exception:
                    # Folder doesn't exist, add it to changes
                    if i == len(path_parts) - 1:  # Last folder in path
                        if not description:
                            description = f"# {part.capitalize()}\n\nThis folder contains {part} related files."
                    else:
                        description = f"# {part.capitalize()}\n\nThis is a container folder for {part} related components."
                    
                    changes.append({
                        "changeType": "add",
                        "item": {"path": f"/{current_path}/README.md"},
                        "newContent": {
                            "content": description,
                            "contentType": "rawtext"
                        }
                    })

            if changes:
                # Create the commit with all the necessary folders
                push = {
                    "refUpdates": [{"name": f"refs/heads/{branch_name}", "oldObjectId": branch_ref.object_id}],
                    "commits": [{
                        "comment": f"Add folders in path: {folder_path}",
                        "changes": changes
                    }]
                }

                # Push the changes
                self.git_client.create_push(push, repository_id=repo.id, project=self.project_name)
                print(f"Folders in path '{folder_path}' with README.md files added successfully to repository '{repo_name}'.")
            else:
                print(f"All folders in path '{folder_path}' already exist in repository '{repo_name}'.")
            
            return True

        except Exception as e:
            print(f"Error adding folders to repository: {str(e)}")
            return False

    def update_iteration(self, iteration_name, start_date=None, finish_date=None):
        """
        Update an existing iteration in Azure DevOps using the REST API
        Args:
            iteration_name (str): Name of the iteration to update
            start_date (str, optional): New start date of the iteration in 'YYYY-MM-DD' format
            finish_date (str, optional): New finish date of the iteration in 'YYYY-MM-DD' format
        Returns:
            dict: Updated iteration object or None if failed
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + base64.b64encode((':' + self.credentials.password).encode()).decode()
            }

            # First, get the iteration ID
            classification_url = f"{self.organization_url}/{self.project_name}/_apis/wit/classificationnodes/iterations/{iteration_name}?api-version=7.1-preview.2"
            
            # Get current iteration details
            response = requests.get(classification_url, headers=headers)
            response.raise_for_status()
            current_iteration = response.json()

            # Prepare update payload
            update_payload = {
                "id": current_iteration['id'],
                "name": iteration_name,
                "attributes": {
                    "startDate": start_date if start_date else current_iteration['attributes'].get('startDate'),
                    "finishDate": finish_date if finish_date else current_iteration['attributes'].get('finishDate')
                }
            }

            # Update the iteration
            update_response = requests.patch(classification_url, headers=headers, json=update_payload)
            update_response.raise_for_status()
            
            print(f"Iteration '{iteration_name}' updated successfully in project '{self.project_name}'.")
            return update_response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error updating iteration: {str(e)}")
            return None

    def folder_exists(self, folder_path, repo_name=None):
        """
        Check if a folder exists in the repository
        Args:
            folder_path (str): Path to check (e.g., 'src/utils')
            repo_name (str): Name of the repository (optional)
        Returns:
            bool: True if folder exists, False otherwise
        """
        try:
            # Normalize folder path
            folder_path = folder_path.strip('/')
            
            # Get repository
            if not repo_name:
                repo_name = self.repo_name
            repo = self.git_client.get_repository(project=self.project_name, repository_id=repo_name)
            if not repo:
                return False

            # Try to get the folder item
            try:
                self.git_client.get_item(
                    repository_id=repo.id,
                    project=self.project_name,
                    path=f"/{folder_path}"
                )
                return True
            except Exception:
                return False

        except Exception:
            return False

    def file_exists(self, file_path, repo_name=None):
        """
        Check if a file exists in the repository
        Args:
            file_path (str): Path to check (e.g., 'src/utils/helper.py')
            repo_name (str): Name of the repository (optional)
        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            # Normalize file path
            file_path = file_path.strip('/')
            
            # Get repository
            if not repo_name:
                repo_name = self.repo_name
            repo = self.git_client.get_repository(project=self.project_name, repository_id=repo_name)
            if not repo:
                return False

            # Try to get the file item
            try:
                self.git_client.get_item(
                    repository_id=repo.id,
                    project=self.project_name,
                    path=f"/{file_path}",
                    include_content=False
                )
                return True
            except Exception:
                return False

        except Exception:
            return False