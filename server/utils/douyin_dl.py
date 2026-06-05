"""
Playwright Downloader — tai video tu TikTok, Douyin bang browser automation.
Mo trinh duyet that, render JS, intercept API response de lay video URL.
"""
import asyncio, re, json, logging, os

logger = logging.getLogger(__name__)


class PlaywrightDownloader:
    """Tai video tu TikTok/Douyin bang Playwright (browser automation)."""

    def __init__(self):
        self._chrome_dir = self._find_chrome_profile()

    def _find_chrome_profile(self) -> str:
        dirs = [
            r"C:\Users\ACER\AppData\Local\Google\Chrome\User Data\Profile 2",
            r"C:\Users\ACER\AppData\Local\Google\Chrome\User Data\Default",
            r"C:\Users\ACER\AppData\Local\Microsoft\Edge\User Data\Default",
        ]
        for d in dirs:
            if os.path.exists(d):
                return d
        return ""

    def _find_tiktok_video(self, html: str) -> str:
        """Tim video URL trong TikTok page HTML."""
        # Giai ma unicode escapes (TikTok uses \\u002F cho forward slash)
        html = html.replace("\\\\u002F", "/").replace("\\u002F", "/").replace("\\/", "/")
        # Tim URL mp4 voi mime_type marker
        urls = re.findall(r'https?://[^"\'<>,\s]{10,300}?mime_type=video_mp4[^"\'<>,\s]*', html)
        for u in urls:
            if any(x in u for x in ["tiktok", "p16", "byte"]):
                return u.split('"')[0].split(",")[0]
        return ""

    def _find_douyin_video(self, data: dict) -> str:
        """Tim video URL tu Douyin API response."""
        try:
            aweme = data.get("aweme_detail", {})
            video = aweme.get("video", {})
            for key in ["play_addr", "download_addr", "bit_rate"]:
                addr = video.get(key, {})
                urls = addr.get("url_list", [])
                if urls:
                    return urls[0]
        except Exception:
            pass
        raw = json.dumps(data)
        for ext in [".mp4", ".m3u8"]:
            urls = re.findall(rf'https?://[^"\'<> ]+{re.escape(ext)}[^"\'<> ]*', raw)
            for u in urls:
                if "douyin" in u or "byte" in u or "zjcdn" in u:
                    return u
        return ""

    def _detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        if "tiktok.com" in url_lower:
            return "tiktok"
        if "douyin.com" in url_lower or "iesdouyin.com" in url_lower:
            return "douyin"
        return "unknown"

    async def get_video_url(self, page_url: str) -> str:
        """
        Mo trang bang Playwright, cho JS render, tim video URL.
        Supports: TikTok, Douyin.
        """
        from playwright.async_api import async_playwright

        platform = self._detect_platform(page_url)
        video_url = ""
        api_event = asyncio.Event()

        async with async_playwright() as p:
            if self._chrome_dir:
                logger.info(f"Dung Chrome profile: {self._chrome_dir}")
                context = await p.chromium.launch_persistent_context(
                    self._chrome_dir,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                page = context.pages[0] if context.pages else await context.new_page()
            else:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

            await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

            # Intercept API responses
            api_patterns = {
                "tiktok": ["/api/", "/v1/", "/node/"],
                "douyin": ["/aweme/v1/web/aweme/detail/", "/aweme_detail"],
            }.get(platform, [])

            async def handle_response(response):
                nonlocal video_url, api_event
                url = response.url

                # TikTok: intercept webapp data
                if platform == "tiktok" and "/api/trending" in url:
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        vu = self._find_tiktok_video(data)
                        if vu:
                            video_url = vu
                            api_event.set()
                    except Exception:
                        pass

                # Douyin: intercept detail API
                if platform == "douyin" and any(p in url for p in api_patterns):
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        vu = self._find_douyin_video(data)
                        if vu:
                            video_url = vu
                            api_event.set()
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                await page.goto(page_url, wait_until="commit", timeout=30000)

                # Doi API response
                for _ in range(15):
                    if api_event.is_set():
                        break
                    await page.wait_for_timeout(1000)

                logger.info(f"Title: {await page.title()}")

                # Neu chua co, extract tu page content
                if not video_url:
                    html = await page.content()

                    # TikTok: tim video URL trong HTML
                    if platform == "tiktok":
                        video_url = self._find_tiktok_video(html)

                    # Douyin: tim __INITIAL_STATE__
                    if platform == "douyin":
                        matches = re.findall(
                            r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL,
                        )
                        for m in matches:
                            try:
                                data = json.loads(m)
                                vu = self._find_douyin_video(data)
                                if vu:
                                    video_url = vu
                                    break
                            except Exception:
                                pass

            except Exception as e:
                logger.error(f"Playwright {platform}: {e}")
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

        return video_url

    async def download_video(self, page_url: str, output_path: str, video_url: str = "") -> str:
        """Tai video ve file."""
        import aiohttp

        if not video_url:
            video_url = await self.get_video_url(page_url)
        if not video_url:
            raise RuntimeError("Khong the lay video URL")

        logger.info(f"Dang tai: {video_url[:60]}...")
        ref = "https://www.tiktok.com/" if self._detect_platform(page_url) == "tiktok" else "https://www.douyin.com/"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": ref}

        async with aiohttp.ClientSession(headers=headers) as sess:
            async with sess.get(video_url, timeout=120) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                with open(output_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)

        if os.path.getsize(output_path) > 0:
            logger.info(f"Da tai: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path
        raise RuntimeError("File tai ve rong")


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    async def test():
        d = PlaywrightDownloader()
        for url in [
            "https://www.tiktok.com/@hc.ting.trung.mi21/video/7386105127813254416",
            "https://www.douyin.com/video/7645606168974648155",
        ]:
            print(f"\nThu: {url[:60]}...")
            vu = await d.get_video_url(url)
            if vu:
                print(f"OK: {vu[:80]}")
            else:
                print("FAIL")
    asyncio.run(test())
