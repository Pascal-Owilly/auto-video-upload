from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
credentials = flow.run_console()

print("\nAccess Token:", credentials.token)
print("\nRefresh Token:", credentials.refresh_token)
