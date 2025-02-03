import os
import requests
import yt_dlp
import glob
import re
from google.auth import exceptions
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle
import json

# Define the scope and the API service
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",  # Upload videos
    "https://www.googleapis.com/auth/youtube.readonly"  # Read data (e.g., trending videos)
]

CLIENT_SECRET_FILE = 'client_secrets.json'  # Path to your OAuth client secrets JSON

# Path to save the token (for any caching or verification purposes)
TOKEN_PICKLE_FILE = 'token.pickle'

# Path to store the processed videos log (to avoid re-downloading/re-uploading)
PROCESSED_VIDEOS_LOG = 'processed_videos.json'

# Get credentials from the OAuth 2.0 flow
def get_credentials():
    creds = None
    # Check if the token.pickle file exists
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, start the OAuth flow to get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return creds

# Fetch trending videos with refreshed access token
def get_trending_videos():
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return []

    youtube = build("youtube", "v3", credentials=creds)
    request = youtube.videos().list(part="snippet", chart="mostPopular", regionCode="US", maxResults=3)
    response = request.execute()
    return [(item["id"], item["snippet"]["title"]) for item in response.get("items", [])]

# Sanitize filenames
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# Download video
def download_video(video_url, title):
    sanitized_title = sanitize_filename(title)
    os.makedirs("downloads", exist_ok=True)
    video_path = get_downloaded_video_path(title)
    if video_path:
        print(f"✅ Video already downloaded: {title}")
        return video_path
    ydl_opts = {'outtmpl': f'downloads/{sanitized_title}.%(ext)s', 'format': 'best'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    return get_downloaded_video_path(title)

# Get correct file path
def get_downloaded_video_path(title):
    sanitized_title = sanitize_filename(title)
    files = glob.glob(f"downloads/{sanitized_title}.*")  # Find any matching file
    return files[0] if files else None

# Upload video to YouTube
# Upload video to YouTube with dynamic and alternative tags, including the optional 'madeForKids' field
def upload_video(file_path, title, description, made_for_kids=None):
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return

    youtube = build("youtube", "v3", credentials=creds)

    # Generate alternative tags based on the title and description
    tags = ["trending"]  # Starting with "trending"
    
    # Add keywords from the title as alternative tags (simple example)
    title_keywords = title.lower().split()  # Split title into keywords
    for keyword in title_keywords:
        if keyword not in tags:  # Avoid duplicates
            tags.append(keyword)

    # Optionally, add some tags from the description too (you can refine this approach)
    description_keywords = description.lower().split()
    for keyword in description_keywords:
        if keyword not in tags:  # Avoid duplicates
            tags.append(keyword)

    # You can refine the tags further by filtering out irrelevant words

    # Request to upload video
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,  # Adding dynamic tags
            "categoryId": "23"
        },
        "status": {
            "privacyStatus": "public",
        }
    }

    # Only include 'madeForKids' if it is provided (not None)
    if made_for_kids is not None:
        body["status"]["madeForKids"] = made_for_kids

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(file_path, resumable=True)
    )
    request.execute()
    print(f"✅ Uploaded video: {title}")

# Log processed videos to avoid re-download/re-upload
def log_processed_video(video_id):
    if os.path.exists(PROCESSED_VIDEOS_LOG):
        with open(PROCESSED_VIDEOS_LOG, 'r') as f:
            processed_videos = json.load(f)
    else:
        processed_videos = []

    processed_videos.append(video_id)

    with open(PROCESSED_VIDEOS_LOG, 'w') as f:
        json.dump(processed_videos, f)

# Check if video has already been processed
def is_video_processed(video_id):
    if os.path.exists(PROCESSED_VIDEOS_LOG):
        with open(PROCESSED_VIDEOS_LOG, 'r') as f:
            processed_videos = json.load(f)
        return video_id in processed_videos
    return False

# Delete video file after upload
def delete_video(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"🗑️ Deleted video: {file_path}")

# Main Automation Workflow
if __name__ == "__main__":
    viral_videos = get_trending_videos()
    if viral_videos:
        for video_id, title in viral_videos:
            if is_video_processed(video_id):
                print(f"❌ Video {title} has already been processed. Skipping.")
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"📌 Processing video: {title}")

            # Step 1: Download the video
            video_path = download_video(video_url, title)
            if not video_path:
                continue  # Skip if download failed

            # Step 2: Upload the video
            upload_video(video_path, title, f"{title}")
            log_processed_video(video_id)  # Log the video as processed

            # Step 3: Delete the video after upload
            delete_video(video_path)

            print(f"🚀 Successfully uploaded: {title}")
    else:
        print("❌ No viral videos found.")

