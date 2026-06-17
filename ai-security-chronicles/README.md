# AI Security Chronicles — Episode 1: "The Magic Words"
AI Security educational YouTube Short series based on the CLLMSP certification curriculum. Each episode tells a story about an AI security incident and teaches real concepts through narrative.

## Prerequisites
- Python 3.8+
- ffmpeg installed and on PATH
- Gemini API key (optional — placeholders used without)

## Setup
pip install -r requirements.txt
cp .env.example .env
Edit .env and add your GEMINI_API_KEY

## Usage
cd ep01
python generate_episode.py

The script will:
1. Download fonts if needed
2. Generate panel images via Imagen 3 (or placeholders)
3. Create audio narrations via Edge TTS
4. Create the video with Ken Burns effects and overlays
5. Output EP01_Short.mp4 to output/

## Replace Panel Images
To use custom images instead of AI-generated ones, place your own panel_1.png through panel_8.png in the panels/ directory. Script skips generation if all 8 exist.

## Episode List
- **Episode 1: "The Magic Words"** — Prompt Injection
- Episode 2: "The Invisible Ink" — coming soon
- Episode 3: "The Leaking Bucket" — coming soon
