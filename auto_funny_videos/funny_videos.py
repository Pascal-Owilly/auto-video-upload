import os
import requests
import yt_dlp
import ffmpeg
from openai import OpenAI
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.auth
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print(os.getenv("YOUTUBE_API_KEY"))
print(os.getenv("OPENAI_API_KEY"))

# Initialize OpenAI client after loading environment variables
client = OpenAI(api_key=OPENAI_API_KEY)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
VIDEO_DIR = "downloads/"

# Step 1: Fetch Viral Videos (Fetching 3 trending videos)
def get_trending_videos():
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=3&q=funny videos&type=video&videoCategoryId=23&chart=mostPopular&key={YOUTUBE_API_KEY}"
    response = requests.get(url).json()
    return [(item["id"]["videoId"], item["snippet"]["title"]) for item in response.get("items", [])]

# Step 2: Download Video
def download_video(video_url):
    os.makedirs(VIDEO_DIR, exist_ok=True)
    ydl_opts = {'outtmpl': f'{VIDEO_DIR}%(title)s.%(ext)s', 'format': 'best'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

# Step 3: Edit Video
def edit_video(input_file, output_file="edited_video.mp4"):
    (
        ffmpeg.input(input_file)
        .trim(start=5, end=60)
        .output(output_file)
        .run()
    )

# Step 4: Generate AI Title & Description
def generate_title_description(video_title):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": f"Generate a catchy YouTube title and description for a funny video titled: {video_title}"}]
    )
    return response.choices[0].message.content

# Step 5: Upload to YouTube
def upload_video(file_path, title, description):
    creds, _ = google.auth.default(scopes=SCOPES)
    youtube = build("youtube", "v3", credentials=creds)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description, "tags": ["funny", "viral", "meme"], "categoryId": "23"},
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(file_path, resumable=True)
    )
    request.execute()

# Main Automation Workflow (Process 3 Videos)
if __name__ == "__main__":
    viral_videos = get_trending_videos()
    for video_id, title in viral_videos:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"Processing video: {title}")

        # Step 1: Download the video
        download_video(video_url)

        # Step 2: Edit the video (trim, etc.)
        edited_file = "edited_video.mp4"
        edit_video(f"{VIDEO_DIR}{title}.mp4", edited_file)

        # Step 3: Generate AI title and description
        ai_generated_text = generate_title_description(title)
        title, description = ai_generated_text.split('\n', 1)

        # Step 4: Upload the edited video
        upload_video(edited_file, title, description)
        print(f"Uploaded video: {title}")

