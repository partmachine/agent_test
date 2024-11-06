import subprocess
import os

class DotNETCLIClient:
    def __init__(self):
        self.verify_dotnet_installed()

    def verify_dotnet_installed(self):
        """Verify that .NET SDK is installed"""
        try:
            subprocess.run(['dotnet', '--version'], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            raise RuntimeError(".NET SDK is not installed or not in PATH")

    def new_project(self, template, output_dir=None, name=None):
        """
        Create a new .NET project
        Args:
            template (str): The template to use (e.g., 'console', 'classlib', 'web')
            output_dir (str, optional): Output directory for the project
            name (str, optional): Name of the project
        """
        command = ['dotnet', 'new', template]
        if output_dir:
            command.extend(['-o', output_dir])
        if name:
            command.extend(['-n', name])
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Project created successfully: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error creating project: {e.stderr}")
            return False

    def build(self, project_path=None):
        """Build the .NET project"""
        command = ['dotnet', 'build']
        if project_path:
            command.append(project_path)
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Build successful: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Build failed: {e.stderr}")
            return False

    def run(self, project_path=None):
        """Run the .NET project"""
        command = ['dotnet', 'run']
        if project_path:
            command.extend(['--project', project_path])
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Run output: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Run failed: {e.stderr}")
            return False

    def new_solution(self, name=None):
        """
        Create a new solution file
        Args:
            name (str, optional): Name of the solution
        """
        command = ['dotnet', 'new', 'sln']
        if name:
            command.extend(['-n', name])
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Solution created successfully: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error creating solution: {e.stderr}")
            return False

    def add_project_to_solution(self, sln_path, project_path):
        """
        Add a project to a solution
        Args:
            sln_path (str): Path to the solution file
            project_path (str): Path to the project file
        """
        command = ['dotnet', 'sln', sln_path, 'add', project_path]
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Project added to solution successfully: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error adding project to solution: {e.stderr}")
            return False

    def new_gitignore(self):
        """
        Create a new .gitignore file using the dotnet CLI
        Returns:
            bool: True if successful, False otherwise
        """
        command = ['dotnet', 'new', 'gitignore']
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"Gitignore created successfully: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error creating gitignore: {e.stderr}")
            return False