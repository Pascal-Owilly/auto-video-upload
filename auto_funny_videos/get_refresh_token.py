from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Initialize the OAuth flow
flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)

# Use console-based authentication
credentials = flow.run_console()

# Save credentials to a file for later use
with open("token.pickle", "wb") as token_file:
    pickle.dump(credentials, token_file)

# Print the tokens
print("\n✅ Access Token:", credentials.token)
print("🔁 Refresh Token:", credentials.refresh_token)
