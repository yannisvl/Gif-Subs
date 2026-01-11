import streamlit as st
import webvtt
from sentence_transformers import SentenceTransformer, util
import os
import glob
import warnings
import yt_dlp
import subprocess
import sys

# 1. PAGE CONFIG
st.set_page_config(page_title="Video Search & GIF", page_icon="🎥", layout="wide")
warnings.filterwarnings("ignore")

# 2. LOAD AI
@st.cache_resource
def load_models():
    print("🤖 Loading AI Models...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    return model

@st.cache_resource
def load_index(_model):
    if not os.path.exists("subs"): return None, []
    
    vtt_files = glob.glob("subs/*.vtt")
    corpus_texts = []
    metadata = []
    
    print(f"📚 Indexing {len(vtt_files)} subtitle files...")
    for file_path in vtt_files:
        filename = os.path.basename(file_path)
        video_id = filename.split('.')[0] 
        try:
            for caption in webvtt.read(file_path):
                clean_text = caption.text.strip().replace('\n', ' ')
                if len(clean_text) < 3: continue 
                corpus_texts.append(clean_text)
                metadata.append({'text': clean_text, 'start': caption.start, 'video_id': video_id})
        except: continue
            
    if not corpus_texts: return None, []
    embeddings = _model.encode(corpus_texts, convert_to_tensor=True)
    return embeddings, metadata

# 3. GIF GENERATION FUNCTION (Direct FFmpeg + Font Fix)
def create_gif_snippet(video_id, start_seconds, text_caption):
    # Setup Paths
    if not os.path.exists("gifs"): os.makedirs("gifs")
    
    # Clean up old temp files
    for f in glob.glob(f"gifs/temp_{video_id}*"):
        try: os.remove(f)
        except: pass

    temp_video = f"gifs/temp_{video_id}.mp4"
    
    # Safe filename
    safe_text = "".join([c for c in text_caption if c.isalnum() or c==' ']).strip()[:20]
    output_gif = f"gifs/{video_id}_{int(start_seconds)}_{safe_text.replace(' ', '_')}.gif"
    
    if os.path.exists(output_gif): return output_gif

    # Download (Force MP4)
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        'outtmpl': f"gifs/temp_{video_id}.%(ext)s",
        'quiet': True,
        'download_ranges': lambda _, __: [{'start_time': start_seconds, 'end_time': start_seconds + 4}],
        'merge_output_format': 'mp4',
        'ffmpeg_location': r'.',
        'ignoreerrors': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        print(f"Download Error: {e}")
        return None

    if not os.path.exists(temp_video):
        return None

    # Convert to GIF with Greek Font Support
    safe_caption = text_caption.replace("'", "").replace(":", "")
    
    # Point to Windows Arial Font (Fixes the boxes!)
    font_path = "C\:/Windows/Fonts/arial.ttf"

    filters = (
        f"fps=12,scale=480:-1,"
        f"drawtext=fontfile='{font_path}':text='{safe_caption}':"
        f"fontcolor=white:fontsize=24:"
        f"box=1:boxcolor=black@0.5:boxborderw=5:"
        f"x=(w-text_w)/2:y=h-text_h-10,"
        f"split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    )

    cmd = [
        "ffmpeg", "-y", "-i", temp_video, "-vf", filters, output_gif
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(temp_video): os.remove(temp_video)
        return output_gif
    except Exception as e:
        print(f"Error: {e}")
        return None

# 4. MAIN APP
model = load_models()
embeddings, metadata = load_index(model)

st.title("🎥 AI Video Search")
st.markdown("Search for a moment. You can **edit the text** below before generating the GIF.")

query = st.text_input("🔎 Search Bar", placeholder="Type a concept...")

if query and embeddings is not None:
    query_embedding = model.encode(query, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, embeddings, top_k=10)
    
    st.write("### Results")
    
    for i, hit in enumerate(hits[0]):
        score = hit['score']
        if score < 0.25: continue
        
        data = metadata[hit['corpus_id']]
        h, m, s = data['start'].split(':')
        seconds = max(0, int(float(h) * 3600 + float(m) * 60 + float(s)) - 2)
        
        url = f"https://www.youtube.com/watch?v={data['video_id']}&t={seconds}s"
        
        # --- UI LAYOUT ---
        with st.container():
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            
            with col1:
                # NEW: Editable Text Input instead of static text
                # We use the found text as the default value.
                # NOTE: Streamlit widgets keep state by key. Using the loop index
                # can cause stale values when the result order changes on new searches.
                caption_key = f"caption_{hit['corpus_id']}"
                custom_caption = st.text_input(
                    label="Caption", 
                    value=data['text'], 
                    key=caption_key,
                    label_visibility="collapsed"
                )
                st.caption(f"Confidence: {int(score*100)}% | Time: {data['start']}")
                
                gif_place = st.empty()

            with col2:
                st.link_button("▶ Watch", url)
            
            with col3:
                if st.button("🎞️ GIF", key=f"gif_btn_{hit['corpus_id']}"):
                    with st.spinner("Creating..."):
                        # We pass 'custom_caption' (what you typed) instead of data['text']
                        gif_path = create_gif_snippet(data['video_id'], seconds, custom_caption)
                        
                        if gif_path:
                            gif_place.image(gif_path)
                        else:
                            st.error("Failed.")
                            
            st.divider()

elif embeddings is None:
    st.error("Please add files to 'subs/' folder.")