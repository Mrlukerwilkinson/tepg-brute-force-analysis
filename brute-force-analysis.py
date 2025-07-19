import folium
import pandas as pd
import pygeoip
import matplotlib.pyplot as plt
import seaborn as sns
from folium.plugins import HeatMap
from datetime import datetime
from folium import Element
import os
import ipaddress
import re

# -------------------- CONFIG --------------------
INPUT_FILE = "<your-data-source>.csv"# Adjust path as needed
GEOIP_DB = 'GeoLiteCity.dat'
OUTPUT_MAP = 'visualizations/attack_map_final.html'
OUTPUT_HEATMAP = 'visualizations/time_heatmap.png'

os.makedirs('data', exist_ok=True)
os.makedirs('visualizations', exist_ok=True)
os.makedirs('IOCs', exist_ok=True)

TARGET_LAT, TARGET_LON = -33.8688, 151.2093  # Sydney

# -------------------- LOAD & CLEAN --------------------
data = pd.read_csv(INPUT_FILE)
data['TimeStamp'] = pd.to_datetime(data['TimeCreated'], errors='coerce')

def extract_ip(text):
    match = re.search(r'\(([\d\.]+)\)', str(text))
    return match.group(1) if match else None

def extract_hostname(text):
    match = re.search(r'^(.*?)\s*\(', str(text))
    return match.group(1).strip() if match and match.group(1).strip() != '-' else None

data['IP'] = data['RemoteHost'].apply(extract_ip)
data['RemoteHostName'] = data['RemoteHost'].apply(extract_hostname)
data = data[data['IP'].notnull() & data['TimeStamp'].notnull()]

# -------------------- GEOIP --------------------
geoip_reader = pygeoip.GeoIP(GEOIP_DB)
ip_cache = {}

def is_public_ip(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False

def get_ip_location(ip):
    if ip in ip_cache:
        return ip_cache[ip]
    if not is_public_ip(ip):
        ip_cache[ip] = None
        return None
    try:
        record = geoip_reader.record_by_addr(ip)
        if record:
            result = {
                'latitude': record['latitude'],
                'longitude': record['longitude'],
                'country': record.get('country_name', 'Unknown'),
                'city': record.get('city', 'Unknown')
            }
            ip_cache[ip] = result
            return result
    except Exception:
        pass
    ip_cache[ip] = None
    return None

# -------------------- BUILD MAP --------------------
attack_counts = {}
top_countries = {}
heat_data = []

# Aggregate per IP location
for _, row in data.iterrows():
    ip = row['IP']
    location = get_ip_location(ip)
    if location:
        lat, lon = location['latitude'], location['longitude']
        country = location['country']
        key = (lat, lon)
        if key not in attack_counts:
            attack_counts[key] = {'count': 0, 'country': country}
        attack_counts[key]['count'] += 1
        heat_data.append([lat, lon, 1])
        top_countries[country] = top_countries.get(country, 0) + 1

# Build base map
m = folium.Map(location=[10, 20], zoom_start=2.2, tiles="CartoDB positron")

# Added to make the haze better
HeatMap(
    heat_data,
    radius=25,           # Increases the size of each point
    blur=20,             # More blending between points
    min_opacity=0.3,     # Makes sparse areas still visible
    max_zoom=4,          # Aggressive fade at high zoom
    gradient={           # Custom gradient for better visual contrast
        0.2: 'blue',
        0.4: 'lime',
        0.6: 'orange',
        0.8: 'red',
        1.0: 'darkred'
    }
).add_to(m)

# Add target marker for the organization
folium.Marker(
    [TARGET_LAT, TARGET_LON],
    popup='Target Location (NSW, Australia)',
    icon=folium.Icon(color='red', icon='info-sign')
).add_to(m)

# Colored CircleMarkers per IP location, showing city + country total
for (lat, lon), info in attack_counts.items():
    count = info['count']
    country = info['country']
    city = info.get('city', 'Unknown')
    total_country_count = top_countries.get(country, 0)

    if count > 100:
        color = 'red'
    elif count >= 50:
        color = 'orange'
    else:
        color = 'green'

    popup_text = (
        f"<b>Country:</b> {country}<br>"
        f"<b>City:</b> {city}<br>"
        f"<b>Attacks from this city:</b> {count}<br>"
        f"<b>Total attacks from {country}:</b> {total_country_count}"
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=8,
        popup=folium.Popup(popup_text, max_width=250),
        color=color,
        fill=True,
        fill_color=color
    ).add_to(m)


# Legend
legend_html = """
<div style="
 position: fixed;
 bottom: 50px;
 left: 50px;
 width: 200px;
 background-color: white;
 border:2px solid grey;
 z-index:9999;
 font-size:14px;
 padding: 10px;
 box-shadow: 2px 2px 8px rgba(0,0,0,0.2);">
<b>Heatmap Legend</b><br>
<i style="background: #ff0000; width: 18px; height: 18px; float: left; opacity: 0.7;"></i>&nbsp; High Attacks (>100)<br>
<i style="background: #ffa500; width: 18px; height: 18px; float: left; opacity: 0.7;"></i>&nbsp; Moderate Attacks (50-100)<br>
<i style="background: #00ff00; width: 18px; height: 18px; float: left; opacity: 0.7;"></i>&nbsp; Low Attacks (<50)<br>
</div>
"""
m.get_root().html.add_child(Element(legend_html))

# Top 10 countries box
top_ten = sorted(top_countries.items(), key=lambda x: x[1], reverse=True)[:10]
top_ten_html = "<div style='position: fixed; bottom: 50px; right: 50px; width: 250px; background-color: white; border: 2px solid grey; z-index:9999; font-size:14px; padding: 10px; box-shadow: 2px 2px 8px rgba(0,0,0,0.2);'>"
top_ten_html += "<b>Top 10 Attack Countries</b><br>"
for country, count in top_ten:
    top_ten_html += f"{country}: {count} attacks<br>"
top_ten_html += "</div>"
m.get_root().html.add_child(Element(top_ten_html))

# Save map
m.save(OUTPUT_MAP)
print(f"✅ Final map saved to {OUTPUT_MAP}")

# -------------------- TIME HEATMAP --------------------
data['Hour'] = data['TimeStamp'].dt.hour
data['Weekday'] = data['TimeStamp'].dt.weekday
hourly_attacks = data.groupby(['Weekday', 'Hour']).size().unstack(fill_value=0)

plt.figure(figsize=(10, 6))
sns.heatmap(hourly_attacks, cmap="YlOrRd", annot=False)
plt.title("Attack Frequency by Day of Week and Hour")
plt.xlabel("Hour of Day")
plt.ylabel("Day of Week")
plt.xticks(ticks=range(0, 24), labels=range(0, 24))
plt.yticks(ticks=range(0, 7), labels=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
plt.tight_layout()
plt.savefig(OUTPUT_HEATMAP, dpi=300)
plt.close()
print(f"✅ Time heatmap saved to {OUTPUT_HEATMAP}")

# -------------------- EXPORT IOCs --------------------
data[['IP']].drop_duplicates().to_csv('IOCs/ips.txt', index=False, header=False)
data[['RemoteHostName']].dropna().drop_duplicates().to_csv('IOCs/hostnames.txt', index=False, header=False)
data[['PayloadData1']].dropna().drop_duplicates().to_csv('IOCs/usernames.txt', index=False, header=False)
print("✅ Exported IPs, hostnames, and usernames to /IOCs/")


# -------------------- SUMMARY STATS --------------------
start_time = data['TimeStamp'].min()
end_time = data['TimeStamp'].max()
duration = end_time - start_time

# Convert to days/hours
total_days = duration.days
total_hours = duration.seconds // 3600
total_minutes = (duration.seconds % 3600) // 60

unique_ips = data['IP'].nunique()
unique_usernames = data['PayloadData1'].nunique()
total_attempts = len(data)

# Unique countries observed
unique_countries = set([get_ip_location(ip)['country'] for ip in data['IP'].unique() if get_ip_location(ip)])

print("\n📊 Honeypot Observation Window:")
print(f"Start Time: {start_time}")
print(f"End Time:   {end_time}")
print(f"Duration:   {total_days} days, {total_hours} hours, {total_minutes} minutes")

print(f"\n🔢 Brute Force Summary:")
print(f"Unique usernames used: {unique_usernames}")
print(f"Total failed login attempts: {total_attempts}")
print(f"Unique attacking IPs: {unique_ips}")
print(f"Unique countries: {len(unique_countries)}")
