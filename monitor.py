import os
import requests
from tuya_connector import TuyaOpenAPI
from datetime import datetime
import pytz

# --- CONFIGURATION ---
ACCESS_ID = os.environ.get("8scq7j7aav4ekjhsaecp")
ACCESS_SECRET = os.environ.get("16d1768eb85147e4b0823a963b613ecd")
API_ENDPOINT = "https://openapi.tuyaeu.com" 
NTFY_TOPIC = "escape_bathhouse_alerts" 

# LIST OF ICE BATHS
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
    day = now.weekday() 
    hour = now.hour

    # Monday (0) -> No checks (Closed)
    if day == 0: return False

    # Tuesday (1) to Thursday (3) AND Sunday (6): 7am - 7pm (19:00)
    if (1 <= day <= 3) or (day == 6):
        return 7 <= hour < 19
    
    # Friday (4): 7am - 8pm (20:00)
    if day == 4:
        return 7 <= hour < 20

    # Saturday (5): 7am - 9pm (21:00)
    if day == 5:
        return 7 <= hour < 21

    return False

def send_alert(message):
    """Sends a push notification via ntfy.sh"""
    print(f"🚨 SENDING ALERT: {message}")
    
    # FIXED: Removed Emoji from 'Title' to prevent UnicodeEncodeError
    # We kept the emoji in the 'Tags' header which is supported by ntfy
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
                  data=message.encode(encoding='utf-8'),
                  headers={
                      "Title": "Ice Bath Alert", 
                      "Priority": "high",
                      "Tags": "warning,ice_cube"
                  })

def get_device_status(openapi, device_id, name):
    """Fetches status using the v2.0 Shadow Endpoint (REQUIRED for Flow Rate)."""
    
    # We explicitly ask for flow_water (102), temp_current_f (29), and sw_water (105/125)
    url = f'/v2.0/cloud/thing/{device_id}/shadow/properties?codes=flow_water,temp_current_f,sw_water'
    
    response = openapi.get(url)
    
    if not response.get('success'):
        print(f"Error for {name}: {response.get('msg')}")
        return [f"{name}: Connection Error ❌"]

    flow_rate = 0.0
    water_temp = 0.0
    manual_switch = False
    
    # Safe parsing of the v2.0 structure
    properties = response.get('result', {}).get('properties', [])

    print(f"--- Raw Data for {name} ---") 
    for item in properties:
        val = item['value']
        code = item['code']
        
        if code == 'flow_water':
            flow_rate = val / 10.0
        elif code == 'temp_current_f':
            f_temp = val / 10.0
            water_temp = (f_temp - 32) * 5/9
        elif code == 'sw_water':
            manual_switch = bool(val)

    # Intelligent Pump Logic: If flow exists, pump is ON (even if switch says off)
    if flow_rate > 1.0:
        pump_display = "ON (Active Flow)"
    elif manual_switch:
        pump_display = "ON (Switch)"
    else:
        pump_display = "OFF"

    print(f"   > Summary: Flow={flow_rate}L, Temp={water_temp:.1f}°C, Pump={pump_display}\n")

    issues = []
    
    # RULE 1: LOW FLOW CHECK
    if flow_rate < MIN_FLOW:
        if flow_rate == 0:
            issues.append(f"{name}: No Flow (Pump Off?)")
        else:
            issues.append(f"{name}: Low Flow ({flow_rate}L)")
    
    # RULE 2: HIGH TEMP CHECK
    if water_temp > MAX_TEMP and water_temp > 0:
        issues.append(f"{name}: High Temp ({water_temp:.1f}°C)")

    return issues

def main():
    print("--- Starting Ice Bath Check ---")
    
    if not should_run_check():
        print("💤 Outside monitoring hours. Skipping check.")
        return

    openapi = TuyaOpenAPI(API_ENDPOINT, ACCESS_ID, ACCESS_SECRET)
    if not openapi.connect():
        print("❌ Failed to connect to Tuya Cloud")
        return

    all_alerts = []

    for name, device_id in DEVICES.items():
        device_issues = get_device_status(openapi, device_id, name)
        all_alerts.extend(device_issues)

    if all_alerts:
        full_msg = "\n".join(all_alerts)
        send_alert(full_msg)
    else:
        print("✅ All Systems Normal")

if __name__ == "__main__":
    main()
