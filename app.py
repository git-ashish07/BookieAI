import streamlit as st
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Thread
import base64
import os

# File to store bookmarks
BOOKMARKS_FILE = 'bookmarks.json'

# Flask app to receive bookmarks from the extension
flask_app = Flask(__name__)
CORS(flask_app)  # Enable CORS for all routes

@flask_app.route('/bookmarks', methods=['POST'])
def receive_bookmarks():
    bookmarks = request.json
    with open(BOOKMARKS_FILE, 'w') as f:
        json.dump(bookmarks, f)
    print(f"Received {len(bookmarks)} bookmarks")  # Debug print
    return jsonify({"status": "success", "message": "Bookmarks received"})

def run_flask_app():
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, flask_app)  # Change port to 5000

# Start Flask app in a separate thread
Thread(target=run_flask_app, daemon=True).start()

def create_extension_zip(files):
    import io
    import zipfile
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name, file_content in files.items():
            zip_file.writestr(file_name, file_content)
    
    return zip_buffer.getvalue()

def get_metadata(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "N/A"
            description = soup.find('meta', attrs={'name': 'description'})
            description = description['content'] if description else "No description found"
            
            if title == "N/A" and description == "No description found":
                return {
                    'url': url,
                    'title': "N/A",
                    'description': "N/A",
                    'status': 'Active but no metadata',
                    'status_code': response.status_code
                }
            else:
                return {
                    'url': url,
                    'title': title,
                    'description': description,
                    'status': 'Active',
                    'status_code': response.status_code
                }
        else:
            return {
                'url': url,
                'title': "N/A",
                'description': "N/A",
                'status': 'Inactive',
                'status_code': response.status_code
            }
    except requests.RequestException as e:
        return {
            'url': url,
            'title': "N/A",
            'description': "N/A",
            'status': 'Dead',
            'status_code': str(e)
        }

def load_bookmarks():
    if os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, 'r') as f:
            return json.load(f)
    return []

def create_bookmark_button(result):
    color = {
        'Active': '#28a745',  # Green
        'Active but no metadata': '#ffa500',  # Orange
        'Inactive': '#ffa500',  # Orange (same as 'Active but no metadata')
        'Dead': '#dc3545'  # Red
    }.get(result['status'], '#6c757d')  # Default to gray

    # Use the URL if the title is "Metadata not accessible" or "N/A"
    display_text = result['url'] if result['title'] in ["Metadata not accessible", "N/A"] else result['title']

    return f"""
    <a href="{result['url']}" target="_blank" style="text-decoration: none;">
        <button style="
            background-color: {color};
            color: black;
            border: none;
            padding: 10px 15px;
            margin: 5px;
            border-radius: 5px;
            font-size: 14px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 200px;
        ">
            {display_text}
        </button>
    </a>
    """

def display_bookmark_buttons(results):
    buttons_html = "".join([create_bookmark_button(result) for result in results])
    st.markdown(f"""
    <div style="display: flex; flex-wrap: wrap; justify-content: flex-start;">
        {buttons_html}
    </div>
    """, unsafe_allow_html=True)

def main():
    st.title("Browser Bookmark Analyzer")

    if 'step' not in st.session_state:
        st.session_state.step = 'start'

    if st.session_state.step == 'start':
        if st.button("Extract Bookmarks"):
            st.session_state.step = 'extension_check'
            st.experimental_rerun()

    elif st.session_state.step == 'extension_check':
        st.write("Do you have the Bookmark Analyzer Extension installed?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, I have it installed"):
                st.session_state.step = 'wait_for_bookmarks'
                st.experimental_rerun()
        with col2:
            if st.button("No, I need to install it"):
                st.session_state.step = 'download_extension'
                st.experimental_rerun()

    elif st.session_state.step == 'download_extension':
        st.write("To continue, you need to install the Bookmark Analyzer Extension.")
        
        # Provide download link for the extension
        extension_files = {
            'manifest.json': open('Phase-1/bookmark-analyzer-extension/manifest.json', 'rb').read(),
            'background.js': open('Phase-1/bookmark-analyzer-extension/background.js', 'rb').read(),
        }
        extension_zip = create_extension_zip(extension_files)
        
        st.download_button(
            label="Download Extension",
            data=extension_zip,
            file_name="bookmark_analyzer_extension.zip",
            mime="application/zip",
            on_click=lambda: setattr(st.session_state, 'step', 'wait_for_bookmarks')
        )
        
        st.write("After downloading, follow these steps:")
        st.write("1. Unzip the downloaded file")
        st.write("2. Open Chrome and go to chrome://extensions/")
        st.write("3. Enable 'Developer mode' in the top right")
        st.write("4. Click 'Load unpacked' and select the unzipped folder")
        st.write("5. Click the extension icon in Chrome to send bookmarks")

    elif st.session_state.step == 'wait_for_bookmarks':
        st.write("Please click the extension icon in Chrome to send your bookmarks.")
        st.write("Waiting for bookmarks...")
        
        if st.button("I've sent the bookmarks"):
            st.session_state.step = 'check_bookmarks'
            st.experimental_rerun()

    elif st.session_state.step == 'check_bookmarks':
        bookmarks = load_bookmarks()
        if bookmarks:
            st.success(f"Found {len(bookmarks)} bookmarks. Ready to analyze!")
            st.session_state.step = 'analyze'
            st.experimental_rerun()
        else:
            st.error("No bookmarks received yet. Make sure you've clicked the extension icon.")
            if st.button("Try Again"):
                st.session_state.step = 'wait_for_bookmarks'
                st.experimental_rerun()

    elif st.session_state.step == 'analyze':
        bookmarks = load_bookmarks()
        st.success(f"Found {len(bookmarks)} bookmarks. Ready to analyze!")
        if st.button("Analyze Bookmarks"):
            with st.spinner("Analyzing bookmarks..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    results = list(executor.map(get_metadata, bookmarks))

            # Categorize results
            active_links = [r for r in results if r['status'] == 'Active']
            no_metadata_links = [r for r in results if r['status'] in ['Active but no metadata', 'Inactive']]
            dead_links = [r for r in results if r['status'] == 'Dead']

            # Display results by category
            st.subheader("Active Links with Metadata")
            display_bookmark_buttons(active_links)

            st.subheader("Active Links without Metadata")
            display_bookmark_buttons(no_metadata_links)

            st.subheader("Dead Links")
            display_bookmark_buttons(dead_links)

            # Display summary
            st.subheader("Summary")
            st.write(f"Total bookmarks: {len(bookmarks)}")
            st.write(f"Active links with metadata: {len(active_links)}")
            st.write(f"Active links without metadata: {len(no_metadata_links)}")
            st.write(f"Dead links: {len(dead_links)}")

if __name__ == "__main__":
    main()
