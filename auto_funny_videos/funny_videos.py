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
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy import *
import isodate

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

CLIENT_SECRET_FILE = 'client_secrets.json'
TOKEN_PICKLE_FILE = 'token.pickle'
PROCESSED_VIDEOS_LOG = 'processed_videos.json'
REGIONS = ["US", "IN", "GB", "CA", "FR", "DE", "AU", "JP", "KR"]
DEESEEK_API_KEY = 'sk-525b280b70bc4d4e8294beee9a391f85'


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
    youtube = build("youtube", "v3", credentials=creds)
    request = youtube.videos().list(part="snippet,contentDetails", chart="mostPopular", regionCode=region_code, maxResults=5)
    response = request.execute()

    trending_videos = []
    for item in response.get("items", []):
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
        print(f"✅ Already downloaded: {title}")
        return video_path

    ydl_opts = {
        'outtmpl': f'downloads/{sanitized_title}.%(ext)s',
        'format': 'best',
        # Remove the match filter to allow all videos
        'match_filter': None
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([video_url])
        except Exception as e:
            print(f"❌ Download failed for {title}: {e}")
            return None
    return get_downloaded_video_path(title)


def get_downloaded_video_path(title):
    sanitized_title = sanitize_filename(title)
    files = glob.glob(f"downloads/{sanitized_title}.*")
    return files[0] if files else None


def add_watermark(video_path, watermark_text="Viral Giggles"):
    try:
        clip = VideoFileClip(video_path)
        watermark = (TextClip(watermark_text, fontsize=24, color='white')
                     .set_position(("right", "bottom"))
                     .set_duration(clip.duration)
                     .margin(right=10, bottom=10, opacity=0))
        final = CompositeVideoClip([clip, watermark])
        output_path = video_path.replace(".mp4", "_watermarked.mp4")
        final.write_videofile(output_path, codec="libx264", audio_codec="aac")
        return output_path
    except Exception as e:
        print(f"❌ Error adding watermark: {e}")
        return video_path


def generate_title(api_key, context):
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "prompt": f"Generate a short, viral, funny video title based on this: {context}",
        "max_tokens": 20
    }
    try:
        response = requests.post("https://api.deepseek.com/generate", headers=headers, json=payload)
        return response.json().get("text", "Funny Viral Clip")
    except Exception as e:
        print(f"⚠️ Error generating title: {e}")
        return "Funny Viral Clip"


def upload_video(file_path, title, description, made_for_kids=None):
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    tags = list(set(["trending"] + title.lower().split() + description.lower().split()))
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "23"
        },
        "status": {"privacyStatus": "public"}
    }
    if made_for_kids is not None:
        body["status"]["madeForKids"] = made_for_kids

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(file_path, resumable=True)
        )
        response = request.execute()
        print(f"✅ Uploaded video: {title}\n📌 Response: {json.dumps(response, indent=4)}")
    except Exception as e:
        print(f"❌ Upload failed: {e}")


def log_processed_video(video_id):
    processed_videos = []
    if os.path.exists(PROCESSED_VIDEOS_LOG):
        with open(PROCESSED_VIDEOS_LOG, 'r') as f:
            processed_videos = json.load(f)
    if video_id not in processed_videos:
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
            print(f"⚠️ Skipping processed video: {title}")
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        video_path = download_video(video_url, title)
        if video_path:
            watermarked_path = add_watermark(video_path)
            generated_title = generate_title(DEESEEK_API_KEY, title)
            upload_video(watermarked_path, generated_title, title)
            log_processed_video(video_id)
            delete_video(video_path)
            delete_video(watermarked_path)
            print(f"🚀 Uploaded and cleaned up: {generated_title}")


def schedule_video_fetch():
    print("🔁 Running in continuous mode...")
    while True:
        region_code = random.choice(['US', 'GB', 'IN', 'CA', 'AU', 'ZA', 'NG', 'KE'])
        try:
            videos = get_trending_videos(region_code)
            if videos:
                for video_id, title, duration in videos:
                    if is_video_processed(video_id):
                        continue
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    video_path = download_video(video_url, title)
                    if video_path:
                        watermarked_path = add_watermark(video_path)
                        generated_title = generate_title(DEESEEK_API_KEY, title)
                        upload_video(watermarked_path, generated_title, title)
                        log_processed_video(video_id)
                        delete_video(video_path)
                        delete_video(watermarked_path)
                        print(f"🚀 Uploaded and cleaned up: {generated_title}")
                        time.sleep(5)
                        break

            else:
                print("No valid trending videos found.")
        except Exception as e:
            print(f"❌ Error: {e}")



if __name__ == "__main__":
    schedule_video_fetch()
