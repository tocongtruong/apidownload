from flask import Flask, jsonify, request, send_file
import os
import re
import gdown
import yt_dlp
import requests
import logging
import datetime
import threading
import time

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

DOWNLOAD_DIRECTORY = "/home/apidownload"
os.makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)

# --- EXTRACT FUNCTIONS ---

def extract_file_id(drive_link):
    if '/file/d/' in drive_link:
        return drive_link.split('/file/d/')[1].split('/')[0]
    elif 'id=' in drive_link:
        return drive_link.split('id=')[1].split('&')[0]
    return None

def extract_tiktok_id(url):
    patterns = [
        r'video/(\d+)',
        r'/v/(\w+)',
        r'tiktok\.com/\w+/video/(\d+)',
        r'vm\.tiktok\.com/(\w+)',
        r'vt\.tiktok\.com/(\w+)' 
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    try:
        if any(domain in url for domain in ['vm.tiktok.com', 'vt.tiktok.com']):
            response = requests.head(url, allow_redirects=True, timeout=5)
            if response.status_code == 200:
                final_url = response.url
                for pattern in patterns:
                    match = re.search(pattern, final_url)
                    if match:
                        return match.group(1)
    except Exception as e:
        app.logger.warning(f"Lỗi redirect TikTok: {e}")
    return None

def extract_facebook_id(url):
    patterns = [
        r'facebook\.com/reel/(\d+)',
        r'fb\.watch/([a-zA-Z0-9_-]+)',
        r'/reel/(\d+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_youtube_shorts_id(url):
    patterns = [
        r'youtube\.com/shorts/([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        r'[?&]v=([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_instagram_id(url):
    patterns = [
        r'instagram\.com/reel/([a-zA-Z0-9_-]+)',
        r'instagram\.com/p/([a-zA-Z0-9_-]+)',
        r'instagram\.com/tv/([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# --- API ROUTES ---

@app.route('/download', methods=['GET'])
def download_from_url():
    input_url = request.args.get('url')
    if not input_url:
        return jsonify({"success": False, "message": "Thiếu tham số url"}), 400

    try:
        # Google Drive
        if 'drive.google.com' in input_url:
            file_id = extract_file_id(input_url)
            if not file_id:
                return jsonify({"success": False, "message": "Không trích xuất được ID từ link Google Drive"}), 400

            output_path = os.path.join(DOWNLOAD_DIRECTORY, f"{file_id}.mp4")
            if not os.path.exists(output_path):
                download_url = f"https://drive.google.com/uc?id={file_id}&export=download"
                app.logger.info(f"Đang tải file từ: {download_url}")
                gdown.download(download_url, output_path, quiet=False)

            if not os.path.exists(output_path):
                raise FileNotFoundError("Tải file thất bại hoặc không tồn tại")

            file_url = f"{request.host_url.rstrip('/')}/get_file/{file_id}.mp4"
            return jsonify({
                "success": True,
                "message": "File đã được tải về thành công",
                "file_url": file_url
            }), 200

        # Nền tảng hỗ trợ yt-dlp
        supported = {
            'tiktok.com': extract_tiktok_id,
            'facebook.com': extract_facebook_id,
            'fb.watch': extract_facebook_id,
            'youtube.com': extract_youtube_shorts_id,
            'youtu.be': extract_youtube_shorts_id,
            'instagram.com': extract_instagram_id,
        }

        for domain, extract_func in supported.items():
            if domain in input_url:
                video_id = extract_func(input_url) or str(int(time.time()))
                output_path = os.path.join(DOWNLOAD_DIRECTORY, f"{video_id}.mp4")

                if not os.path.exists(output_path):
                    ydl_opts = {
                        'outtmpl': output_path,
                        'quiet': True,
                        #'format': 'mp4',
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'noplaylist': True,
                        'merge_output_format': 'mp4',
                        'nocheckcertificate': True,
                    }

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(input_url, download=True)
                        title = info.get('title', '') if info else ''
                        thumbnail = info.get('thumbnail', '') if info else ''

                if not os.path.exists(output_path):
                    raise FileNotFoundError("Tải video thất bại hoặc không tồn tại")

                file_url = f"{request.host_url.rstrip('/')}/get_file/{video_id}.mp4"
                return jsonify({
                    "success": True,
                    "message": title,
                    "file_url": file_url,
                    "thumbnail": thumbnail
                }), 200

        return jsonify({"success": False, "message": "Không hỗ trợ nền tảng này"}), 400

    except Exception as e:
        app.logger.error(f"Lỗi khi tải: {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi khi tải: {str(e)}"}), 500

@app.route('/get_file/<filename>', methods=['GET'])
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_DIRECTORY, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"success": False, "message": "File không tồn tại"}), 404

@app.route('/clean', methods=['GET'])
def clean_directory():
    try:
        file_count = 0
        for filename in os.listdir(DOWNLOAD_DIRECTORY):
            file_path = os.path.join(DOWNLOAD_DIRECTORY, filename)
            if os.path.isfile(file_path) and filename.endswith('.mp4'):
                os.unlink(file_path)
                file_count += 1
        return jsonify({
            "success": True,
            "message": f"Đã xóa {file_count} file .mp4 trong {DOWNLOAD_DIRECTORY}"
        }), 200
    except Exception as e:
        app.logger.error(f"Lỗi khi xóa file: {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi khi xóa file: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "message": "API đang hoạt động",
        "timestamp": str(datetime.datetime.now())
    })

# --- AUTO CLEANER ---

def auto_clean_every_3_hours():
    while True:
        try:
            file_count = 0
            for filename in os.listdir(DOWNLOAD_DIRECTORY):
                file_path = os.path.join(DOWNLOAD_DIRECTORY, filename)
                if os.path.isfile(file_path) and filename.endswith('.mp4'):
                    os.unlink(file_path)
                    file_count += 1
            app.logger.info(f"[TỰ ĐỘNG] Đã xoá {file_count} file .mp4 sau mỗi 6 giờ")
        except Exception as e:
            app.logger.error(f"Lỗi khi tự động xoá file: {str(e)}")
        time.sleep(6 * 3600)

if __name__ == "__main__":
    cleaner_thread = threading.Thread(target=auto_clean_every_3_hours, daemon=True)
    cleaner_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
