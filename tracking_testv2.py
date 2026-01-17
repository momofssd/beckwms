import requests

USERID = "4242NTRADE281"

url = "https://secure.shippingapis.com/ShippingAPI.dll"

xml = f"""<TrackRequest USERID="{USERID}">
<TrackID ID="9400111899223856923456"/>
</TrackRequest>"""

params = {
    "API": "TrackV2",
    "XML": xml
}

r = requests.get(url, params=params)
print(r.text)
