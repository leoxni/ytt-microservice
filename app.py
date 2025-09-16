from fastapi import FastAPI, UploadFile
import subprocess, os, uuid, requests

app = FastAPI()

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HF_API_KEY = os.getenv("HF_API_KEY", "")

@app.post("/process")
def process_video(youtube_url: str, start: int = 0, duration: int = 30):
    """
    Download a YouTube video, cut a clip (default 30s), 
    and generate subtitles using HuggingFace Whisper.
    """
    file_id = str(uuid.uuid4())
    video_path = f"{OUTPUT_DIR}/{file_id}.mp4"
    clip_path = f"{OUTPUT_DIR}/{file_id}_clip.mp4"
    subs_path = f"{OUTPUT_DIR}/{file_id}.srt"

    # 1. Download video
    subprocess.run([
        "yt-dlp", "-f", "mp4", "-o", video_path, youtube_url
    ], check=True)

    # 2. Cut 30–60s clip
    subprocess.run([
        "ffmpeg", "-ss", str(start), "-t", str(duration),
        "-i", video_path, "-c", "copy", clip_path
    ], check=True)

    # 3. Transcribe with HuggingFace Whisper
    with open(clip_path, "rb") as f:
        resp = requests.post(
            "https://api-inference.huggingface.co/models/openai/whisper-base",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            data=f
        )
        try:
            text = resp.json()["text"]
        except:
            text = "Transcription failed."

    with open(subs_path, "w", encoding="utf-8") as f:
        f.write(text)

    return {
        "clip_url": f"/download/{file_id}_clip.mp4",
        "subs_url": f"/download/{file_id}.srt",
        "text": text
    }

@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        return {"error": "file not found"}
    return {"download": f"File available at {file_path}"}
