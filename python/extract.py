import sys
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from parser import parse_html
import time

def main():
    
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}))
        return
    
    url = payload.get("url")
    company = payload.get("company", "Unknown")
    period = payload.get("period", "Unknown")
    
    if not url:
        print(json.dumps({"error": "missing url"}))
        return
    
    # Configure Chrome with MAXIMUM stealth
    options = Options()
    
    # Run in headless mode
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Critical anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # (I had Edge browser) I took this user-agent from a real Edge browser for amazon
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0'
    options.add_argument(f'user-agent={user_agent}')
    
    # Additional stealth settings
    options.add_argument('--disable-web-security')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    
    # Preferences to appear more human
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        
        # Override navigator properties to hide automation
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = {
                    runtime: {}
                };
            '''
        })
        
        # Set realistic viewport
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': 1920,
            'height': 1080,
            'deviceScaleFactor': 1,
            'mobile': False
        })
        
        # Override User-Agent via CDP
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": user_agent,
            "platform": "Windows",
            "acceptLanguage": "en-US,en;q=0.9"
        })
        
        # Set page load timeout
        driver.set_page_load_timeout(45)
        
        # Navigate to page
        driver.get(url)
        
        # Wait for body to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            pass
        
        # Additional wait for dynamic content
        time.sleep(3)
        
        # Scroll page to trigger lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        # Get final HTML
        html = driver.page_source
        
        # Debug: Save HTML
        import os
        debug_dir = "debug_html"
        os.makedirs(debug_dir, exist_ok=True)
        filename = company.replace(" ", "_").replace(",", "").replace(".", "") + "_" + period + "_selenium.html"
        filepath = os.path.join(debug_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Validate we got real content
        if len(html) < 500:
            error_result = {
                "url": url,
                "company": company,
                "period": period,
                "error": f"Page returned minimal content ({len(html)} chars) - possible bot detection",
                "extraction_status": "failed",
                "debug_file": filepath
            }
            print(json.dumps(error_result))
            return
        
        # Parse HTML
        result = parse_html(html, url, company, period)
        result['debug_file'] = filepath
        result['html_length'] = len(html)
        
        print(json.dumps(result))
        
    except TimeoutException:
        error_result = {
            "url": url,
            "company": company,
            "period": period,
            "error": "Page load timeout",
            "extraction_status": "failed"
        }
        print(json.dumps(error_result))
        
    except Exception as e:
        error_result = {
            "url": url,
            "company": company,
            "period": period,
            "error": str(e),
            "extraction_status": "failed"
        }
        print(json.dumps(error_result))
        
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()