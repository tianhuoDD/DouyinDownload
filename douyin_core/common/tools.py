from urllib.parse import urlparse
from datetime import datetime, date, timedelta
def extract_sec_user_id(url: str) -> str | None:
    """
    从抖音用户主页 URL 中提取 sec_user_id
    """
    try:
        parsed = urlparse(url)
        path = parsed.path  # /user/xxxxx

        if "/user/" not in path:
            return None

        sec_user_id = path.split("/user/")[-1].strip("/")

        # 去掉可能的 query 参数残留（保险）
        sec_user_id = sec_user_id.split("?")[0]

        return sec_user_id if sec_user_id else None

    except Exception:
        return None
def is_today(ts: int) -> bool:
    """判断时间戳是否为今天"""
    return datetime.fromtimestamp(ts).date() == date.today()

def is_yesterday(ts: int) -> bool:
    """判断时间戳是否为昨天"""
    return datetime.fromtimestamp(ts).date() == date.today() - timedelta(days=1)
if __name__ == "__main__":
    url = "https://www.douyin.com/user/MS4wLjABAAAAsFL91bhVsEDoW39ZsExLDP6vhQ901VeWqx_eANoIMjJM4fKuSnka68tqyBHJs87j?from_tab_name=main"
    sec_user_id = extract_sec_user_id(url)
    print(sec_user_id)