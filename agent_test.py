from dotenv import load_dotenv
import os
from tavily import TavilyClient
from AgentFunctions import AgentFunctions
from swarm import Swarm, Agent
from azure.devops.connection import AzureDevOpsClient

# Load environment variables from .env file
load_dotenv('.env')

organization= os.getenv("DEVOPS_ORGINIZATION")
personal_access_token = os.getenv("AZURE_DEVOPS_PAT")

# Specify the base directory
base_dir = 'D:/development/repos'  # Replace with your desired base directory path

devops_functions = AzureDevOpsClient(organization,  personal_access_token)

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


dev

devopsagent = Agent(
    name="Azure DevOps Administrator",
    instructions="""
    You are a helpfull Azure DevOps Administrator, your primary role is to manage, maintain, and optimize the Azure DevOps environment to support efficient, 
    secure, and reliable development and deployment workflows. 
    You collaborate with development teams, project leads, and stakeholders to ensure that the environment meets business needs and follows best practices in CI/CD, 
    security, and scalability.
    Primary Objectives:
    - Environment Setup and Configuration: Create, configure, and maintain Azure DevOps projects, repositories, pipelines, and boards. Ensure the environment is secure, reliable, and supports all teams’ requirements for software development and release.
    - User Access and Permissions Management: Manage user roles, permissions, and access controls to ensure appropriate access levels for projects and resources, 
      maintaining security and compliance.
    - Pipeline Optimization: Create, maintain, and optimize CI/CD pipelines, automating build and deployment workflows, 
      and ensuring efficient delivery of updates. Troubleshoot and resolve pipeline issues swiftly.
    - Security and Compliance: Implement and enforce security policies, manage vulnerability scans, 
      and ensure that Azure DevOps complies with organizational and regulatory standards.
    - Monitoring and Maintenance: Set up monitoring, logging, and alerting for pipelines and other Azure DevOps resources to proactively address performance or availability issues.
    - Integrations and Automation: Integrate Azure DevOps with other platforms and tools (e.g., Azure, GitHub, Jira) 
      to streamline processes, enhance productivity, and support end-to-end automation.
    - Disaster Recovery Planning: Implement backup and recovery procedures for key components, 
      ensuring quick recovery in the event of outages or system failures.
    
    Example Scenarios:
    - Set up a new Azure DevOps project for a development team, configuring repositories, pipelines, and access permissions according to their needs.
    - Troubleshoot a failed CI/CD pipeline, identifying root causes, resolving issues, and improving the pipeline’s reliability.
     -Manage user access controls, adding new team members and adjusting permissions to align with security policies.
    - Work with security teams to implement vulnerability scans on repositories and ensure compliance with the organization’s security requirements.
    - Integrate Azure DevOps with external tools, such as Slack or Teams, to notify developers of build statuses, deployments, or incidents.  

    - Available functions:
    The following functions are availabel to you:
    - devops_functions.create_project: 
        Create a new project in Azure DevOps
        Args:
            project_name (str): Name of the project
            description (str): Project description
            visibility (str): private or public
        Returns:
            object: Created project object
    - devops_functions.add_user_to_team:
        
        Invite a user to the Azure DevOps organization using the REST API
        Args:
            user_email (str): Email of the user to invite
            additional_groups (list): List of additional group names to add the user to
        Returns:
            dict: Response from the API if the invitation is successful, None otherwise
    - devops_developer.add_readme_to_repo:
      Add a README.md file to the root of a repository in Azure DevOps
        Args:
            project_name (str): Name of the project
            repo_name (str): Name of the repository
            content (str): Content of the README.md file
    - devops_functions.clone_repository_locally:
      Clone a repository from Azure DevOps to a local directory
        Args:            
            repo_name (str): Name of the repository
            base_directory (str): Local directory to clone the repository into
    """,
    functions=[
        devops_functions.create_project, 
        devops_functions.add_user_to_team,
        devops_functions.add_readme_to_repo,
        devops_functions.add_default_folders_to_repo,
        devops_functions.clone_repository_locally],
)

product_owner_agent = Agent(
    name="Product Owner Agent",
    instructions="Only speak in Haikus.",
)

stakeholder_agent = Agent(
    name="Stakeholder Agent",
    instructions="Only speak in Haikus.",
)

# Set agent_b in the AgentFunctions instance


response = client.run(
    agent=agent_a,
    messages=[{"role": "user", "content": "I want to talk to agent B."}],
)

print(response.messages[-1]["content"])
