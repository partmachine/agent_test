from multiprocessing import context
from pickle import GET
from dotenv import load_dotenv
import os
from tavily import TavilyClient
from AgentFunctions import AgentFunctions
from swarm import Swarm, Agent
from AzureDevOpsClient import AzureDevOpsClient  # Adjust 'path.to.file' to the actual path and file name where AzureDevOpsClient is defined
from DevOpsAgent import DevOpsAgent
from prompts import *


# Load environment variables from .env file
load_dotenv('.env')


organization= os.getenv("DEVOPS_ORGINIZATION")
personal_access_token = os.getenv("AZURE_DEVOPS_PAT")

devops_functions = AzureDevOpsClient(organization, personal_access_token)

def escalate_to_agent(reason=None):
    return f"Escalating to agent: {reason}" if reason else "Escalating to agent"

def valid_to_change_flight():
    return "Customer is eligible to change flight"

def change_flight():
    return "Flight was successfully changed!"

def initiate_refund():
    status = "Refund initiated"
    return status

def initiate_flight_credits():
    status = "Successfully initiated flight credits"
    return status

def case_resolved():
    return "Case resolved. No further questions."

def initiate_baggage_search():
    return "Baggage was found!"


def transfer_to_product_owner():
    phase = context_variables.get("phase").lower()
    agents = {
        "inception phase": product_owner_inception,
        "planning phase": product_owner_planning,
        "development phase": product_owner_development,
        # Add other phases and corresponding agents here as needed
    }

    for key in agents:
        # Check if the phase is contained within the agent's key
        if phase in key:
            return agents[key]
        
    return product_owner_inception

# generic functions
def transfer_to_product_owner_planning():
    print(f"TRANSFER_TO_PRODUCT_OWNER_PLANNING")
    return product_owner_planning

def transfer_to_product_owner_development():
    print(f"TRANSFER_TO_PRODUCT_OWNER_DEVELOPMENT")
    return product_owner_development

def transfer_to_architect_planning():
    print(f"TRANSFER_TO_DEVELOPMENT_ARCHITECT")
    development_architect_planning.calling_agent = current_agent
    return development_architect_planning

def get_project_name():
    return context_variables["project_name"]

def get_iteration():
    return context_variables["iteration"]

def get_phase():
    return context_variables["phase"]

def set_project_name(project_name):
    context_variables["project_name"] = project_name

def set_iteration(iteration_name):
    context_variables["iteration_name"] = iteration_name

def set_phase(phase):
    context_variables["phase"] = phase
    transfer_to_product_owner()


# def triage_instructions(context_variables):
#     customer_context = context_variables.get("customer_context", None)
#     flight_context = context_variables.get("flight_context", None)
#     return f"""You are to triage a users request, and call a tool to transfer to the right intent.
#     Once you are ready to transfer to the right intent, call the tool to transfer to the right intent.
#     You dont need to know specifics, just the topic of the request.
#     When you need more information to triage the request to an agent, ask a direct question without explaining why you're asking it.
#     Do not share your thought process with the user! Do not make unreasonable assumptions on behalf of user.
#     The customer context is here: {customer_context}, and flight context is here: {flight_context}"""


product_owner_inception = DevOpsAgent(
    name="Product Owner Agent (INCEPTION)",
    instructions=STARTER_PROMPT + PRODUCT_OWNER_INCEPTION,
    functions=[
        devops_functions.create_project,
        devops_functions.get_project_by_name,
        devops_functions.get_work_items_hierarchy,
        devops_functions.create_backlog_item,
        devops_functions.add_work_item_comment,
        devops_functions.assign_work_item_to_iteration,
        devops_functions.create_iteration,          
        devops_functions.set_work_item_priority,
        devops_functions.update_work_item,
        get_project_name,
        get_iteration,
        get_phase,
        set_project_name,
        set_iteration,
        set_phase,  
        transfer_to_architect_planning,  
        transfer_to_product_owner,
        transfer_to_product_owner_planning
    ],
)

product_owner_planning = DevOpsAgent(
    name="Product Owner Agent (PLANNING)",
    instructions=STARTER_PROMPT + PRODUCT_OWNER_PLANNING,
    functions=[
        devops_functions.get_project_by_name,
        devops_functions.get_work_items_hierarchy,
        devops_functions.create_backlog_item,
        devops_functions.add_work_item_comment,
        devops_functions.assign_work_item_to_iteration,
        devops_functions.create_iteration,          
        devops_functions.set_work_item_priority,
        devops_functions.update_work_item,
        get_project_name,
        get_iteration,
        get_phase,
        set_project_name,
        set_iteration,
        set_phase,  
        transfer_to_architect_planning,
        transfer_to_product_owner,
        transfer_to_product_owner_planning,
        transfer_to_product_owner_development
    ],
)

product_owner_development = DevOpsAgent(
    name="Product Owner Agent (DEVELOPMENT)",
    instructions=STARTER_PROMPT + PRODUCT_OWNER_PLANNING,
    functions=[
        devops_functions.create_project,
        devops_functions.get_project_by_name,
        devops_functions.get_work_items_hierarchy,
        devops_functions.create_backlog_item,
        devops_functions.add_work_item_comment,
        devops_functions.assign_work_item_to_iteration,
        devops_functions.create_iteration,          
        devops_functions.set_work_item_priority,
        devops_functions.update_work_item,
        get_project_name,
        get_iteration,
        get_phase,
        set_project_name,
        set_iteration,
        set_phase,
        transfer_to_product_owner,
        transfer_to_product_owner_planning,
        transfer_to_product_owner_development
    ],
)

development_architect_planning = DevOpsAgent(
    name="Development Architecture Agent (PLANNING)",
    instructions=STARTER_PROMPT + DEVELOPMENT_ARCHITECT_INCEPTION_AND_PLANNING,
    functions=[
        devops_functions.get_project_by_name,
        devops_functions.get_work_items_hierarchy,
        devops_functions.create_backlog_item,
        devops_functions.add_work_item_comment,
        devops_functions.assign_work_item_to_iteration,
        devops_functions.create_iteration,          
        devops_functions.set_work_item_priority,
        devops_functions.update_work_item,
        get_project_name,
        get_iteration,
        get_phase,
        set_project_name,
        set_iteration,
        set_phase,
        transfer_to_product_owner,
        transfer_to_product_owner_planning,
        transfer_to_product_owner_development
    ],
)

# triage_agent = Agent(
#     name="Triage Agent",
#     instructions=triage_instructions,
#     functions=[transfer_to_flight_modification, transfer_to_lost_baggage],
# )

# flight_modification = Agent(
#     name="Flight Modification Agent",
#     instructions="""You are a Flight Modification Agent for a customer service airlines company.
#       You are an expert customer service agent deciding which sub intent the user should be referred to.
# You already know the intent is for flight modification related question. First, look at message history and see if you can determine if the user wants to cancel or change their flight.
# Ask user clarifying questions until you know whether or not it is a cancel request or change flight request. Once you know, call the appropriate transfer function. Either ask clarifying questions, or call one of your functions, every time.""",
#     functions=[transfer_to_flight_cancel, transfer_to_flight_change],
#     parallel_tool_calls=False,
# )

# flight_cancel = Agent(
#     name="Flight cancel traversal",
#     instructions=STARTER_PROMPT + FLIGHT_CANCELLATION_POLICY,
#     functions=[
#         escalate_to_agent,
#         initiate_refund,
#         initiate_flight_credits,
#         transfer_to_triage,
#         case_resolved,
#     ],
# )

# flight_change = Agent(
#     name="Flight change traversal",
#     instructions=STARTER_PROMPT + FLIGHT_CHANGE_POLICY,
#     functions=[
#         escalate_to_agent,
#         change_flight,
#         valid_to_change_flight,
#         transfer_to_triage,
#         case_resolved,
#     ],
# )

# lost_baggage = Agent(
#     name="Lost baggage traversal",
#     instructions=STARTER_PROMPT + LOST_BAGGAGE_POLICY,
#     functions=[
#         escalate_to_agent,
#         initiate_baggage_search,
#         transfer_to_triage,
#         case_resolved,
#     ],
# )

import json

from swarm import Swarm


def process_and_print_streaming_response(response):
    content = ""
    last_sender = ""

    for chunk in response:
        if "sender" in chunk:
            last_sender = chunk["sender"]

        if "content" in chunk and chunk["content"] is not None:
            if not content and last_sender:
                print(f"\033[94m{last_sender}:\033[0m", end=" ", flush=True)
                last_sender = ""
            print(chunk["content"], end="", flush=True)
            content += chunk["content"]

        if "tool_calls" in chunk and chunk["tool_calls"] is not None:
            for tool_call in chunk["tool_calls"]:
                f = tool_call["function"]
                name = f["name"]
                if not name:
                    continue
                print(f"\033[94m{last_sender}: \033[95m{name}\033[0m()")

        if "delim" in chunk and chunk["delim"] == "end" and content:
            print()  # End of response message
            content = ""     

def pretty_print_messages(messages) -> None:
    for message in messages:
        if message["role"] != "assistant":
            continue

        # print agent name in blue
        print(f"\033[94m{message['sender']}\033[0m:", end=" ")

        # print response, if any
        if message["content"]:
            print(message["content"])

        # print tool calls in purple, if any
        tool_calls = message.get("tool_calls") or []
        if len(tool_calls) > 1:
            print()
        for tool_call in tool_calls:
            f = tool_call["function"]
            name, args = f["name"], f["arguments"]
            arg_str = json.dumps(json.loads(args)).replace(":", "=")
            print(f"\033[95m{name}\033[0m({arg_str[1:-1]})")
        
current_agent = None  
def run_demo_loop(
    starting_agent, context_variables=None, stream=False, debug=False
) -> None:
    client = Swarm()
    print("Starting Swarm CLI 🐝")

    messages = []
    agent = starting_agent
    current_agent = agent
    agent.context_variables = context_variables

    while True:
        user_input = input("Stakeholder Input: ")
        if user_input.lower() == "/exit":
            print("Exiting the loop. Goodbye!")
            break  # Exit the loop
        messages.append({"role": "user", "content": user_input})

        response = client.run(
            agent=agent,
            messages=messages,
            context_variables=context_variables or {},
            stream=stream,
            debug=debug,
        )

        if stream:
            response = process_and_print_streaming_response(response)
        else:
            pretty_print_messages(response.messages)

        messages.extend(response.messages)
        current_agent = response.agent
        agent = current_agent


        #total_tokens += response.usage.total_tokens
        # total_prompt_tokens += response.usage.prompt_tokens
        # completion_tokens += response.usage.completion_tokens

        # print(f"Total tokens used: {total_tokens}")
        # print(f"Total prompt tokens used: {total_prompt_tokens}")
        # print(f"Total completion tokens used: {completion_tokens}")

      
# total_tokens = 0
# total_prompt_tokens = 0
# completion_tokens = 0

context_variables = {
"phase": "Inception Phase",
"iteration": "",
"project name": "",
}

run_demo_loop(product_owner_inception, context_variables=context_variables, debug=False)        