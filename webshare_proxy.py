import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

def get_webshare_proxy():
    """Fetch a working proxy from Webshare API"""
    api_token = os.getenv("WEBSHARE_API_TOKEN")
    
    if not api_token:
        print("⚠️ WEBSHARE_API_TOKEN not found in .env file")
        return None
    
    try:
        # Fetch proxy list from Webshare API
        url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=25"
        headers = {"Authorization": f"Token {api_token}"}
        
        print("Fetching proxies from Webshare...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        proxies = data.get("results", [])
        
        if not proxies:
            print("✗ No proxies available in your Webshare account")
            return None
        
        print(f"✓ Found {len(proxies)} proxies")
        
        # Test each proxy until we find a working one
        for proxy in proxies:
            proxy_address = proxy.get("proxy_address")
            proxy_port = proxy.get("port")
            username = proxy.get("username")
            password = proxy.get("password")
            
            if not all([proxy_address, proxy_port, username, password]):
                continue
            
            # Format proxy for Playwright
            proxy_config = {
                "server": f"http://{proxy_address}:{proxy_port}",
                "username": username,
                "password": password
            }
            
            # Test the proxy
            print(f"Testing proxy: {proxy_address}:{proxy_port}...")
            if test_proxy(proxy_config):
                print(f"✓ Proxy working: {proxy_address}:{proxy_port}")
                return proxy_config
            else:
                print(f"✗ Proxy failed: {proxy_address}:{proxy_port}")
        
        print("✗ No working proxies found")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching proxies from Webshare: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return None

def test_proxy(proxy_config):
    """Test if a proxy works by making a request to Turnitin"""
    try:
        # Test with a simple request to Turnitin
        proxies = {
            "http": f"http://{proxy_config['username']}:{proxy_config['password']}@{proxy_config['server'].replace('http://', '')}",
            "https": f"http://{proxy_config['username']}:{proxy_config['password']}@{proxy_config['server'].replace('http://', '')}"
        }
        
        response = requests.get(
            "https://www.turnitin.com/login_page.asp",
            proxies=proxies,
            timeout=15
        )
        
        # Check if we got a valid response (not blocked)
        if response.status_code == 200 and "ERROR" not in response.text[:200]:
            return True
        return False
        
    except Exception as e:
        return False

if __name__ == "__main__":
    # Test the proxy fetching
    proxy = get_webshare_proxy()
    if proxy:
        print(f"\n✅ Working proxy found!")
        print(f"Server: {proxy['server']}")
        print(f"Username: {proxy['username']}")
    else:
        print("\n❌ No working proxy found")
