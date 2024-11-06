import msal
import requests

# Azure application details
client_id = "9f138ff2-743e-4d5a-b1b2-735b85e4719b"
client_secret = "hQ28Q~Pef6zA8b15tE8OYivDCqCKVi1HKA7_Rc57"
tenant_id = "533a0585-fc92-4ed8-928a-ab91f453e3c7"

# OAuth2 authority and scopes
authority = f"https://login.microsoftonline.com/{tenant_id}"
scopes = ["https://graph.microsoft.com/.default"]

# Acquire access token
app = msal.ConfidentialClientApplication(
    client_id, authority=authority, client_credential=client_secret
)
token_response = app.acquire_token_for_client(scopes=scopes)

if "access_token" in token_response:
    print("Access token acquired successfully.")

    # Send email using Microsoft Graph API
    headers = {
        "Authorization": f"Bearer {token_response['access_token']}",
        "Content-Type": "application/json" 
    }

    email_data = {
        "message": {
            "subject": "Hello from Python!",
            "body": {"contentType": "Text", "content": "This is a test email sent using Microsoft Graph API."},
            "toRecipients": [
                {"emailAddress": {"address": "rene.vangeffen@live.nl"}}
            ]
        }
    }

    response = requests.post(
    "https://graph.microsoft.com/v1.0/users/admin@leeney-software.com/sendMail",
    headers=headers,
    json=email_data
)


    if response.status_code == 202:
        print("Email sent successfully!")
    else:
        print(f"Failed to send email: {response.status_code}, {response.text}")
else:
    print("Failed to acquire access token:", token_response.get("error_description"))
