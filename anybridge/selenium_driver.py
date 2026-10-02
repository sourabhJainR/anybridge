"""Selenium/WebDriver provider with the same async AnyBridge capability surface."""
from __future__ import annotations
import asyncio, base64, time
from pathlib import Path
from .security import NetworkGuard
from .sites import normalize_url

_HERE=Path(__file__).parent
SHIM=(_HERE/"shim.js").read_text()
PAGETOOLS=(_HERE/"pagetools.js").read_text()

class SeleniumDependencyError(RuntimeError): pass

class SeleniumDriver:
    def __init__(self,url=None,headless=True,*,allow_private_network=True,storage_state=None,
                 allowed_hosts=(),browser="chrome",driver=None):
        self.url=normalize_url(url) if url else "about:blank"
        self.headless=headless; self.storage_state=storage_state
        self.browser=browser.casefold()
        self._guard=NetworkGuard(allow_private=allow_private_network,isolate_private=True,allowed_hosts=allowed_hosts)
        self._driver=driver; self._owns_driver=driver is None; self._started=False; self._injected=False

    def _import(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            from selenium.webdriver.edge.options import Options as EdgeOptions
            return webdriver,ChromeOptions,FirefoxOptions,EdgeOptions
        except ImportError as e:
            raise SeleniumDependencyError("Install anybridge[selenium] to use the Selenium provider.") from e

    def _create_driver(self):
        webdriver,ChromeOptions,FirefoxOptions,EdgeOptions=self._import()
        if self.browser=="chrome":
            o=ChromeOptions()
            if self.headless:o.add_argument("--headless=new")
            o.add_argument("--disable-background-networking");o.add_argument("--disable-component-update")
            o.add_argument("--disable-sync");o.add_argument("--no-first-run")
            return webdriver.Chrome(options=o)
        if self.browser=="firefox":
            o=FirefoxOptions()
            if self.headless:o.add_argument("-headless")
            return webdriver.Firefox(options=o)
        if self.browser=="edge":
            o=EdgeOptions()
            if self.headless:o.add_argument("--headless=new")
            return webdriver.Edge(options=o)
        raise ValueError(f"Unsupported Selenium browser: {self.browser!r}")

    async def start(self,settle=1.0):
        if self._started:return self
        self._driver=self._driver or await asyncio.to_thread(self._create_driver)
        self._started=True
        if self.url!="about:blank":
            await self.navigate(self.url); await asyncio.sleep(settle)
        return self

    async def close(self):
        if self._driver is not None and self._owns_driver:
            await asyncio.to_thread(self._driver.quit)
        self._driver=None; self._started=False

    @property
    def started(self):return self._started
    @property
    def current_url(self):return self._driver.current_url if self._driver else self.url
    async def _run(self,fn,*args):return await asyncio.to_thread(fn,*args)

    async def _inject(self):
        if self._injected:return
        await self._run(self._driver.execute_script,SHIM)
        await self._run(self._driver.execute_script,PAGETOOLS)
        self._injected=True

    async def navigate(self,url):
        url=await self._guard.assert_url(normalize_url(url))
        await self._run(self._driver.get,url); self._injected=False; await self._inject()
        return await self.current_site()

    async def current_site(self):
        if not self._started:return {}
        return await self._run(lambda:{"url":self._driver.current_url,"title":self._driver.title})

    async def snapshot(self,interactive_only=True,compact=True,selector=None,max_chars=12000):
        await self._inject()
        script="return arguments[0] ? (document.querySelector(arguments[0])?.innerText || '') : (document.body?.innerText || '');"
        return str(await self._run(self._driver.execute_script,script,selector) or "")[:max_chars]

    def _ref_css(self,ref):return f'[data-anybridge-ref="{ref.replace(chr(34),chr(92)+chr(34))}"]'

    async def click_ref(self,ref):
        e=await self._run(self._driver.find_element,"css selector",self._ref_css(ref));await self._run(e.click);return await self.snapshot()

    async def fill_ref(self,ref,value,press_enter=False):
        e=await self._run(self._driver.find_element,"css selector",self._ref_css(ref));await self._run(e.clear);await self._run(e.send_keys,value)
        if press_enter:
            from selenium.webdriver.common.keys import Keys
            await self._run(e.send_keys,Keys.ENTER)
        return await self.snapshot()

    async def select_ref(self,ref,value):
        from selenium.webdriver.support.ui import Select
        e=await self._run(self._driver.find_element,"css selector",self._ref_css(ref));await self._run(Select(e).select_by_visible_text,value);return await self.snapshot()

    async def press_key(self,key,ref=None):
        from selenium.webdriver.common.keys import Keys
        e=await self._run(self._driver.find_element,"css selector",self._ref_css(ref)) if ref else await self._run(lambda:self._driver.switch_to.active_element)
        await self._run(e.send_keys,getattr(Keys,key.upper(),key));return await self.snapshot()

    async def wait_for(self,selector=None,text=None,timeout_ms=10000):
        deadline=time.monotonic()+timeout_ms/1000
        while time.monotonic()<deadline:
            if selector and await self._run(self._driver.find_elements,"css selector",selector):return True
            if text and text in await self._run(lambda:self._driver.find_element("tag name","body").text):return True
            await asyncio.sleep(.1)
        raise TimeoutError("Timed out waiting for the requested browser condition.")

    async def extract_structured(self,schema,selector=None):
        await self._inject()
        value=await self._run(self._driver.execute_script,"const e=arguments[0]?document.querySelector(arguments[0]):document.body; return e?e.innerText:'';",selector)
        return {"text":str(value or ""), "schema":schema}

    async def screenshot(self,full_page=False):
        return base64.b64encode(await self._run(self._driver.get_screenshot_as_png)).decode("ascii")

    async def list_tools(self):
        await self._inject()
        return await self._run(self._driver.execute_script,"return window.__anybridge__?.listTools?.() || [];")

    async def call_tool(self,name,arguments):
        await self._inject()
        script="return window.__anybridge__.callTool(arguments[0],arguments[1]);"
        return await self._run(self._driver.execute_async_script,"const done=arguments[arguments.length-1]; Promise.resolve(window.__anybridge__.callTool(arguments[0],arguments[1])).then(done);",name,arguments)

    async def network_policy(self):return self._guard.policy()
    async def trust_host(self,host):self._guard.allow_hosts((host,));return self._guard.policy()
    async def revoke_host(self,host):return self._guard.revoke_host(host)
