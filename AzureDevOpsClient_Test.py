import os
import json
import logging
import sys
from AzureDevOpsClient import AzureDevOpsClient
from dotenv import load_dotenv

# Setup logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('azure_devops.log'),  # Log to a file
        logging.StreamHandler(sys.stdout)         # Log to console
    ]
)
# Load environment variables from .env file
load_dotenv('.env')
logger = logging.getLogger(__name__)

organization= os.getenv("DEVOPS_ORGINIZATION")
personal_access_token = os.getenv("AZURE_DEVOPS_PAT")

# Specify the base directory
base_dir = 'D:/development/repos'  # Replace with your desired base directory path

print(f"Current namespace: {__name__}")  # This will show you the actual namespace
logger.info(f"Organization: {organization}")
logger.info(f"Personal Access Token: {personal_access_token}")  

client = AzureDevOpsClient(organization,  personal_access_token)
client.project.get_process_templates()
client.project.get_project_by_name('SiamEComm')
# # client.project.create_project(project_name= 'SiamEComm', description= "A platform to help Thai farmers sell their products directly to consumers.", visibility= "private")

# client.project.add_readme_to_repo('SiamEComm')  
# # client.project.add_default_folders_to_repo('SiamEComm')
# client.project.add_folder('src/utils/blah/blah', 'This folder contains utility functions for the project.')

# phase = client.project.set_current_phase('planning')
# phase = client.project.get_current_phase()
# print(phase)

# client.project.add_user_to_team('AI_Architect@leeney-software.com', ['Build Administrators','Project Administrators'])   
# client.project.list_users_in_tenant()
# client.project.list_users_via_rest_api()
# client.project.add_user_to_team('AI_BackendDeveloper@leeney-software.com', ['Build Administrators','My Group'])
# json = client.project.to_json()
# print(json)
# client.project.create_area('Test Area')

# client.project.add_readme_to_repo('SiamEComm')
# client.project.add_default_folders_to_repo('SiamEComm')

# epic_item_id = client.project.create_backlog_item('Epic2', 'Test Description', 'Epic' )
# feature_item_id = client.project.create_backlog_item( 'Feature2', 'Test Description', 'Feature', epic_item_id )
# task_item_id = client.project.create_backlog_item('Task Item2', 'Test Description', 'Task', feature_item_id )

# client.project.create_iteration('Iteration 4', '2024-15-01', '2024-11-30')

# client.project.assign_work_item_to_iteration( epic_item_id, 'Iteration 4' )
# client.project.assign_work_item_to_iteration( feature_item_id, 'Iteration 4')
# client.project.assign_work_item_to_iteration( task_item_id, 'Iteration 4')

# client.project.assign_work_item_to_user( task_item_id, 'rene.vangeffen@live.nl')
# client.project.add_work_item_comment( task_item_id, 'This is a test comment')

# json = client.project.get_work_items_hierarchy()
# print(json)

# work_items = client.project.get_work_items_assigned_to_user('rene.vangeffen@live.nl')
# print(work_items)
# work_items = client.project.get_backlog_items(['Feature'])
# print(work_items)
# client.project.clone_repository_locally(base_dir,'SiamEComm')
# group = client.project.find_group_by_display_name('Contributors')
# print(group)
# user = client.project.find_user('AI_Architect@leeney-software.com')
# print(user)

# client.project.list_user_teams('rene.vangeffen@live.nl')
# #client.project.remove_user_matching('Build Service (LeeNey)')

# user = client.project.find_user('AI_Architect@leeney-software.com')
# print(user)
# group = client.project.get_group('Build Administrators')
# print(group)
# client.project.remove_user_from_team('AI_Architect@leeney-software.com')

client.project.delete_project('SiamEComm', base_dir) 
