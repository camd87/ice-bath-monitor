import os
import requests
from tuya_connector import TuyaOpenAPI
from datetime import datetime
import pytz

# --- CONFIGURATION ---
# Load API keys from GitHub Secrets (Keep these secret!)
ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET")
API_ENDPOINT = "https://openapi.tuyaeu.com" 

# Your Notification Topic
NTFY_TOPIC = "escape_bathhouse_alerts" 

# LIST OF ICE BATHS
# We map a Friendly Name to the Device ID
DEVICES = {
    "Downstairs ⬇️": "bfc028169a340521dcuol5",
    "Upstairs ⬆️":   "bfce55e51b1d41fca6b0ns"
}

# --- THRESHOLDS ---
MIN_FLOW = 19.0  # L/min
MAX_TEMP = 12.0  # Degrees Celsius

def should_run_check():
    """Checks if we are within the business monitoring hours (Sydney Time)."""
    tz = pytz.timezone('Australia/Sydney')
    now = datetime.now(tz)
    day = now.weekday() # Mon=0, Tue=1 ... Sun=6
    hour = now.hour

    # Monday (0) or Sunday (6) -> No checks
    if day == 0 or day == 6:
        return False

    # Tue (1) - Thu (3): 7am - 7pm (19:00)
    if 1 <= day <= 3:
        return 7 <= hour < 19
    
    # Friday (4): 7am - 8pm (20:00)
    if day == 4:
        return 7 <= hour < 20

    # Saturday (5): 7am - 9pm (21:00)
    if day == 5:
        return 7 <= hour < 21

    return False

def send_alert(message):
    """Sends a push notification to your phone via ntfy.sh"""
    print(f"🚨 SENDING ALERT: {message}")
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
                  data=message.encode(encoding='utf-8'),
                  headers={"Title": "Ice Bath Alert 🧊", "Priority": "high"})

def get_device_status(openapi, device_id, name):
    """Fetches status for a single device and returns any issues found."""
    response = openapi.get(f'/v1.0/devices/{device_id}/status')
    
    if not response.get('success'):
        return [f"{name}: Connection Error ❌"]

    flow_rate = 0.0
    water_temp = 0.0
    pump_status = "Unknown"

    # Parse the specific data points
    for item in response['result']:
        if item['code'] == 'flow_water': 
            flow_rate = item['value'] / 10.0
        elif item['code'] == 'temp_top_f': 
            water_temp = item['value'] / 10.0
        elif item['code'] == 'sw_water':
            pump_status = "ON" if item['value'] else "OFF"

    print(f"   > {name}: Flow={flow_rate}L, Temp={water_temp}°C, Pump={pump_status}")

    # Check for issues
    issues = []
    
    # Rule 1: Flow is too low (and pump is actually supposed to be ON)
    # We assume if flow is 0, the pump might just be turned off manually.
    # If you want to be alerted even if pump is off, remove the 'and flow_rate > 0' check.
    if flow_rate < MIN_FLOW:
        if flow_rate == 0:
            issues.append(f"{name}: No Flow (Pump Off?)")
        else:
            issues.append(f"{name}: Low Flow ({flow_rate}L)")
    
    # Rule 2: Temp is too high
    if water_temp > MAX_TEMP:
        issues.append(f"{name}: High Temp ({water_temp}°C)")

    return issues

def main():
    print("--- Starting Ice Bath Check ---")
    
    if not should_run_check():
        print("💤 Outside monitoring hours. Skipping check.")
        return

    # 1. Connect to Tuya Cloud
    openapi = TuyaOpenAPI(API_ENDPOINT, ACCESS_ID, ACCESS_SECRET)
    if not openapi.connect():
        print("❌ Failed to connect to Tuya Cloud")
        return

    all_alerts = []

    # 2. Loop through both devices
    for name, device_id in DEVICES.items():
        device_issues = get_device_status(openapi, device_id, name)
        all_alerts.extend(device_issues)

    # 3. Send Notification if needed
    if all_alerts:
        # Join all alerts into one message
        full_msg = "\n".join(all_alerts)
        send_alert(full_msg)
    else:
        print("✅ All Systems Normal")

if __name__ == "__main__":
    main()
