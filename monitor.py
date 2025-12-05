import os
import requests
from tuya_connector import TuyaOpenAPI
from datetime import datetime
import pytz

# --- CONFIGURATION ---
ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET")
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

    if day == 0 or day == 6: return False # Mon/Sun
    if 1 <= day <= 3: return 7 <= hour < 19 # Tue-Thu
    if day == 4: return 7 <= hour < 20 # Fri
    if day == 5: return 7 <= hour < 21 # Sat

    return False

def send_alert(message):
    """Sends a push notification to your phone via ntfy.sh"""
    print(f"🚨 SENDING ALERT: {message}")
    # FIXED: Removed Emoji from 'Title' header to prevent Unicode Error
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
                  data=message.encode(encoding='utf-8'),
                  headers={"Title": "Ice Bath Alert", "Priority": "high"})

def get_device_status(openapi, device_id, name):
    """Fetches status for a single device and returns any issues found."""
    # We use the 'functions' endpoint sometimes if status is empty, but let's stick to status first
    response = openapi.get(f'/v1.0/devices/{device_id}/status')
    
    if not response.get('success'):
        return [f"{name}: Connection Error ❌"]

    flow_rate = 0.0
    water_temp = 0.0
    pump_status = "Unknown"

    print(f"--- Raw Data for {name} ---") # Debug print to help us see what we get
    for item in response['result']:
        val = item['value']
        code = item['code']
        
        # FLOW CHECK (Checking multiple potential names)
        if code in ['flow_water', '102', 'flow_rate']:
            flow_rate = val / 10.0
            print(f"   Found Flow ({code}): {flow_rate}")

        # TEMP CHECK (Checking multiple potential names)
        # We prefer temp_top_f (C), but will fall back to temp_current_f (F) if needed
        elif code in ['temp_top_f', '114']:
            water_temp = val / 10.0
            print(f"   Found Temp C ({code}): {water_temp}")
        elif code in ['temp_current_f', '29'] and water_temp == 0:
            # If we haven't found Celsius yet, use this and convert F to C
            # temp_current_f is usually raw F (e.g. 755 = 75.5F)
            f_temp = val / 10.0
            water_temp = (f_temp - 32) * 5/9
            print(f"   Found Temp F ({code}): {f_temp}F -> {water_temp:.1f}C")

        # PUMP CHECK
        elif code in ['sw_water', '125']:
            pump_status = "ON" if val else "OFF"

    print(f"   > Summary: Flow={flow_rate}L, Temp={water_temp:.1f}°C, Pump={pump_status}\n")

    issues = []
    # Alert Logic
    if flow_rate < MIN_FLOW:
        if flow_rate == 0:
            issues.append(f"{name}: No Flow (Pump Off?)")
        else:
            issues.append(f"{name}: Low Flow ({flow_rate}L)")
    
    if water_temp > MAX_TEMP and water_temp > 0: # Ensure we don't alert on 0.0 reading error
        issues.append(f"{name}: High Temp ({water_temp:.1f}°C)")

    return issues

def main():
    print("--- Starting Ice Bath Check ---")
    
    # Bypass time check for testing if you want, otherwise keep it:
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
