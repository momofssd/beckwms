import requests
import xml.etree.ElementTree as ET

USERID = "4242NTRADE281"
TRACKING_NUMBER = "9234690400829600412948"

url = "https://secure.shippingapis.com/ShippingAPI.dll"

xml_request = f"""
<TrackRequest USERID="{USERID}">
    <TrackID ID="{TRACKING_NUMBER}"></TrackID>
</TrackRequest>
""".strip()

params = {
    "API": "TrackV2",
    "XML": xml_request
}

response = requests.get(url, params=params)

print("Raw response:")
print(response.text)
