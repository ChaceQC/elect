"""拼接既有同视口参考截图；仅处理合成验收图片，不访问业务服务。"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    root = Path(sys.argv[1])
    for width in (1440, 375):
        for page in ("login", "monitor", "rooms", "details", "overview"):
            before = Image.open(root / "reference" / f"{width}-{page}.png").convert("RGB")
            after = Image.open(root / "ui-fixes" / f"{width}-{page}.png").convert("RGB")
            assert before.width == after.width == width
            canvas = Image.new("RGB", (width * 2 + 20, max(before.height, after.height) + 30), "white")
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 8), "REFERENCE", fill="black")
            draw.text((width + 28, 8), "CURRENT 0.18.1", fill="black")
            canvas.paste(before, (0, 30))
            canvas.paste(after, (width + 20, 30))
            canvas.save(root / "ui-fixes" / f"compare-{width}-{page}.png")
    print("已生成10张同视口参考/修复后对照图")


if __name__ == "__main__":
    main()
