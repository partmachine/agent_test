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
        self.project = AzureDevOpsProject(self.organization, self.personal_access_token)    