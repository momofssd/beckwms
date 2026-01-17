import os
import requests
import json
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# --- Configuration ---
# Use https://apis.usps.com for Production
# Use https://apis-tem.usps.com for Testing/Sandbox
BASE_URL = "https://apis.usps.com"

CLIENT_ID = os.getenv("USPS_CONSUMER_KEY")
CLIENT_SECRET = os.getenv("USPS_CONSUMER_SECRET")
TRACKING_NUMBER = "9234690400829600412948"

def get_usps_token():
    """
    Step 1: Exchange credentials for a Bearer Token
    No scope parameter needed - it's determined by your API subscriptions
    """
    auth_url = f"{BASE_URL}/oauth2/v3/token"
    
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        # Scope is omitted - it's auto-assigned based on your subscribed APIs
    }
    
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    print("[*] Requesting access token...")
    response = requests.post(auth_url, data=payload, headers=headers)
    
    if response.status_code == 200:
        token_data = response.json()
        print("[+] Token acquired successfully!")
        print(f"[i] Scopes granted: {token_data.get('scope', 'N/A')}")
        print(f"[i] Expires in: {token_data.get('expires_in', 0)} seconds")
        return token_data.get("access_token")
    else:
        print(f"[-] Auth Failed ({response.status_code}): {response.text}")
        return None

def get_tracking_info(token, tracking_num):
    """
    Step 2: Get tracking details using the Bearer Token
    Tries multiple endpoint formats to ensure compatibility
    """
    clean_tracking = tracking_num.replace(" ", "")
    
    # USPS v3 API endpoint format
    track_url = f"{BASE_URL}/tracking/v3/tracking/{clean_tracking}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    print(f"\n[*] Fetching tracking info for: {clean_tracking}")
    print(f"[*] Endpoint: {track_url}")
    
    response = requests.get(track_url, headers=headers)
    
    print(f"[*] Response Status: {response.status_code}")
    
    if response.status_code == 200:
        print("[+] Tracking data retrieved successfully!")
    elif response.status_code == 401:
        print("[-] Authentication failed - check your API subscriptions")
        print("[!] You may need to subscribe to the Tracking API in your developer portal")
    elif response.status_code == 404:
        print("[-] Tracking number not found or endpoint incorrect")
    else:
        print(f"[!] Unexpected response: {response.status_code}")
    
    return response.json()

def display_tracking_data(data):
    """Step 3: Display tracking information in a readable format"""
    print("\n" + "="*60)
    print("TRACKING INFORMATION")
    print("="*60)
    
    if "error" in data:
        print("\n[-] ERROR:")
        print(f"Code: {data['error'].get('code')}")
        print(f"Message: {data['error'].get('message')}")
        if 'errors' in data['error']:
            for err in data['error']['errors']:
                print(f"\n  - {err.get('title')}: {err.get('detail')}")
                print(f"    Source: {err.get('source')}")
        print("\n[!] TROUBLESHOOTING:")
        print("1. Go to https://developer.usps.com")
        print("2. Click 'My Apps' -> Select your 'Tracking' app")
        print("3. Click 'Edit' button")
        print("4. Subscribe to 'Tracking API' or 'Package Tracking API v3'")
        print("5. Save and wait a few minutes for changes to propagate")
    else:
        print("\n[+] Full Response:")
        print(json.dumps(data, indent=2))
    
    print("="*60)

# --- Execution ---
if __name__ == "__main__":
    print("="*60)
    print("USPS TRACKING API - PACKAGE TRACKER")
    print("="*60)
    
    # Verify credentials are loaded
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[-] ERROR: Missing credentials!")
        print("Please ensure your .env file contains:")
        print("  USPS_CONSUMER_KEY=your_key_here")
        print("  USPS_CONSUMER_SECRET=your_secret_here")
        exit(1)
    
    # Step 1: Get access token
    access_token = get_usps_token()

    if access_token:
        # Step 2: Get tracking information
        tracking_data = get_tracking_info(access_token, TRACKING_NUMBER)
        
        # Step 3: Display results
        display_tracking_data(tracking_data)
    else:
        print("\n[-] Failed to obtain access token. Please check your credentials.")
        print("Verify in your .env file:")
        print(f"  USPS_CONSUMER_KEY: {'Set' if CLIENT_ID else 'MISSING'}")
        print(f"  USPS_CONSUMER_SECRET: {'Set' if CLIENT_SECRET else 'MISSING'}")