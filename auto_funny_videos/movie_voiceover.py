import os
import requests
import yt_dlp
import glob
import re
import random
import pickle
import json
import datetime
from gtts import gTTS  # For generating the "like and subscribe" message
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
from google.auth.transport.requests import Request
from google.auth.oAuthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import isodate

# Define constants
MAX_VIDEO_LENGTH = 300  # Maximum video length in seconds (5 minutes)
CTA_DURATION = 5  # Duration for "Like and Subscribe" message
CLIENT_SECRET_FILE = 'client_secrets.json'  # Path to your OAuth client secrets JSON
TOKEN_PICKLE_FILE = 'token.pickle'  # Path to store the token
PROCESSED_VIDEOS_LOG = 'processed_videos.json'  # Log file to track processed videos
REGIONS = ["US", "IN", "GB", "CA", "FR", "DE", "AU", "JP", "KR"]

# Define scope for Google API
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",  # Upload videos
    "https://www.googleapis.com/auth/youtube.readonly"  # Read data (e.g., trending videos)
]

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
            if duration and parse_duration(duration) <= MAX_VIDEO_LENGTH:
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
        response = request.execute()
        print(f"✅ Uploaded video: {title}")
        print(f"📌 API Response: {json.dumps(response, indent=4)}")  # Print response
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

def create_like_and_subscribe_voiceover():
    message = "Thank you for watching! Don't forget to like and subscribe for more videos!"
    tts = gTTS(message, lang='en')
    tts.save("like_and_subscribe.mp3")
    return "like_and_subscribe.mp3"

def combine_movie_with_voiceover(movie_path, main_voiceover_path, output_path):
    movie_clip = VideoFileClip(movie_path)

    # Trim the movie if it's longer than the max duration
    if movie_clip.duration > MAX_VIDEO_LENGTH:
        print(f"❌ Movie is longer than 5 minutes. Trimming to {MAX_VIDEO_LENGTH} seconds.")
        movie_clip = movie_clip.subclip(0, MAX_VIDEO_LENGTH)  # Trim the movie to 5 minutes

    main_audio_clip = AudioFileClip(main_voiceover_path)

    # Ensure the main audio clip is not longer than the movie
    if main_audio_clip.duration > movie_clip.duration:
        print(f"❌ Main voiceover is longer than the movie. Trimming it.")
        main_audio_clip = main_audio_clip.subclip(0, movie_clip.duration)  # Trim the audio to match movie length

    # Create and add the "like and subscribe" voiceover for the last few seconds
    like_and_subscribe_path = create_like_and_subscribe_voiceover()
    subscribe_audio_clip = AudioFileClip(like_and_subscribe_path)

    # Trim the 'Like and Subscribe' voiceover to fit the last 5 seconds
    if subscribe_audio_clip.duration > CTA_DURATION:
        print(f"❌ 'Like and Subscribe' voiceover is too long. Trimming to {CTA_DURATION} seconds.")
        subscribe_audio_clip = subscribe_audio_clip.subclip(0, CTA_DURATION)  # Trim to 5 seconds

    # Trim the main audio to leave 5 seconds for the CTA
    main_audio_clip = main_audio_clip.subclip(0, movie_clip.duration - CTA_DURATION)

    # Combine the main audio with the CTA (Like and Subscribe)
    final_audio = concatenate_audioclips([main_audio_clip, subscribe_audio_clip])

    # Set the audio for the video clip
    final_video = movie_clip.set_audio(final_audio)

    # Write the final video
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
    print(f"✅ Video and voiceover combined successfully, saved as: {output_path}")

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

