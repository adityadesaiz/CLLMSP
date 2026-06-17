import os
import requests
import config

def setup_environment():
    for d in [config.PANEL_DIR, config.FONT_DIR, config.OUTPUT_DIR, config.AUDIO_DIR]:
        os.makedirs(d, exist_ok=True)

    fonts = {
        "Roboto-Bold.ttf": "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf",
        "Roboto-Regular.ttf": "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf"
    }

    for fname, url in fonts.items():
        path = os.path.join(config.FONT_DIR, fname)
        if not os.path.exists(path):
            print(f"Downloading {fname}...")
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                with open(path, 'wb') as f:
                    f.write(r.content)
            except requests.exceptions.RequestException as e:
                print(f"Error downloading {fname}: {e}")

def print_validation_report():
    print("\n" + "="*51)
    print("VALIDATION REPORT".center(51))
    print("="*51)
    out_path = os.path.join(config.OUTPUT_DIR, config.OUTPUT_FILENAME)

    panels_exist = all(os.path.exists(os.path.join(config.PANEL_DIR, f"panel_{i}.png")) for i in range(1, 9))
    audio_exists = any(fname.endswith('.mp3') for fname in os.listdir(config.AUDIO_DIR)) if os.path.exists(config.AUDIO_DIR) else False
    video_exists = os.path.exists(out_path)

    print(f"[X] Environment Setup")
    print(f"[{'X' if panels_exist else ' '}] Panel Generation")
    print(f"[{'X' if audio_exists else ' '}] Audio Narration Generation")
    print(f"[{'X' if video_exists else ' '}] Video Rendering")
    if video_exists:
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"    -> Output size: {size_mb:.2f} MB")
    print("="*51)

if __name__ == "__main__":
    setup_environment()

    import image_gen
    import audio_gen
    import video_gen

    image_gen.generate_all_panels()
    audio_gen.generate_all_audio(video_gen.TIMELINE)
    video_gen.generate_video()

    print_validation_report()
