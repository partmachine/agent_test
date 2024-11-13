import json
from AzureDevOpsClient import AzureDevOpsClient

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv('.env')

organization= os.getenv("DEVOPS_ORGINIZATION")
personal_access_token = os.getenv("AZURE_DEVOPS_PAT")

# Specify the base directory
base_dir = 'D:/development/repos'  # Replace with your desired base directory path

client = AzureDevOpsClient(organization,  personal_access_token)
client.project_details.get_process_templates()
# client.create_project(project_name= 'Thai Farmers Marketplace', description= "A platform to help Thai farmers sell their products directly to consumers.", visibility= "public")
# client.add_user_to_team('AI_Architect@leeney-software.com', ['Build Administrators','Project Administrators'])   
client.project_details.get_project_by_name('SiamEComm')
client.project_details.create_area('Test Area')

json = client.project_details.get_work_items_hierarchy()
print(json)
client.add_readme_to_repo('TestProject')
client.add_default_folders_to_repo('TestProject')

epic_item_id = client.project_details.create_backlog_item('Epic2', 'Test Description', 'Epic' )
feature_item_id = client.project_details.create_backlog_item( 'Feature2', 'Test Description', 'Feature', epic_item_id )
task_item_id = client.project_details.create_backlog_item('Task Item2', 'Test Description', 'Task', feature_item_id )

client.project_details.create_iteration('Iteration 1', '2024-11-01', '2024-11-30')

client.project_details.assign_work_item_to_iteration( epic_item_id, 'Iteration 1' )
client.project_details.assign_work_item_to_iteration( feature_item_id, 'Iteration 1')
client.project_details.assign_work_item_to_iteration( task_item_id, 'Iteration 1')

client.project_details.assign_work_item_to_user( task_item_id, 'rene.vangeffen@live.nl')
client.project_details.add_work_item_comment( task_item_id, 'This is a test comment')

work_items = client.project_details.get_work_items_assigned_to_user('rene.vangeffen@live.nl')
print(work_items)
work_items = client.project_details.get_backlog_items('Feature')
print(work_items)
client.project_details.clone_repository_locally(base_dir)
group = client.project_details.find_group_by_display_name('Contributors')
print(group)
user = client.project_details.find_user('rene.vangeffen@live.nl')
print(user)

client.project_details.list_active_directory_users()
client.project_details.list_user_teams('rene.vangeffen@live.nl')

user = client.project_details.find_user('AI_Architect@leeney-software.com')
print(user)
group = client.project_details.get_group('Build Administrators')
print(group)
client.project_details.remove_user_from_team('AI_Architect@leeney-software.com')

client.project_details.delete_project('TestProject', base_dir) 
