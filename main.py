import os
import json
import tempfile
import requests
import librosa
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI

# Load .env file
load_dotenv()

# Init Firebase (from env if exists, otherwise from local file)
firebase_credentials_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")

if firebase_credentials_json:
    print("[INFO] Loading Firebase credentials from environment variable.")
    firebase_credentials_dict = json.loads(firebase_credentials_json)
    firebase_credentials_dict["private_key"] = firebase_credentials_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(firebase_credentials_dict)
else:
    print("[INFO] Loading Firebase credentials from local file.")
    cred = credentials.Certificate("firebase_config.json")

firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

def download_audio(url):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                for chunk in response.iter_content(chunk_size=1024):
                    tmp.write(chunk)
                return tmp.name
        else:
            print(f"[ERROR] Failed to download file: {url}")
            return None
    except Exception as e:
        print(f"[EXCEPTION] Error downloading file: {e}")
        return None

def calculate_bpm(file_path):
    try:
        y, sr = librosa.load(file_path)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return round(float(tempo), 2)
    except Exception as e:
        print(f"[EXCEPTION] Error in BPM calculation: {e}")
        return None

def process_missing_bpm():
    print("🔍 Scanning all songs without BPM...")
    songs = db.collection('songs').stream()

    total = 0
    success = 0
    failed = 0

    for doc in songs:
        data = doc.to_dict()
        audio_url = data.get('audioUrl')
        bpm = data.get('bpm')
        title = data.get('title', 'Unknown')

        if not audio_url:
            print(f"[WARNING] Skipping '{title}' - no audioUrl.")
            continue
        if bpm is not None:
            print(f"[INFO] Skipping '{title}' - BPM already exists.")
            continue

        total += 1
        print(f"\n🎵 Processing song: {title}")
        print(f"⬇️ Downloading: {audio_url}")
        file_path = download_audio(audio_url)
        if not file_path:
            print(f"[ERROR] Failed to download '{title}'.")
            failed += 1
            continue

        print(f"🎧 Calculating BPM for: {file_path}")
        bpm_result = calculate_bpm(file_path)
        os.remove(file_path)

        if bpm_result:
            print(f"✅ Calculated BPM = {bpm_result} for '{title}'")
            db.collection('songs').document(doc.id).update({'bpm': bpm_result})
            success += 1
        else:
            print(f"❌ Failed to calculate BPM for '{title}'")
            failed += 1

    print("\n📊 Done.")
    print(f"Total processed: {total}")
    print(f"✅ Success: {success}")
    print(f"❌ Failed: {failed}")

@app.on_event("startup")
async def startup_event():
    process_missing_bpm()
