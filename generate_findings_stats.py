import pandas as pd
import re
import ipaddress
import pygeoip
from collections import Counter

# ------------------- CONFIG -------------------
INPUT_FILE = "4625_normalised.csv"
GEO_DB_PATH = "GeoLiteCity.dat"

# ------------------- Setup --------------------
geoip_reader = pygeoip.GeoIP(GEO_DB_PATH)
ip_cache = {}

def extract_ip(text):
    match = re.search(r'\(([\d\.]+)\)', str(text))
    return match.group(1) if match else None

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
        if record and 'country_name' in record:
            result = {
                'latitude': record.get('latitude'),
                'longitude': record.get('longitude'),
                'country': record.get('country_name', 'Unknown'),
                'city': record.get('city', 'Unknown')
            }
            ip_cache[ip] = result
            return result
    except Exception:
        pass
    ip_cache[ip] = None
    return None

# ------------------- Load & Normalize -------------------
print("📂 Loading and normalizing...")
data = pd.read_csv(INPUT_FILE)
data['IP'] = data['RemoteHost'].apply(extract_ip)
data = data[data['IP'].notnull()]  # Filter out rows with no extractable IP

# ------------------- GeoIP Analysis -------------------
print("🌍 Performing GeoIP lookups...")
country_counter = Counter()

for ip in data['IP']:
    loc = get_ip_location(ip)
    if loc and loc['country']:
        country_counter[loc['country']] += 1

# ------------------- Results -------------------
total_attacks = sum(country_counter.values())
top_countries = country_counter.most_common(10)
top_total = sum([c for _, c in top_countries])
top_pct = (top_total / total_attacks) * 100

print("\n🔝 Top 10 Attacking Countries:")
print(f"{'Country':<20} {'Count':>10} {'Percent':>10}")
for country, count in top_countries:
    pct = (count / total_attacks) * 100
    print(f"{country:<20} {count:>10} {pct:>9.2f}%")

print(f"\n📊 Total attacks from top 10: {top_total:,} ({top_pct:.2f}%)")
print(f"📦 Total attacks (geolocated): {total_attacks:,}")
