# app.py
import os, uuid, random, subprocess, requests, shutil
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse

app = FastAPI()
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)
HF_API_KEY = os.getenv("HF_API_KEY", "")

MODEL_ENDPOINT = "https://api-inference.huggingface.co/models/openai/whisper-small"  # or whisper-base

def run_cmd(cmd):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:{proc.stdout}\nstderr:{proc.stderr}")
    return proc.stdout

@app.post("/process")
def process_video(payload: dict = Body(...)):
    youtube_url = payload.get("youtube_url")
    if not youtube_url:
        raise HTTPException(status_code=400, detail="youtube_url required in JSON body")

    uid = str(uuid.uuid4())
    video_path = os.path.join(OUTPUT_DIR, f"{uid}.%(ext)s")
    downloaded_path = os.path.join(OUTPUT_DIR, f"{uid}.mp4")
    clip_path = os.path.join(OUTPUT_DIR, f"{uid}_clip.mp4")
    srt_path = os.path.join(OUTPUT_DIR, f"{uid}.srt")

    try:
        # Download best mp4
        run_cmd(["yt-dlp", "-f", "best[ext=mp4]/best", "-o", video_path, youtube_url])

        # Find actual downloaded file (yt-dlp may add extension)
        # Move first matching file to uid.mp4 (simpler)
        found = None
        for name in os.listdir(OUTPUT_DIR):
            if name.startswith(uid) and name.endswith(".mp4"):
                found = os.path.join(OUTPUT_DIR, name)
                break
        if not found:
            # try any file starting with uid
            for name in os.listdir(OUTPUT_DIR):
                if name.startswith(uid):
                    found = os.path.join(OUTPUT_DIR, name)
                    break
        if not found:
            raise RuntimeError("Downloaded file not found")

        # Ensure consistent file name
        shutil.move(found, downloaded_path)

        # random start + duration (safety limits)
        start = random.randint(15, 120)
        duration = random.randint(30, 60)

        # Trim with ffmpeg (re-encode to ensure compatibility)
        run_cmd([
            "ffmpeg", "-y", "-ss", str(start), "-i", downloaded_path,
            "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", clip_path
        ])

        # Call Hugging Face inference API for transcription (file upload)
        with open(clip_path, "rb") as fh:
            resp = requests.post(MODEL_ENDPOINT, headers={"Authorization": f"Bearer {HF_API_KEY}"}, data=fh)
        text = ""
        if resp.status_code == 200:
            try:
                j = resp.json()
                # Many HF ASR endpoints return {"text":"..."}
                text = j.get("text") if isinstance(j, dict) else str(j)
            except Exception:
                text = resp.text
        else:
            text = f"Transcription error: {resp.status_code}"

        # write SRT (simple single-block SRT)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:10,000\n")
            f.write(text if text else "No transcription.")

        # Return direct download paths (Render will serve these on same host)
        # We will return the filenames; n8n will GET /download/{filename}
        return {
            "clip_filename": os.path.basename(clip_path),
            "srt_filename": os.path.basename(srt_path),
            "start_sec": start,
            "duration_sec": duration,
            "text": text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
def download_file(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename=filename)
