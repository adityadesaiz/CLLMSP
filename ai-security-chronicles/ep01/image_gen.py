import os
import time
import textwrap
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import config

try:
    from google import genai
    from google.genai import types
    HAS_GOOGLE_GENAI = True
except ImportError:
    HAS_GOOGLE_GENAI = False

PREFIX = "Semi-realistic digital illustration in graphic novel style. Consistent character: Priya Mehta, a 32-year-old Indian woman with short hair just past shoulders, wearing a dark navy blazer over a teal blouse, confident expression, warm skin tone, sharp eyes. Modern Indian fintech office setting. No text, no words, no letters, no captions anywhere in image. "

PANELS = {
    1: {"prompt": "Priya walking into a modern glass-walled fintech office building in Mumbai. Morning sunlight streaming through floor-to-ceiling windows. She carries a laptop bag and holds an ID access card. Building has a large blue N logo above the entrance. Other employees walking in background. Confident posture. Warm morning lighting.", "accent": config.TEAL},
    2: {"prompt": "Priya standing in a dark tech control room, looking at a large wall-mounted dashboard screen showing real-time call analytics — graphs, numbers showing 15000+ calls, green status indicators, audio waveforms. A male Indian colleague in business casual gestures proudly at the screen. Screens cast blue glow on their faces. Impressed but thoughtful expression on Priya.", "accent": config.TEAL},
    3: {"prompt": "Split composition. Left half: silhouette of a man in a dark room speaking into a phone, face partially lit by screen glow, mysterious and calculating expression. Right half: futuristic AI voice assistant interface with blue audio waveform actively processing speech, microphone icon glowing. Dark moody cinematic atmosphere. Tension and suspense feeling.", "accent": config.RED_ACCENT},
    4: {"prompt": "Close-up of a dark digital screen showing audio being transcribed to text in real-time. Most text lines are calm blue color, but several specific phrases glow in alarming red — visually standing out as dangerous. Audio waveform visualization in background. Dark interface with cybersecurity aesthetic. Ominous dangerous atmosphere.", "accent": config.RED_ACCENT},
    5: {"prompt": "Priya looking at her phone with a shocked horrified expression. Behind her, a large dashboard screen shows a red alert overlay — warning indicators flashing, loan approval notification visible. Red warning lights reflecting off her face. Office environment in background, late afternoon. Tense alarming atmosphere. She just received terrible news.", "accent": config.RED_ACCENT},
    6: {"prompt": "Priya sitting at a desk wearing over-ear headphones, intensely studying multiple computer screens showing audio waveforms, call transcripts, and AI decision logs. Dark office, late afternoon golden light from window. Screens casting blue glow on her concentrated face. Papers and notes scattered on desk. Coffee mug beside her. Detective investigating a crime scene atmosphere.", "accent": config.TEAL},
    7: {"prompt": "Abstract technical visualization: two streams of flowing light particles — one stream colored blue representing trusted system instructions, one stream colored red representing untrusted user input — both flowing into a single glowing neural network brain processor in the center. Inside the processor the colors mix completely becoming indistinguishable. The AI cannot tell them apart. Dark black background, cybersecurity data visualization aesthetic. Dramatic and educational.", "accent": config.RED_ACCENT},
    8: {"prompt": "Priya looking concerned and thoughtful, resting chin on hand. Behind her, a computer screen shows an email interface with one email open — the email has a subtle red glow at the bottom suggesting hidden content. Dark office, dramatic single-source lighting. She's processing what happened and worried about what comes next. Contemplative serious mood.", "accent": config.TEAL}
}

def create_placeholder(panel_num, data):
    img = Image.new('RGB', (1080, 1920), config.BG_DARK)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (1080, 40)], fill=data["accent"])

    try:
        font_large = ImageFont.truetype(os.path.join(config.FONT_DIR, "Roboto-Bold.ttf"), 120)
        font_small = ImageFont.truetype(os.path.join(config.FONT_DIR, "Roboto-Regular.ttf"), 50)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((540, 600), f"PANEL {panel_num}", font=font_large, fill=config.WHITE, anchor="mm")

    wrapped = textwrap.fill(data["prompt"], width=35)
    draw.multiline_text((540, 960), wrapped, font=font_small, fill=config.LIGHT_GRAY, anchor="ma", align="center", spacing=20)

    img.save(os.path.join(config.PANEL_DIR, f"panel_{panel_num}.png"))

def generate_all_panels():
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    api_key = os.getenv("GEMINI_API_KEY")

    client = genai.Client(api_key=api_key) if HAS_GOOGLE_GENAI and api_key else None

    if not client:
        print("No API key found. Using placeholder images. Set GEMINI_API_KEY in .env for AI-generated panels.")

    all_exist = all(os.path.exists(os.path.join(config.PANEL_DIR, f"panel_{i}.png")) for i in range(1, 9))
    if all_exist:
        print("All 8 panels already exist. Skipping image generation.")
        return

    for i in range(1, 9):
        path = os.path.join(config.PANEL_DIR, f"panel_{i}.png")
        if os.path.exists(path):
            continue

        print(f"Generating Panel {i}/8 via Imagen 3...")
        if client:
            success = False
            for attempt in range(2):
                try:
                    result = client.models.generate_images(
                        model=config.IMAGE_MODEL,
                        prompt=PREFIX + PANELS[i]["prompt"],
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                            aspect_ratio=config.IMAGE_ASPECT_RATIO,
                            output_mime_type="image/png"
                        )
                    )

                    # Imagen returns the raw bytes directly, saving a request call
                    with open(path, 'wb') as handler:
                        handler.write(result.generated_images[0].image.image_bytes)

                    success = True
                    time.sleep(2)  # Rate limit avoidance
                    break
                except Exception as e:
                    print(f"  Attempt {attempt+1} failed: {e}")
                    time.sleep(2)
            if not success:
                print(f"  Falling back to placeholder for Panel {i}")
                create_placeholder(i, PANELS[i])
        else:
            create_placeholder(i, PANELS[i])

    print("Image generation complete.")
