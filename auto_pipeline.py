# 抖音当天视频自动搬运到B站
import subprocess
import json
import sys
from datetime import date
from pathlib import Path

# ========== 配置 ==========
DOUYIN_USER_URL = "https://www.douyin.com/user/MS4wLjABAAAAsFL91bhVsEDoW39ZsExLDP6vhQ901VeWqx_eANoIMjJM4fKuSnka68tqyBHJs87j"  # 替换为目标抖音用户主页链接
DOWNLOAD_DIR = Path("./downloads")
BILI_TID = 138        # B站分区ID，138=搞笑，自行调整
BILI_COPYRIGHT = 2    # 2=转载
BILI_SOURCE = DOUYIN_USER_URL
BILI_TAGS = ["抖音", "搬运"]
# ==========================

def get_today_videos() -> list[dict]:
    """获取目标账号今日发布的视频信息列表"""
    result = subprocess.run(
        ["python", "douyin_download.py", "info", DOUYIN_USER_URL, "--full"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("获取视频信息失败:", result.stderr)
        return []

    all_videos = json.loads(result.stdout)  # 根据你的 info 实际输出格式调整
    today = date.today().isoformat()        # "2025-04-15"

    today_videos = []
    for v in all_videos:
        # create_time 字段名请根据 --full 的实际输出调整
        create_time = v.get("create_time", "")
        if create_time.startswith(today):
            today_videos.append(v)

    print(f"今日新视频数量: {len(today_videos)}")
    return today_videos


def download_video(video: dict) -> Path | None:
    """下载单个无水印视频，返回本地文件路径"""
    url = video.get("share_url") or video.get("aweme_id")  # 根据实际字段调整
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    result = subprocess.run(
        ["python", "douyin_download.py", "download", url],
        capture_output=True, text=True, cwd="."
    )
    if result.returncode != 0:
        print(f"下载失败: {url}\n{result.stderr}")
        return None

    # 找到最新下载的 mp4 文件（简单策略：mtime 最新）
    mp4_files = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    return mp4_files[0] if mp4_files else None


def upload_to_bilibili(video_path: Path, title: str, desc: str):
    """上传视频到B站"""
    tags_args = BILI_TAGS
    result = subprocess.run(
        [
            "python", "bilibili_upload.py", "upload",
            "--file", str(video_path),
            "--title", title[:80],   # B站标题限80字
            "--tid", str(BILI_TID),
            "--tags", *tags_args,
            "--desc", desc[:250],
            "--copyright", str(BILI_COPYRIGHT),
            "--source", BILI_SOURCE,
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"上传失败: {video_path.name}\n{result.stderr}")
        return False
    print(f"上传成功: {video_path.name}")
    return True


def main():
    videos = get_today_videos()
    if not videos:
        print("今日无新视频，退出。")
        sys.exit(0)

    for video in videos:
        title = video.get("desc", "抖音视频搬运")
        desc  = video.get("desc", "")

        print(f"\n处理视频: {title}")
        video_path = download_video(video)
        if not video_path:
            continue

        upload_to_bilibili(video_path, title, desc)

        # 上传完成后删除本地文件，节省磁盘
        video_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()