#!/usr/bin/env python3

SKIP_TIMING = False          
MANUAL_FIRE_HOUR = 19        
MANUAL_FIRE_MIN = 37         
MANUAL_FIRE_SEC = 0          

OFFSET_MS = 120              
BURST_INTERVAL_MS = 50       
BURST_COUNT = 10             

DEBUG = True                 
SHOW_COUNTDOWN = True        
COUNTDOWN_REFRESH_MS = 100   
SHOW_DRIFT = True            

import subprocess
import sys
import os
import time
import json
import hashlib
import random
import linecache
import signal
import ctypes

from datetime import datetime, timezone, timedelta

import ntplib
import pytz
import urllib3

from colorama import init, Fore, Style

if os.name == "nt":
    ctypes.windll.winmm.timeBeginPeriod(1)

def install(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", pkg]
    )

for p in ("ntplib", "pytz", "urllib3", "colorama"):
    try:
        __import__(p)
    except:
        install(p)

init(autoreset=True)  

G = Fore.GREEN
Y = Fore.YELLOW
R = Fore.RED
B = Fore.BLUE
C = Fore.CYAN
GB = Style.BRIGHT + Fore.GREEN

TZ_BEIJING = pytz.timezone("Asia/Shanghai")

def clear():
    os.system("cls" if os.name == "nt" else "clear")

clear()

def log_info(msg):  print(f"{B}[INFO]{Fore.RESET} {msg}")
def log_ok(msg):    print(f"{G}[OK]{Fore.RESET} {msg}")
def log_warn(msg):  print(f"{Y}[WARN]{Fore.RESET} {msg}")
def log_err(msg):   print(f"{R}[ERR]{Fore.RESET} {msg}")
def log_debug(msg):
    if DEBUG:       print(f"{C}[DEBUG]{Fore.RESET} {msg}")

def signal_handler(sig, frame):
    print(f'\n{R}[!] Interrupted - Clean exit')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def now_beijing():
    return datetime.now(timezone.utc).astimezone(TZ_BEIJING)

def show_beijing_time(prefix="[BEIJING]"):
    bt = now_beijing()
    print(
        f"{B}{prefix} "
        f"{bt.strftime('%H:%M:%S.%f')[:-3]}"
        f"{Fore.RESET}"
    )

show_beijing_time()

slot = int(input(f'{G}[Slot 1-4]: '))

token_num = (
    1 if slot in (1, 3)
    else 2 if slot in (2, 4)
    else None
)

if not token_num:
    log_err("Invalid slot selection")
    sys.exit(1)

clear()
show_beijing_time()
print(f'{GB}Token Assignment #{token_num}')

token = linecache.getline(
    "token.txt",
    token_num
).strip()

if not token:
    log_err("Target slot credential array is blank or file is missing")
    sys.exit(1)

URL_STATUS = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
URL_APPLY = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"

UA = "okhttp/4.12.0"  

NTP_SERVERS = [
    "ntp0.ntp-servers.net",
    "ntp1.ntp-servers.net",
    "ntp2.ntp-servers.net"
]

def gen_device_id():
    return hashlib.sha1(
        f"{random.random()}-{time.time()}".encode()
    ).hexdigest().upper()

def format_remaining(seconds):
    if seconds < 0:
        seconds = 0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hrs:02}:{mins:02}:{secs:02}.{ms:03}"

def get_ntp_beijing():
    client = ntplib.NTPClient()

    for server in NTP_SERVERS:
        try:
            start = time.perf_counter()
            r = client.request(server, version=3, timeout=3)
            latency = (time.perf_counter() - start) * 1000

            bt = datetime.fromtimestamp(
                r.tx_time,
                timezone.utc
            ).astimezone(TZ_BEIJING)

            log_ok(f"NTP sync from {server} ({latency:.2f}ms)")
            log_debug(f"NTP offset={r.offset * 1000:.2f}ms | delay={r.delay * 1000:.2f}ms")
            print(f"{G}[NTP] {bt.strftime('%H:%M:%S.%f')[:-3]}{Fore.RESET}")
            return bt

        except Exception as e:
            log_warn(f"NTP sync failure: {server} ({e})")

    bt = now_beijing()
    log_warn("Falling back to local OS system clock authority")
    print(f"{Y}[SYS] {bt.strftime('%H:%M:%S.%f')[:-3]}{Fore.RESET}")
    return bt

def synced_time(start_bt, start_perf):
    elapsed = (time.perf_counter() - start_perf)
    return start_bt + timedelta(seconds=elapsed)

def get_target(start_bt):
    if SKIP_TIMING:
        target = start_bt.replace(
            hour=MANUAL_FIRE_HOUR,
            minute=MANUAL_FIRE_MIN,
            second=MANUAL_FIRE_SEC,
            microsecond=0
        )
        log_warn(f"Manual override scheduler set: {target.strftime('%H:%M:%S Beijing')}")
        return target

    target = (start_bt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    log_warn(f"Auto-midnight baseline computed: {target.strftime('%Y-%m-%d %H:%M:%S Beijing')}")
    return target

def wait_target(start_bt, start_perf, target):
    log_info("Waiting for target window initialization...")
    last_print = 0

    while True:
        now = synced_time(start_bt, start_perf)
        diff = (target - now).total_seconds()

        if SHOW_COUNTDOWN:
            current = time.perf_counter()
            if current - last_print >= (COUNTDOWN_REFRESH_MS / 1000):
                real_bt = now_beijing()
                drift = (real_bt - now).total_seconds() * 1000
                line = f"\r{Y}T-minus: {format_remaining(diff)} "
                if SHOW_DRIFT:
                    line += f"| Drift: {drift:+.2f}ms "
                print(line, end="", flush=True)
                last_print = current

        if diff <= 0:  
            break

        if diff > 1:        time.sleep(0.25)     
        elif diff > 0.1:    time.sleep(0.01)     
        elif diff > 0.01:   time.sleep(0.001)    
        else:               time.sleep(0.0001)   

    print()
    log_ok("Target threshold cleared.")

class Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=10,                      
            retries=urllib3.Retry(           
                total=1, backoff_factor=0
            ),
            timeout=urllib3.Timeout(         
                connect=2.0, read=5.0
            )
        )

    def request(self, method, url, headers=None, body=None):
        try:
            h = headers or {}
            if method == 'POST':
                body = body or b'{"is_retry":true}'
                h.update({
                    'Content-Type': 'application/json',
                    'Content-Length': str(len(body)),
                    'User-Agent': UA,
                    'Connection': 'keep-alive', 
                    'Accept-Encoding': 'gzip'
                })

            return self.http.request(
                method, url, headers=h, body=body,
                preload_content=False  
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log_err(f"HTTP Socket exception caught: {e}")
            return None

def check_status(session, token, device_id):
    h = {
        "Cookie": f"new_bbs_serviceToken={token}; versionCode=500411; versionName=5.4.11; deviceId={device_id};"
    }
    start = time.perf_counter()
    r = session.request('GET', URL_STATUS, headers=h)
    latency = (time.perf_counter() - start) * 1000

    if not r:
        return False

    try:
        raw = r.data.decode('utf-8')
        data = json.loads(raw)

        try:    r.close()
        except: r.release_conn()

        log_debug(f"Status validation latency: {latency:.2f}ms")
        log_debug(f"Status payload: {raw}")

        if data.get("code") == 100004:
            log_err("Authentication token is expired or structurally invalid.")
            sys.exit(1)

        info = data.get("data", {})
        is_pass = info.get("is_pass")
        button = info.get("button_state")

        print(f'{G}[Status Verification]: ', end='')

        if is_pass == 4 and button == 1:
            print(f'{GB}READY FOR BURST APPLICATION INTERFACE')
            return True
        elif is_pass == 1:
            print(f'{GB}System Account is already approved!')
            sys.exit(0)
        else:
            print(f'{R}Verification rejected. Criteria unmet or window closed (Code states: Pass={is_pass} | Btn={button})')
            sys.exit(1)

    except Exception as e:
        log_err(f"Status decoder error: {e}")
        return False

def fire(session, token, device_id):
    h = {
        "Cookie": f"new_bbs_serviceToken={token}; versionCode=500411; versionName=5.4.11; deviceId={device_id};"
    }
    try:
        start = time.perf_counter()
        r = session.request("POST", URL_APPLY, headers=h)
        latency = (time.perf_counter() - start) * 1000

        if not r:
            log_err(f"Network transport pipeline lost drop state ({latency:.2f}ms)")
            return None

        raw = r.data.decode('utf-8')
        data = json.loads(raw)

        try:    r.close()
        except: r.release_conn()

        log_debug(f"HTTP roundtrip transit time: {latency:.2f}ms")
        log_debug(f"Server response payload: {raw}")
        return data

    except KeyboardInterrupt:
        raise
    except Exception as e:
        log_err(f"Fire context exception: {e}")
        return None

def handle_resp(resp):
    code = resp.get("code")

    if code != 0:
        log_err(f"API rejection edge: return code={code}")
        log_debug(json.dumps(resp, indent=2))
        return False

    data = resp.get("data", {})
    result = data.get("apply_result")
    deadline = data.get("deadline_format", "")

    log_debug(f"Target query state mapped: apply_result={result}")

    if result == 1:
        log_ok("APPROVAL SEEDED SUCCESSFULLY 🎉")
        return True
    elif result == 3:
        log_warn(f"Server capacity exhausted. Quota limit reached until: {deadline}")
        return False
    elif result == 4:
        log_err(f"Account security velocity threshold hit. Blocked until: {deadline}")
        return False
    else:
        log_warn(f"Unmapped fallback code state received: {resp}")
        return False

def main():
    device_id = gen_device_id()
    session = Session()

    log_info("Running credential check and API endpoint validations...")
    if not check_status(session, token, device_id):
        return

    start_bt = get_ntp_beijing()
    start_perf = time.perf_counter()

    target = get_target(start_bt)
    
    fire_start = target - timedelta(milliseconds=OFFSET_MS)

    wait_target(start_bt, start_perf, fire_start)

    clear()
    show_beijing_time()
    print(f'{GB}🚀 PRECISE BURST ENGINE DEPLOYED NOW!\n')

    success = False

    try:
        for i in range(BURST_COUNT):
            shot_target = target + timedelta(milliseconds=i * BURST_INTERVAL_MS)

            while True:
                shot_time = synced_time(start_bt, start_perf)
                diff = (shot_target - shot_time).total_seconds()

                if diff <= 0:  
                    break
                
                time.sleep(max(diff * 0.7, 0.0001))

            actual_fire = synced_time(start_bt, start_perf)
            timing_error = (actual_fire - shot_target).total_seconds() * 1000

            print(
                f"{B}[SHOT {i+1:02}/{BURST_COUNT:02}]{Fore.RESET} "
                f"Target={shot_target.strftime('%H:%M:%S.%f')[:-3]} "
                f"| Actual={actual_fire.strftime('%H:%M:%S.%f')[:-3]} "
                f"| Error={timing_error:+.2f}ms"
            )

            resp = fire(session, token, device_id)

            if resp:
                if handle_resp(resp):
                    success = True
                    log_ok(f"BURST PIPELINE RESOLVED ON SHOT APPLICATION POSITION #{i+1}")
                    break  

    except KeyboardInterrupt:
        log_warn("High-frequency execution matrix halted via manual interrupt rules.")

    if not success:
        print(f'{R}\n❌ Precise loop sequence completed. Allocation window closed without approval.')

    print(f'{Y}[*] Next open server pool cycle resets at: 00:00 Beijing time tomorrow.\n')

if __name__ == "__main__":
    main()
