import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import websocket
from datetime import datetime
import rel
import ssl
import traceback


def get_env_var(env_var: str) -> str:
    """Return environment variable of key ``env_var``. Will stop application if not found."""
    try:
        return os.environ[env_var]
    except KeyError:
        print(f"Missing environment variable: {env_var}")
        raise


def get_env_consts() -> dict:
    """Return dict containing all required environment variables at application launch."""
    env_const_dict = {
        "IP_USERNAME": "",
        "IP_PASSWORD": "",
    }

    for key in env_const_dict:
        env_const_dict[key] = get_env_var(key)

    return env_const_dict


async def get_signature() -> str:
    """
    Uses a Playwright headless browser to authenticate login.

    User authentication is done via HTTP, the server sends an authentication signature to the client which is then
    sent as the first frame over the websocket.

    A browser is used to comply with CORS security measures.

    :return: Authentication signature
    :rtype: str
    """
    async with async_playwright() as p:
        browser_type = p.chromium
        browser = await browser_type.launch_persistent_context("persistent_context")
        page = await browser.new_page()

        await page.goto("https://idle-pixel.com/login/")
        await page.locator('[id=id_username]').fill(env_consts["IP_USERNAME"])
        await page.locator('[id=id_password]').fill(env_consts["IP_PASSWORD"])
        await page.locator("[id=login-submit-button]").click()

        page_content = await page.content()
        soup = BeautifulSoup(page_content, 'html.parser')
        script_tag = soup.find("script").text

        sig_plus_wrap = script_tag.split(";", 1)[0]

        signature = sig_plus_wrap.split("'")[1]

        return signature


def on_ws_message(ws, raw_message: str):
    """
    Primary handler for received websocket frames.

    :param ws: websocket
    :param raw_message: String containing websocket data
    :type raw_message: str
    """

    log_ws_message(raw_message, True)


def on_ws_error(ws, error):
    """
    Top level error handler.

    If websocket connection drops, will print a retrying message to notify before ``rel`` retries.
    Otherwise, prints timestamp, error, and traceback.

    :param ws: websocket
    :param error: Exception object
    """

    if isinstance(error, websocket.WebSocketConnectionClosedException):
        print("Connection closed. Retrying...")
    else:
        print(datetime.now().strftime("%d/%m/%Y , %H:%M:%S"))
        print(error)
        traceback.print_tb(error.__traceback__)


def on_ws_close(ws, close_status_code, close_msg):
    """Called when websocket is closed by server."""
    print("### closed ###")


def on_ws_open(ws):
    """
    Called when websocket opens.

    Acquires authentication signature then sends it as first frame over websocket.

    :param ws: websocket
    """
    print("Opened connection.")
    print("Acquiring signature...")
    signature = asyncio.run(get_signature())
    print("Signature acquired.")
    print("Logging in...")
    ws.send(f"LOGIN={signature}")


def log_ws_message(raw_message: str, received: bool):
    message_data = {
        "time": datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
        "length": len(raw_message),
        "message": raw_message,
        "received": received,
    }

    direction_indicator = "↓" if received else "↑"

    formatted_output = f"{direction_indicator}[{message_data['time']}] {message_data['message']}"

    print(formatted_output)


if __name__ == "__main__":
    env_consts = get_env_consts()

    websocket.enableTrace(False)
    ws = websocket.WebSocketApp("wss://server1.idle-pixel.com",
                                on_open=on_ws_open,
                                on_message=on_ws_message,
                                on_error=on_ws_error,
                                on_close=on_ws_close)

    ws.run_forever(dispatcher=rel,
                   reconnect=120,
                   sslopt={"cert_reqs": ssl.CERT_NONE})  # Set dispatcher to automatic reconnection, 5 second reconnect delay if connection closed unexpectedly, no SSL cert
    rel.signal(2, rel.abort)  # Keyboard Interrupt
    rel.dispatch()
