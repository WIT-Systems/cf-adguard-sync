# cf-AdGuard-Sync

Synchronize Cloudflare DNS zones (including explicit subdomains and native wildcards) into a local `dnsmasq` instance for high-availability, offline-resilient homelabs.

## Features

* **Native Wildcard Support**: Seamlessly translates Cloudflare wildcards (`*.example.com`) into native `dnsmasq` address rules (`address=/domain/ip`), bypassing standard DNS rewrite limitations.
* **Explicit Record Priority**: Generates a clean explicit hosts file (`custom.hosts`) so specific subdomains take absolute precedence over wildcard catches.
* **WAN Resilience & Offline Persistence**: Connectivity-aware polling safely preserves existing local DNS state if Cloudflare or the WAN goes offline.
* **Complete Network Isolation**: Designed to run on an internal Docker network (`internal: true`) for secure, local-first reliability.
* **Automated CI/CD**: Built-in GitHub Actions workflow automatically compiles and pushes release images to `ghcr.io/WIT-Systems/cf-adguard-sync`.

---

## Getting Started

Add the container stack to your `compose.yaml`:

```yaml
services:
  dnsmasq:
    image: jpillora/dnsmasq
    container_name: local-dnsmasq
    restart: unless-stopped
    volumes:
      - cfads_dns_data:/data
    ports:
      - "5353:53/udp"
    command: --addn-hosts=/data/custom.hosts --conf-file=/data/wildcards.conf --log-queries

  cf-dns-sync:
    image: ghcr.io/wit-systems/cf-adguard-sync:latest
    build: .
    container_name: cf-dns-sync
    restart: unless-stopped
    volumes:
      - cfads_dns_data:/data
    environment:
      - CF_TOKEN=CFtokenhere
      - CF_ZONES=example.com
      - HOSTS_FILE=/data/custom.hosts
      - WILDCARD_CONF=/data/wildcards.conf
      - SYNC_INTERVAL=30

volumes:
  cfads_dns_data: