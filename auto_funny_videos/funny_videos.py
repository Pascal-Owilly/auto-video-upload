import os
import requests
import yt_dlp
import glob
import re
import random
from google.auth import exceptions
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle
import json
import datetime
import time
from threading import Timer

# Define the scope and the API service
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",  # Upload videos
    "https://www.googleapis.com/auth/youtube.readonly"  # Read data (e.g., trending videos)
]

CLIENT_SECRET_FILE = 'client_secrets.json'  # Path to your OAuth client secrets JSON
TOKEN_PICKLE_FILE = 'token.pickle'  # Path to store the token
PROCESSED_VIDEOS_LOG = 'processed_videos.json'  # Log file to track processed videos

# List of regions to randomly choose from
REGIONS = ["US", "IN", "GB", "CA", "FR", "DE", "AU", "JP", "KR"]

# Get credentials from the OAuth 2.0 flow
def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return creds

# Fetch trending videos with refreshed access token from a random region
def get_trending_videos(region_code):
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return []

    youtube = build("youtube", "v3", credentials=creds)
    request = youtube.videos().list(part="snippet", chart="mostPopular", regionCode=region_code, maxResults=5)
    response = request.execute()

    # Filter videos that are <= 3 minutes
    trending_videos = [(item["id"], item["snippet"]["title"], item["snippet"]["duration"])
                       for item in response.get("items", [])
                       if "duration" in item["contentDetails"] and parse_duration(item["contentDetails"]["duration"]) <= 180]

    return trending_videos

# Helper function to convert ISO 8601 duration to seconds
def parse_duration(duration):
    import isodate
    return isodate.parse_duration(duration).total_seconds()

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
    files = glob.glob(f"downloads/{sanitized_title}.*")
    return files[0] if files else None

# Upload video to YouTube
def upload_video(file_path, title, description, made_for_kids=None):
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return

    youtube = build("youtube", "v3", credentials=creds)

    tags = ["trending"]
    title_keywords = title.lower().split()
    for keyword in title_keywords:
        if keyword not in tags:
            tags.append(keyword)

    description_keywords = description.lower().split()
    for keyword in description_keywords:
        if keyword not in tags:
            tags.append(keyword)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "23"
        },
        "status": {
            "privacyStatus": "public",
        }
    }

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
def process_videos_for_time(time_of_day):
    regions = random.sample(REGIONS, 1)
    for region in regions:
        viral_videos = get_trending_videos(region)
        if viral_videos:
            for video_id, title, _ in viral_videos:
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
            print(f"❌ No viral videos found for region {region}.")

# Scheduling
def schedule_video_fetch():
    times = ['07:00:00', '10:00:00', '14:10:00', '16:00:00', '19:00:00']  # Time slots
    current_time = datetime.datetime.now().strftime("%H:%M:%S")

    if current_time in times:
        process_videos_for_time(current_time)
    else:
        print(f"⏳ Next video fetch will be at one of the scheduled times.")
    
    # Set a timer to run the task every day at the same time
    for t in times:
        target_time = datetime.datetime.strptime(t, "%H:%M:%S")
        now = datetime.datetime.now()
        if target_time > now:
            delta = target_time - now
            Timer(delta.total_seconds(), schedule_video_fetch).start()

if __name__ == "__main__":
    schedule_video_fetch()

