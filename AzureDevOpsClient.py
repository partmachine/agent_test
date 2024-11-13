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
from AzureDevOpsClientModels import AzureDevOpsProject, WorkItemDetails

class AzureDevOpsClient:    
    def __init__(self, organization, personal_access_token):
        """
        Initialize Azure DevOps client
        Args:
            organization_url (str): The URL of your Azure DevOps organization
            personal_access_token (str): Azure DevOps Personal Access Token
        """
        self.organization = organization
        self.personal_access_token = personal_access_token
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
        self.project_details = AzureDevOpsProject(self.organization, self.personal_access_token)


    
    
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
    
    