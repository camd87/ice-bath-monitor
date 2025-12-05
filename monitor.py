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
    """Sends a push notification via ntfy.sh"""
    print(f"🚨 SENDING ALERT: {message}")
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
                  data=message.encode(encoding='utf-8'),
                  headers={"Title": "Ice Bath Alert", "Priority": "high"})

def get_device_status(openapi, device_id, name):
    """Fetches status using the v2.0 Shadow Endpoint to find hidden Flow Rate."""
    
    # UPDATED: We use the v2.0 'Shadow' endpoint which you proved works
    # We explicitly ask for the specific codes: flow_water, temp_current_f, and sw_water
    url = f'/v2.0/cloud/thing/{device_id}/shadow/properties?codes=flow_water,temp_current_f,sw_water'
    
    response = openapi.get(url)
    
    if not response.get('success'):
        print(f"Error for {name}: {response.get('msg')}")
        return [f"{name}: Connection Error ❌"]

    flow_rate = 0.0
    water_temp = 0.0
    pump_status = "Unknown"

    # The v2.0 structure is slightly deeper: result -> properties
    # We use .get() to avoid crashing if 'properties' is missing
    properties = response.get('result', {}).get('properties', [])

    print(f"--- Raw Data for {name} ---") 
    for item in properties:
        val = item['value']
        code = item['code']
        
        # FLOW CHECK
        if code == 'flow_water':
            flow_rate = val / 10.0
            print(f"   Found Flow: {flow_rate}")

        # TEMP CHECK (Using the F value since that is what v2.0 returns)
        elif code == 'temp_current_f':
            f_temp = val / 10.0
            # Convert F to C
            water_temp = (f_temp - 32) * 5/9
            print(f"   Found Temp: {f_temp}F -> {water_temp:.1f}C")

        # PUMP CHECK
        elif code == 'sw_water':
            pump_status = "ON" if val else "OFF"
            print(f"   Found Pump: {pump_status}")

    print(f"   > Summary: Flow={flow_rate}L, Temp={water_temp:.1f}°C, Pump={pump_status}\n")

    issues = []
    
    # RULE 1: LOW FLOW
    if flow_rate < MIN_FLOW:
        # If flow is 0, we check if the pump is ON. If pump is OFF, maybe ignore?
        # For now, we report "Pump Off?" if flow is 0
        if flow_rate == 0:
            issues.append(f"{name}: No Flow (Pump Off?)")
        else:
            issues.append(f"{name}: Low Flow ({flow_rate}L)")
    
    # RULE 2: HIGH TEMP
    # We only alert if temp > 0 to avoid false alerts on read errors
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
