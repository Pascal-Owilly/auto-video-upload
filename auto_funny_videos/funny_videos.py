import os
import requests
import yt_dlp
import glob
import re
import random
import pickle
import json
import datetime
import time
from threading import Timer
from google.auth import exceptions
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import isodate

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

def get_trending_videos(region_code):
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return []

    youtube = build("youtube", "v3", credentials=creds)
    request = youtube.videos().list(part="snippet,contentDetails", chart="mostPopular", regionCode=region_code, maxResults=5)
    response = request.execute()

    trending_videos = []
    for item in response.get("items", []):
        if "contentDetails" in item:
            duration = item["contentDetails"].get("duration")
            if duration and parse_duration(duration) <= 180:
                trending_videos.append((item["id"], item["snippet"]["title"], duration))

    return trending_videos

def parse_duration(duration):
    return isodate.parse_duration(duration).total_seconds()

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

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

def get_downloaded_video_path(title):
    sanitized_title = sanitize_filename(title)
    files = glob.glob(f"downloads/{sanitized_title}.*")
    return files[0] if files else None

def upload_video(file_path, title, description, made_for_kids=None):
    creds = get_credentials()
    if not creds:
        print("❌ Failed to authenticate with Google.")
        return

    try:
        youtube = build("youtube", "v3", credentials=creds)
        tags = list(set(["trending"] + title.lower().split() + description.lower().split()))
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
    except Exception as e:
        print(f"❌ An error occurred while uploading video: {title}. Error: {str(e)}")

def log_processed_video(video_id):
    processed_videos = []
    if os.path.exists(PROCESSED_VIDEOS_LOG):
        with open(PROCESSED_VIDEOS_LOG, 'r') as f:
            processed_videos = json.load(f)
    
    processed_videos.append(video_id)
    with open(PROCESSED_VIDEOS_LOG, 'w') as f:
        json.dump(processed_videos, f)

def is_video_processed(video_id):
    if os.path.exists(PROCESSED_VIDEOS_LOG):
        with open(PROCESSED_VIDEOS_LOG, 'r') as f:
            return video_id in json.load(f)
    return False

def delete_video(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"🗑️ Deleted video: {file_path}")

def process_videos_for_time(time_of_day):
    region = random.choice(REGIONS)
    viral_videos = get_trending_videos(region)
    if not viral_videos:
        print(f"❌ No viral videos found for region {region}.")
        return

    for video_id, title, _ in viral_videos:
        if is_video_processed(video_id):
            print(f"❌ Video {title} already processed. Skipping.")
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"📌 Processing video: {title}")
        video_path = download_video(video_url, title)
        if video_path:
            upload_video(video_path, title, title)
            log_processed_video(video_id)
            delete_video(video_path)
            print(f"🚀 Successfully uploaded: {title}")

def schedule_video_fetch():
    times = ['07:00:00', '10:00:00', '14:10:00', '16:00:00', '19:00:00']
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    process_videos_for_time(current_time)
    print("⏳ Next video fetch scheduled.")
    for t in times:
        target_time = datetime.datetime.strptime(t, "%H:%M:%S").time()
        now = datetime.datetime.now().time()
        if target_time > now:
            delta = datetime.datetime.combine(datetime.date.today(), target_time) - datetime.datetime.now()
            Timer(delta.total_seconds(), schedule_video_fetch).start()

if __name__ == "__main__":
    schedule_video_fetch()

