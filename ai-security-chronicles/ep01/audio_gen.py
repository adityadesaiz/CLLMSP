import os
import subprocess
import config

def generate_tts(text, file_id):
    if not text:
        return None

    out_path = os.path.join(config.AUDIO_DIR, f"voice_{file_id}.mp3")

    # Skip if already generated to save time on reruns
    if os.path.exists(out_path):
        return out_path

    print(f"Generating voice for segment: {file_id}...")

    # Using edge-tts CLI tool
    cmd = [
        "edge-tts",
        "--voice", config.TTS_VOICE,
        "--text", text,
        "--write-media", out_path
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        return out_path
    except subprocess.CalledProcessError as e:
        print(f"Error generating TTS for {file_id}: {e}")
        return None

def generate_all_audio(timeline):
    print("Starting audio narration generation...")
    for segment in timeline:
        if segment.get("audio_text"):
            generate_tts(segment["audio_text"], segment["id"])
    print("Audio generation complete.")
