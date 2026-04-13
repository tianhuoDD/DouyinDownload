from pathlib import Path
import yaml

# =========================
# 项目根目录（自动定位）
# =========================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# =========================
# 配置文件路径
# =========================
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

# =========================
# 读取配置（只加载一次）
# =========================
def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()