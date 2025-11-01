# This Flask server acts as a proxy to bypass CORS restrictions.
# IT HAS BEEN MODIFIED to support showing the CAPTCHA in the HTML client.

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import os
import io
import base64 # Import new modules

# --- CONFIGURATION ---
app = Flask(__name__)
# IMPORTANT: This allows your HTML file (running on a different port/origin) to talk to this server.
CORS(app) 
EBOARD_URL = "https://eboardresults.com"

# --- NEW: API ROUTE TO FETCH CAPTCHA ---
@app.route('/api/get-captcha', methods=['GET'])
def get_captcha():
    """
    Fetches a new CAPTCHA image and the session cookie.
    Sends the image as Base64 data and the cookie back to the client.
    """
    session = requests.Session()
    
    try:
        # 1. Fetch the dynamic CAPTCHA image
        captcha_url = f"{EBOARD_URL}/v2/captcha?t={int(time.time() * 1000)}"
        captcha_response = session.get(captcha_url, stream=True, timeout=10)
        
        if captcha_response.status_code != 200:
            return jsonify({"status": -1, "msg": "Failed to fetch CAPTCHA image."}), 502

        # 2. Convert image to Base64 string instead of saving to file
        image_bytes = io.BytesIO(captcha_response.content)
        image_b64 = base64.b64encode(image_bytes.read()).decode('utf-8')
        
        # 3. Get the session cookies
        session_cookies = session.cookies.get_dict()

        print(f"[PROXY] CAPTCHA and session cookie sent to client.")

        # 4. Return the image data and cookies to the client
        return jsonify({
            "status": 0,
            "msg": "CAPTCHA ready",
            "image_b64": image_b64,
            "cookies": session_cookies 
        })

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed during CAPTCHA fetch: {e}")
        return jsonify({"status": -1, "msg": f"Network error fetching CAPTCHA: {e}"}), 500

# --- MODIFIED: API PROXY ROUTE ---
@app.route('/api/get-result-proxy', methods=['POST'])
def get_result_proxy():
    # 1. Start a new session
    session = requests.Session()
    
    # 2. Get the full payload from the front-end client
    try:
        client_payload = request.get_json()
        if not client_payload:
            return jsonify({"status": -1, "msg": "No payload received from client."}), 400
            
        # 3. Extract the CAPTCHA solution and cookies sent from the client
        captcha_solution = client_payload.get('captcha')
        session_cookies = client_payload.get('cookies')

        if not captcha_solution or not session_cookies:
            return jsonify({"status": -1, "msg": "Payload missing CAPTCHA or cookie data."}), 400
            
        # 4. Apply the client's session cookies to our new session
        # This links this request to the CAPTCHA fetch
        session.cookies.update(session_cookies)

    except Exception as e:
        return jsonify({"status": -1, "msg": f"Invalid JSON payload from client: {e}"}), 400

    # 5. Inject the solved CAPTCHA and other required fields into the payload
    result_payload = {
        'board': client_payload.get('board'),
        'exam': client_payload.get('exam'),
        'year': client_payload.get('year'),
        'result_type': client_payload.get('result_type', '1'),
        'roll': client_payload.get('roll'),
        'reg': client_payload.get('reg'),
        'captcha': captcha_solution,
        'submit': 'View Result',
        'eiin': '',
        'dcode': '',
        'ccode': ''
    }

    # 6. Send the final POST request to the live Eboard API
    try:
        final_url = f"{EBOARD_URL}/v2/getres"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': f"{EBOARD_URL}/v2/home", 
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36'
        }
        
        eboard_response = session.post(
            final_url, 
            data=result_payload,
            headers=headers,
            timeout=30
        )

        # 7. Return the Eboard server's response
        if eboard_response.status_code == 200:
            return eboard_response.json()
        else:
            print(f"[ERROR] Eboard API request failed. Status: {eboard_response.status_code}")
            return jsonify({"status": -1, "msg": f"Eboard server rejected the request with status code {eboard_response.status_code}."}), 502

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Final POST request failed: {e}")
        return jsonify({"status": -1, "msg": f"Network error connecting to Eboard: {e}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=False)