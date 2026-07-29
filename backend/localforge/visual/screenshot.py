import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Standard installation paths for Chrome and Edge on Windows
WINDOWS_BROWSER_PATHS = [
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser_executable() -> str | None:
    """Find Google Chrome or Microsoft Edge executable on Windows."""
    for path in WINDOWS_BROWSER_PATHS:
        if os.path.isfile(path):
            return path

    # Try locating via basic command query if not found in standard paths
    for exe in ["msedge.exe", "chrome.exe"]:
        try:
            # check if exe is on PATH using 'where' command in Windows
            res = subprocess.run(["where", exe], capture_output=True, text=True, check=True)
            path = res.stdout.strip().split("\n")[0]
            if os.path.isfile(path):
                return path
        except Exception:
            continue

    return None


def capture_html_screenshot(html_path: str, output_image_path: str) -> bool:
    """Capture a screenshot of a local HTML file using Chrome/Edge Headless.

    Returns True if screenshot was captured successfully, False otherwise.
    """
    if not os.path.isfile(html_path):
        logger.error(f"HTML file not found for screenshot: {html_path}")
        return False

    browser_exe = find_browser_executable()
    if not browser_exe:
        logger.error(
            "No compatible browser (Chrome or Edge) found for visual validation screenshots."
        )
        return False

    # Standardize absolute paths with absolute formatting for file:// schema or simple path resolution
    abs_html = os.path.abspath(html_path)
    abs_output = os.path.abspath(output_image_path)

    # Ensure directory of the output image exists
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)

    # Build CLI command for headless capture
    with tempfile.TemporaryDirectory(prefix="localforge-headless-") as profile_dir:
        cache_dir = os.path.join(profile_dir, "cache")
        cmd = [
            browser_exe,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--disable-gpu-compositing",
            "--disable-accelerated-2d-canvas",
            "--disable-accelerated-video-decode",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-features=VizDisplayCompositor",
            "--hide-scrollbars",
            f"--user-data-dir={profile_dir}",
            f"--disk-cache-dir={cache_dir}",
            f"--screenshot={abs_output}",
            "--window-size=1280,720",
            "file:///" + abs_html.replace("\\", "/"),
        ]

        logger.info(f"Running screenshot command: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as exc:
            logger.error(f"Failed to execute browser screenshot: {exc}")
            return False
        if os.path.isfile(abs_output) and os.path.getsize(abs_output) > 0:
            logger.info(f"Successfully captured screenshot to: {abs_output}")
            return True
        else:
            logger.error(
                f"Browser screenshot failed: output file not created. Stdout: {res.stdout}, Stderr: {res.stderr}"
            )
            return False
