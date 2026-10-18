import os
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cf-dns-sync")

CF_TOKEN = os.getenv("CF_TOKEN")
CF_ZONES = [z.strip() for z in os.getenv("CF_ZONES", "").split(",") if z.strip()]
HOSTS_FILE = os.getenv("HOSTS_FILE", "/data/custom.hosts")
WILDCARD_CONF = os.getenv("WILDCARD_CONF", "/data/wildcards.conf")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "60"))

os.makedirs(os.path.dirname(HOSTS_FILE), exist_ok=True)

def check_internet() -> bool:
    try:
        requests.get("https://api.cloudflare.com/cdn-cgi/trace", timeout=3)
        return True
    except Exception:
        return False

def resolve_zone_id(domain: str, headers: dict) -> str:
    url = f"https://api.cloudflare.com/client/v4/zones?name={domain}"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            result = resp.json().get("result", [])
            if result:
                return result[0].get("id")
    except Exception as e:
        logger.error(f"Error resolving domain {domain}: {e}")
    return None

def perform_sync():
    if not CF_TOKEN or not CF_ZONES:
        logger.error("CF_TOKEN or CF_ZONES environment variables are not set.")
        return

    if not check_internet():
        logger.info("WAN is offline. Keeping existing local DNS state.")
        return

    cf_headers = {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json",
    }

    hosts_lines = []
    wildcard_lines = []
    ip_lookup = {} # To resolve CNAME targets if needed

    try:
        records_cache = []
        for zone_input in CF_ZONES:
            zone_id = zone_input
            if len(zone_input) != 32:
                zone_id = resolve_zone_id(zone_input, cf_headers)
                if not zone_id:
                    continue

            url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?per_page=500"
            resp = requests.get(url, headers=cf_headers, timeout=10)
            if resp.status_code == 200:
                for record in resp.json().get("result", []):
                    if record.get("proxied", False):
                        continue
                    records_cache.append(record)
                    if record.get("type") == "A":
                        ip_lookup[record.get("name").lower()] = record.get("content")

        # Process cached records
        for record in records_cache:
            name = record.get("name").lower()
            rtype = record.get("type")
            content = record.get("content")

            # 1. Handle Wildcards (e.g. *.example.com)
            if "*" in name:
                # Extract root domain (e.g. example.com from *.example.com)
                base_domain = name.replace("*.", "")
                target_ip = content
                
                # If the wildcard points to a CNAME target instead of an IP, resolve it
                if rtype == "CNAME" and content.lower() in ip_lookup:
                    target_ip = ip_lookup[content.lower()]

                if target_ip:
                    # dnsmasq format: address=/example.com/10.1.1.10
                    wildcard_lines.append(f"address=/{base_domain}/{target_ip}\n")
                    logger.info(f"Mapped wildcard *.{base_domain} -> {target_ip}")

            # 2. Handle Explicit A Records
            elif rtype == "A":
                hosts_lines.append(f"{content} {name}\n")

        if not hosts_lines and not wildcard_lines:
            logger.warning("Fetched 0 valid records from Cloudflare. Skipping sync to protect local state.")
            return

        # Atomically write out files
        with open(HOSTS_FILE, "w") as f:
            f.writelines(hosts_lines)

        with open(WILDCARD_CONF, "w") as f:
            f.writelines(wildcard_lines)

        logger.info(f"Successfully synced {len(hosts_lines)} explicit records and {len(wildcard_lines)} wildcard rules.")

    except Exception as e:
        logger.error(f"Sync exception encountered: {e}. Preserving existing local DNS state.")

if __name__ == "__main__":
    logger.info("Starting Cloudflare to dnsmasq sync daemon...")
    while True:
        perform_sync()
        time.sleep(SYNC_INTERVAL)