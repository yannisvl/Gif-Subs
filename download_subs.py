import yt_dlp
import webvtt
from sentence_transformers import SentenceTransformer, util
import os
import glob
import warnings

warnings.filterwarnings("ignore")

# Add this import at the top
from faster_whisper import WhisperModel


class VideoSearchApp:
    def __init__(self):
        print("------------------------------------------------")
        print("🤖 Loading AI Models...")
        self.search_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("🚀 Loading Faster-Whisper (Small Model)...")
        self.transcribe_model = WhisperModel("small", device="cpu", compute_type="int8") 
        print("✅ System Ready.")
        print("------------------------------------------------")

    def process_url(self, url):
        """
        Scans a playlist or video URL.
        """
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'ignoreerrors': True,
            
            # --- FIREFOX CONFIGURATION ---
            'cookiesfrombrowser': ('firefox',),  # <--- THE FIX
            # 'cookiefile': 'cookies.txt',       # <--- REMOVED
        }

        print(f"🔍 Scanning URL...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                print(f"❌ Critical Error scanning URL: {e}")
                return

            if not info:
                print("❌ No information found.")
                return

            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                print(f"📂 Playlist found: {len(entries)} videos.")
                for i, entry in enumerate(entries):
                    print(f"\n--- Video {i+1}/{len(entries)} ---")
                    try:
                        self.download_or_generate_subs(entry['url'], entry['id'], entry.get('title'))
                    except Exception as e:
                        print(f"⚠️ SKIPPING VIDEO due to error: {e}")
                        continue
            else:
                self.download_or_generate_subs(info['original_url'], info['id'], info.get('title'))

    def download_or_generate_subs(self, video_url, video_id, title):
        # --- 1. CHECK IF FILE ALREADY EXISTS ---
        # Check for both standard VTT and Greek specific VTT
        expected_files = glob.glob(f"subs/{video_id}*.vtt")
        
        if expected_files:
            print(f"⏭️  Skipping '{title}': Subtitles already exist.")
            return  # <--- STOP HERE, DO NOTHING ELSE

        # --- If we are here, the file is missing. Proceed as normal. ---
        print(f"🎥 Processing: {title}")
        
        # 2. Try downloading existing Greek subs
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True, 
            'subtitleslangs': ['el'],
            'outtmpl': f'subs/{video_id}',
            'quiet': True,
            'ignoreerrors': True,
            'cookiesfrombrowser': ('firefox',),
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'ffmpeg_location': r'.', # Uses current folder
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 3. Verify File Existence
        found_files = glob.glob(f"subs/{video_id}*.vtt")
        
        if found_files:
            print(f"   ✅ Found YouTube subtitles.")
        else:
            print(f"   ⚠️ No subtitles found. Attempting AI Generation...")
            self.generate_subs_with_whisper(video_url, video_id)

    def generate_subs_with_whisper(self, video_url, video_id):
        # A. Download AUDIO
        audio_file = f"temp_{video_id}.mp3"
        ydl_audio_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"temp_{video_id}.%(ext)s",
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'quiet': True,
            'cookiesfrombrowser': ('firefox',),
            'ffmpeg_location': r'.',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_audio_opts) as ydl:
                ydl.download([video_url])
        except Exception as e:
            return

        if not os.path.exists(audio_file): return

        print("   🎙️ Transcribing (High Quality & Fast)...")
        
        # B. TRANSCRIBE with Faster-Whisper
        # It returns a generator, not a list, so we loop through it
        segments, info = self.transcribe_model.transcribe(
            audio_file, 
            language="el", 
            beam_size=5,
            initial_prompt="Αυτό είναι ένα βίντεο στα Ελληνικά." # Forces Greek grammar mode
        )

        # C. Save VTT
        vtt_path = f"subs/{video_id}.el.vtt"
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            
            for segment in segments:
                start = self.format_timestamp(segment.start)
                end = self.format_timestamp(segment.end)
                text = segment.text.strip()
                f.write(f"{start} --> {end}\n{text}\n\n")
        
        print(f"   ✅ AI Subtitles generated!")
        if os.path.exists(audio_file): os.remove(audio_file)

    def format_timestamp(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"

if __name__ == "__main__":
    app = VideoSearchApp()
    url = input("Enter YouTube URL: ")
    app.process_url(url)