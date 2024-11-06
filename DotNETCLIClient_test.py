from DotNETCLIClient import DotNETCLIClient

# Instantiate the DotNETCLIClient class
dotnet_cli_client = DotNETCLIClient()

# Test the get_version method
dotnet_version = dotnet_cli_client.get_version()
if dotnet_version:
    print(f".NET CLI Version: {dotnet_version}")
else:
    print("Failed to retrieve .NET CLI version.")

# Test the execute_command method with a sample command
sample_command = "dotnet new gitignore"
command_output = dotnet_cli_client.execute_command(sample_command)
if command_output:
    print(f"Command Output: {command_output}")
else:
    print("Failed to execute the command.")